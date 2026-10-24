"""Store the interview agent's results (AGRC-32)."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assessment, AssessmentControl, ControlResult
from app.schemas.agent_results import AgentControlResult
from app.schemas.decision_trace import DecisionTrace
from app.services.decision_traces import record_interview_trace, record_trace


def save_agent_result(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    result: AgentControlResult,
    trace: DecisionTrace,
    *,
    source_turn_ids: Sequence[UUID] | None = None,
    trace_record_id: UUID | None = None,
) -> list[ControlResult]:
    """Add the agent's result for one question to the current transaction.

    Records the status_assessed trace, then adds one versioned control_results row
    per control id (author "agent") linked to that trace. Each new row chains to
    the previous version and enters the expert review queue.

    Current limitation: evidence_refs stays empty and maturity null, because the
    agent does not attach documents or assess maturity yet.

    Every check runs before anything is written. It only flushes: the caller commits, so the trace and the rows are saved together
    or not at all.
    """
    _check_trace(organization_id, assessment_id, result, trace)

    assessment = db.scalar(
        select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.organization_id == organization_id,
        )
    )
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")

    controls = _load_controls(db, organization_id, assessment_id, result.control_ids)

    if source_turn_ids is not None:
        trace_record = record_interview_trace(
            db, trace, source_turn_ids, record_id=trace_record_id
        )
    else:
        trace_record = record_trace(db, trace, record_id=trace_record_id)
    rows = []
    for control in controls:
        # _load_controls locks each control row, serializing version assignment
        # against both other agent runs and expert reviews for this control.
        previous = db.scalar(
            select(ControlResult)
            .where(
                ControlResult.organization_id == organization_id,
                ControlResult.assessment_id == assessment_id,
                ControlResult.assessment_control_id == control.id,
            )
            .order_by(ControlResult.version_no.desc())
            .limit(1)
        )
        rows.append(
            ControlResult(
                organization_id=organization_id,
                assessment_id=assessment_id,
                assessment_control_id=control.id,
                version_no=(previous.version_no + 1) if previous is not None else 1,
                based_on_result_id=previous.id if previous is not None else None,
                author_actor="agent",
                control_status=result.status,
                explanation=result.explanation,
                justification=result.justification,
                not_assessed_reason=result.not_assessed_reason,
                confidence=result.confidence,
                requires_human_review=result.requires_human_review,
                evidence_pending=result.evidence_pending,
                evidence_refs=[],
                trace_id=trace_record.id,
            )
        )
    db.add_all(rows)
    db.flush()
    return rows


def _check_trace(
    organization_id: UUID, assessment_id: UUID, result: AgentControlResult, trace: DecisionTrace
) -> None:
    """The trace must be the agent's status decision that explains this result."""
    if trace.decision_type != "status_assessed" or trace.actor_type != "agent":
        problem = "The trace must be an agent status_assessed decision."
    elif trace.organization_id != organization_id or trace.assessment_id != assessment_id:
        problem = "The trace belongs to another organization or assessment."
    elif trace.output.get("status") != result.status or sorted(trace.control_ids) != sorted(result.control_ids):
        problem = "The trace does not record this result."
    else:
        return
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=problem)


def _load_controls(
    db: Session, organization_id: UUID, assessment_id: UUID, control_ids: list[str]
) -> list[AssessmentControl]:
    """The assessment's controls for these codes, in the same order, locked until the caller commits."""
    controls = db.scalars(
        select(AssessmentControl)
        .where(
            AssessmentControl.organization_id == organization_id,
            AssessmentControl.assessment_id == assessment_id,
            AssessmentControl.control_code.in_(control_ids),
        )
        .order_by(AssessmentControl.id)
        .with_for_update()
    ).all()
    by_code = {control.control_code: control for control in controls}

    missing = [code for code in control_ids if code not in by_code]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Controls not in this assessment: {', '.join(missing)}.",
        )

    out_of_scope = [code for code in control_ids if not by_code[code].in_scope]
    if out_of_scope:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Controls outside the assessment scope: {', '.join(out_of_scope)}.",
        )

    # Re-assessment behavior is not decided yet. Refuse a new agent result when
    # any version already exists, so a rerun cannot supersede an expert-reviewed result.
    already_assessed = db.scalars(
        select(AssessmentControl.control_code)
        .join(
            ControlResult,
            (ControlResult.assessment_control_id == AssessmentControl.id)
            & (ControlResult.organization_id == AssessmentControl.organization_id)
            & (ControlResult.assessment_id == AssessmentControl.assessment_id),
        )
        .where(
            AssessmentControl.organization_id == organization_id,
            AssessmentControl.assessment_id == assessment_id,
            AssessmentControl.id.in_([control.id for control in controls]),
        )
    ).all()
    if already_assessed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Controls that already have a result: "
                f"{', '.join(sorted(set(already_assessed)))}."
            ),
        )

    return [by_code[code] for code in control_ids]
