"""Bridge authenticated interview sessions to LangGraph and durable domain records."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Assessment,
    AssessmentControl,
    AssessmentModule,
    AssessmentSession,
    ControlResult,
    InterviewTurn,
    KBVersion,
    Question as DBQuestion,
)
from app.schemas.agent_results import AgentControlResult
from app.schemas.decision_trace import DecisionTrace, TraceSource
from app.schemas.interviews import InterviewTurnRead
from app.services.agent_results import save_agent_result
from app.services.decision_traces import record_interview_trace
from app.services.langgraph_checkpointer import (
    interview_thread_config,
    open_interview_checkpointer,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_TURN_REF = re.compile(r"^turn:(\d+)$")
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))


@dataclass(frozen=True)
class _AgentContext:
    assessment: Assessment
    session: AssessmentSession
    knowledge_base: Any
    question_codes: list[str]
    control_codes: list[str]
    question_ids: dict[str, UUID]


def start_interview_agent(db: Session, session_id: UUID) -> list[InterviewTurnRead]:
    """Create the first agent prompt, or reconcile an already checkpointed session."""
    return _run_interview_graph(db, session_id, answer_turn_id=None)


def advance_interview_agent(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    session_id: UUID,
    answer_turn_id: UUID,
) -> list[InterviewTurnRead]:
    """Resume a session from one durable participant answer and persist graph output."""
    return _run_interview_graph(
        db,
        session_id,
        answer_turn_id=answer_turn_id,
        organization_id=organization_id,
        assessment_id=assessment_id,
    )


def _run_interview_graph(
    db: Session,
    session_id: UUID,
    *,
    answer_turn_id: UUID | None,
    organization_id: UUID | None = None,
    assessment_id: UUID | None = None,
) -> list[InterviewTurnRead]:
    # Hold the domain session row while invoking the graph. This serializes distinct
    # answer requests for one thread across API workers and protects checkpoint order.
    with db.begin():
        interview_session = db.scalar(
            select(AssessmentSession)
            .where(
                AssessmentSession.id == session_id,
                *(
                    [AssessmentSession.organization_id == organization_id]
                    if organization_id is not None
                    else []
                ),
                *(
                    [AssessmentSession.assessment_id == assessment_id]
                    if assessment_id is not None
                    else []
                ),
            )
            .with_for_update()
        )
        if interview_session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found.")

        context = _load_agent_context(db, interview_session)
        answer_turn = None
        if answer_turn_id is not None:
            answer_turn = db.scalar(
                select(InterviewTurn).where(
                    InterviewTurn.id == answer_turn_id,
                    InterviewTurn.organization_id == interview_session.organization_id,
                    InterviewTurn.session_id == interview_session.id,
                    InterviewTurn.speaker == "participant",
                )
            )
            if answer_turn is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview answer not found.")

        config = interview_thread_config(interview_session.id)
        with open_interview_checkpointer() as checkpointer:
            graph, _tracer = _build_graph(context, checkpointer=checkpointer)
            snapshot = graph.get_state(config)
            saved_turns = list(
                db.scalars(
                    select(InterviewTurn)
                    .where(
                        InterviewTurn.organization_id == interview_session.organization_id,
                        InterviewTurn.session_id == interview_session.id,
                    )
                    .order_by(InterviewTurn.sequence_no)
                )
            )

            if not snapshot.values:
                if saved_turns:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Interview turns exist without a resumable agent checkpoint.",
                    )
                from agentic_grc_agent.nodes import initial_state

                graph.invoke(
                    initial_state(
                        str(interview_session.organization_id),
                        str(interview_session.assessment_id),
                        context.question_codes,
                        in_scope_control_codes=context.control_codes,
                        kb_version=context.knowledge_base.kb_version,
                    ),
                    config,
                )
                snapshot = graph.get_state(config)
            else:
                _validate_checkpoint_scope(snapshot.values, context)

            if answer_turn is not None:
                _resume_for_saved_answer(graph, snapshot, config, answer_turn)
                snapshot = graph.get_state(config)
            elif snapshot.values:
                checkpoint_sequence = max(
                    (int(turn["seq"]) for turn in snapshot.values.get("turns", [])),
                    default=0,
                )
                unprocessed_answers = [
                    turn
                    for turn in saved_turns
                    if turn.speaker == "participant" and turn.sequence_no > checkpoint_sequence
                ]
                if len(unprocessed_answers) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Multiple saved answers are ahead of the interview checkpoint.",
                    )
                if unprocessed_answers:
                    _resume_for_saved_answer(graph, snapshot, config, unprocessed_answers[0])
                    snapshot = graph.get_state(config)

            graph_state = snapshot.values
            sequence_to_turn = _persist_graph_turns(db, context, graph_state.get("turns", []))
            _persist_graph_traces(db, context, graph_state.get("traces", []), sequence_to_turn)

            first_generated_sequence = (
                answer_turn.sequence_no + 1 if answer_turn is not None else 1
            )
            generated_rows = list(
                db.scalars(
                    select(InterviewTurn)
                    .where(
                        InterviewTurn.organization_id == interview_session.organization_id,
                        InterviewTurn.session_id == interview_session.id,
                        InterviewTurn.speaker == "agent",
                        InterviewTurn.sequence_no >= first_generated_sequence,
                    )
                    .order_by(InterviewTurn.sequence_no)
                )
            )

        return [_turn_read(turn) for turn in generated_rows]


def _load_agent_context(db: Session, interview_session: AssessmentSession) -> _AgentContext:
    from agentic_grc_agent.knowledge import load_kb

    assessment = db.scalar(
        select(Assessment).where(
            Assessment.id == interview_session.assessment_id,
            Assessment.organization_id == interview_session.organization_id,
        )
    )
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    controls = list(
        db.scalars(
            select(AssessmentControl)
            .where(
                AssessmentControl.organization_id == assessment.organization_id,
                AssessmentControl.assessment_id == assessment.id,
                AssessmentControl.in_scope.is_(True),
            )
            .order_by(AssessmentControl.control_code)
        )
    )
    control_codes = [control.control_code for control in controls]
    if not control_codes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment has no in-scope controls configured for an interview.",
        )

    app_settings = get_settings()
    kb_path = app_settings.agrc_kb_path or (
        _REPOSITORY_ROOT / "agentic_grc_agent" / "data" / "kb_demo.yaml"
    )
    try:
        knowledge_base = load_kb(kb_path)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assessment knowledge base is unavailable.",
        ) from exc
    if knowledge_base.kb_version != assessment.kb_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The assessment knowledge-base version is not configured for the interview agent.",
        )
    if knowledge_base.language_code != "en":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The configured interview agent currently supports English only.",
        )

    stored_kb_version = db.scalar(
        select(KBVersion).where(KBVersion.label == assessment.kb_version)
    )
    if stored_kb_version is not None and stored_kb_version.status != "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The assessment knowledge-base version is not published for interviews.",
        )

    question_query = (
        select(DBQuestion, AssessmentModule)
        .join(AssessmentModule, AssessmentModule.id == DBQuestion.module_id)
        .join(KBVersion, KBVersion.id == AssessmentModule.kb_version_id)
        .where(
            KBVersion.label == assessment.kb_version,
            KBVersion.status == "published",
        )
        .order_by(AssessmentModule.sort_order, DBQuestion.sort_order, DBQuestion.code)
    )
    if interview_session.block_id is not None:
        question_query = question_query.where(AssessmentModule.block_id == interview_session.block_id)
    db_questions = db.execute(question_query).all()

    yaml_by_code = {question.code: question for question in knowledge_base.questions}
    question_ids: dict[str, UUID] = {}
    selected_codes: list[str] = []
    selected_questions = []
    if db_questions:
        for db_question, module in db_questions:
            if db_question.code not in yaml_by_code:
                continue
            if db_question.code in question_ids:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The configured knowledge base contains duplicate question codes.",
                )
            base_question = yaml_by_code[db_question.code]
            selected_codes.append(db_question.code)
            question_ids[db_question.code] = db_question.id
            selected_questions.append(
                base_question.model_copy(
                    update={"text": db_question.question_text, "module": module.name}
                )
            )
    else:
        if interview_session.block_id is not None or app_settings.interview_data_mode != "synthetic":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This interview requires questions stored in the assessment knowledge base.",
            )
        selected_codes = [question.code for question in knowledge_base.questions]
        selected_questions = list(knowledge_base.questions)

    if not selected_codes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No interview questions are configured for the assessment knowledge-base version.",
        )
    if not any(
        mapping.node_code in set(control_codes)
        for question in selected_questions
        for mapping in question.mappings
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No configured interview questions map to the assessment's in-scope controls.",
        )

    scoped_kb = knowledge_base.model_copy(update={"questions": selected_questions})
    return _AgentContext(
        assessment=assessment,
        session=interview_session,
        knowledge_base=scoped_kb,
        question_codes=selected_codes,
        control_codes=control_codes,
        question_ids=question_ids,
    )


def _build_graph(context: _AgentContext, checkpointer=None, tracer=None):
    from agentic_grc_agent.graph import build_graph
    from agentic_grc_agent.llm import OllamaLLM
    from agentic_grc_agent.nodes import Deps
    from agentic_grc_agent.trace import TraceRecorder

    settings = get_settings()
    try:
        llm = OllamaLLM(
            settings.agrc_llm_model,
            settings.agrc_ollama_host,
            settings.agrc_llm_timeout_s,
            settings.agrc_llm_retries,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The interview model runtime is unavailable.",
        ) from exc

    if tracer is None:
        tracer = TraceRecorder()
    deps = Deps(
        llm=llm,
        kb=context.knowledge_base,
        tracer=tracer,
        max_follow_ups=settings.agrc_max_follow_ups,
    )
    return build_graph(deps, checkpointer=checkpointer), tracer


def _validate_checkpoint_scope(state: dict, context: _AgentContext) -> None:
    existing_scope = state.get("in_scope_control_codes")
    if existing_scope is None or set(existing_scope) != set(context.control_codes):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved interview checkpoint does not match the assessment's current control scope.",
        )
    if (
        state.get("organization_id") != str(context.session.organization_id)
        or state.get("assessment_id") != str(context.assessment.id)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Interview checkpoint mismatch.")
    if state.get("kb_version") != context.knowledge_base.kb_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved interview checkpoint uses a different knowledge-base version.",
        )
    if state.get("question_codes") != context.question_codes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved interview question scope no longer matches the assessment.",
        )


def _resume_for_saved_answer(graph, snapshot, config: dict, answer_turn: InterviewTurn) -> None:
    turns = snapshot.values.get("turns", [])
    graph_by_sequence = {int(turn["seq"]): turn for turn in turns}
    graph_sequence = max(graph_by_sequence, default=0)
    graph_answer = graph_by_sequence.get(answer_turn.sequence_no)

    if answer_turn.sequence_no <= graph_sequence:
        if (
            graph_answer is None
            or graph_answer.get("speaker") != "participant"
            or graph_answer.get("content") != answer_turn.content
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The saved answer does not match the resumable interview checkpoint.",
            )
        return

    if answer_turn.sequence_no != graph_sequence + 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview checkpoint is behind the saved answer history.",
        )
    if not any(task.interrupts for task in snapshot.tasks):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview agent is not waiting for an answer.",
        )
    graph.invoke(Command(resume=answer_turn.content), config)


def _persist_graph_turns(db: Session, context: _AgentContext, graph_turns: list[dict]) -> dict[int, InterviewTurn]:
    existing_rows = list(
        db.scalars(
            select(InterviewTurn)
            .where(
                InterviewTurn.organization_id == context.session.organization_id,
                InterviewTurn.session_id == context.session.id,
            )
            .order_by(InterviewTurn.sequence_no)
        )
    )
    by_sequence = {turn.sequence_no: turn for turn in existing_rows}
    max_sequence = max(by_sequence, default=0)
    for graph_turn in graph_turns:
        sequence_no = int(graph_turn["seq"])
        speaker = graph_turn["speaker"]
        turn_type = graph_turn["turn_type"]
        content = graph_turn["content"]
        question_id = context.question_ids.get(graph_turn["question_code"])
        existing = by_sequence.get(sequence_no)
        if existing is not None:
            if (
                existing.speaker != speaker
                or existing.turn_type != turn_type
                or existing.content != content
                or existing.question_id != question_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Persisted interview turns do not match the agent checkpoint.",
                )
            continue
        if speaker != "agent" or sequence_no != max_sequence + 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The agent checkpoint contains an unpersisted participant turn or a sequence gap.",
            )

        turn = InterviewTurn(
            organization_id=context.session.organization_id,
            session_id=context.session.id,
            sequence_no=sequence_no,
            speaker="agent",
            participant_id=None,
            turn_type=turn_type,
            question_id=question_id,
            replies_to_turn_id=None,
            content=content,
            language_code=context.knowledge_base.language_code,
        )
        db.add(turn)
        db.flush()
        by_sequence[sequence_no] = turn
        max_sequence = sequence_no
    return by_sequence


def _persist_graph_traces(
    db: Session,
    context: _AgentContext,
    trace_rows: list[dict],
    sequence_to_turn: dict[int, InterviewTurn],
) -> None:
    for raw_trace in trace_rows:
        trace_id = UUID(raw_trace["id"])
        source_ids: list[UUID] = []
        sources = []
        for raw_source in raw_trace.get("sources", []):
            if raw_source.get("type") != "interview_turn":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The interview agent emitted an unsupported trace source.",
                )
            match = _TURN_REF.fullmatch(raw_source.get("ref", ""))
            turn = sequence_to_turn.get(int(match.group(1))) if match else None
            if turn is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The interview trace references a turn that was not persisted.",
                )
            source_ids.append(turn.id)
            sources.append(TraceSource(type="interview_turn", ref=f"interview_turn:{turn.id}"))

        if not source_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The interview agent emitted a decision without a persisted source turn.",
            )

        trace = DecisionTrace(
            organization_id=UUID(raw_trace["organization_id"]),
            assessment_id=UUID(raw_trace["assessment_id"]),
            decision_type=raw_trace["decision_type"],
            control_ids=raw_trace["control_ids"],
            module=raw_trace.get("module"),
            sources=sources,
            evidence_nature=raw_trace.get("evidence_nature"),
            actor_type=raw_trace["actor_type"],
            actor_user_id=raw_trace.get("actor_user_id"),
            model_name=raw_trace.get("model_name"),
            prompt_id=raw_trace.get("prompt_id"),
            prompt_version=raw_trace.get("prompt_version"),
            kb_version=raw_trace["kb_version"],
            output=raw_trace["output"],
            rationale=raw_trace["rationale"],
            confidence=raw_trace.get("confidence"),
            requires_human_review=raw_trace.get("requires_human_review", False),
            latency_ms=raw_trace.get("latency_ms"),
            fallback_used=raw_trace.get("fallback_used", False),
        )

        if trace.decision_type == "status_assessed":
            result = AgentControlResult.from_agent_output(trace.output)
            existing_result = db.scalar(
                select(ControlResult.id).where(
                    ControlResult.organization_id == context.session.organization_id,
                    ControlResult.assessment_id == context.session.assessment_id,
                    ControlResult.trace_id == trace_id,
                )
            )
            if existing_result is None:
                save_agent_result(
                    db,
                    context.session.organization_id,
                    context.session.assessment_id,
                    result,
                    trace,
                    source_turn_ids=source_ids,
                    trace_record_id=trace_id,
                )
        else:
            record_interview_trace(db, trace, source_ids, record_id=trace_id)


def _turn_read(turn: InterviewTurn) -> InterviewTurnRead:
    return InterviewTurnRead(
        id=turn.id,
        sequence_no=turn.sequence_no,
        speaker=turn.speaker,
        participant_id=turn.participant_id,
        turn_type=turn.turn_type,
        question_id=turn.question_id,
        replies_to_turn_id=turn.replies_to_turn_id,
        content=turn.content,
        language_code=turn.language_code,
        created_at=turn.created_at,
        source_references=[
            {"type": "interview_turn", "ref": f"interview_turn:{turn.id}"}
        ],
    )
