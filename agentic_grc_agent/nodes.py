"""Interview steps. Each method is a LangGraph node: it receives the state and
returns only the keys it changes. They are plain functions, so they can be
unit-tested without LangGraph."""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, TypedDict

from . import prompts
from .fallback import heuristic_interpret
from .llm import LLM, LLMError
from .rules import decide_next_step
from .schemas import (
    Action,
    AnswerInterpretation,
    Clarification,
    ControlResult,
    FollowUpQuestion,
    KnowledgeBase,
    Missing,
    NextStep,
    Question,
)
from .trace import DecisionTrace, TraceRecorder, TraceSource


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class InterviewState(TypedDict, total=False):
    organization_id: str
    assessment_id: str
    question_codes: list[str]
    current_index: int
    follow_ups_used: int
    pending_message: str  # what the agent says next to the participant
    turns: Annotated[list[dict], operator.add]  # full transcript, append-only
    last_interpretation: dict
    last_step: dict
    results: Annotated[dict, _merge]  # question_code -> ControlResult dump


def initial_state(organization_id: str, assessment_id: str, question_codes: list[str]) -> InterviewState:
    return {
        "organization_id": organization_id,
        "assessment_id": assessment_id,
        "question_codes": question_codes,
        "current_index": 0,
        "follow_ups_used": 0,
        "turns": [],
        "results": {},
    }


@dataclass
class Deps:
    llm: LLM
    kb: KnowledgeBase
    tracer: TraceRecorder
    max_follow_ups: int = 3


class InterviewNodes:
    def __init__(self, deps: Deps):
        self.d = deps

    # ------------------------------------------------------------- helpers
    def _question(self, s: InterviewState) -> Question:
        return self.d.kb.get(s["question_codes"][s["current_index"]])

    @staticmethod
    def _turns_for(s: InterviewState, code: str) -> list[dict]:
        return [t for t in s.get("turns", []) if t["question_code"] == code]

    @staticmethod
    def _turn(s: InterviewState, code: str, speaker: str, turn_type: str, content: str) -> dict:
        return {
            "seq": len(s.get("turns", [])) + 1,
            "question_code": code,
            "speaker": speaker,
            "turn_type": turn_type,
            "content": content,
        }

    def _trace(self, s: InterviewState, q: Question, **fields) -> None:
        self.d.tracer.record(
            DecisionTrace(
                organization_id=s["organization_id"],
                assessment_id=s["assessment_id"],
                control_ids=[m.node_code for m in q.mappings],
                module=q.module,
                kb_version=self.d.kb.kb_version,
                **fields,
            )
        )

    def _sources(self, s: InterviewState, code: str) -> list[TraceSource]:
        return [
            TraceSource(type="interview_turn", ref=f"turn:{t['seq']}", excerpt=t["content"][:300])
            for t in self._turns_for(s, code)
            if t["speaker"] == "participant"
        ]

    # --------------------------------------------------------------- nodes
    def ask_question(self, s: InterviewState) -> dict:
        q = self._question(s)
        prefix = "Thank you. Let's move on to the next question.\n\n" if s["current_index"] > 0 else ""
        text = prefix + q.text
        return {
            "pending_message": text,
            "follow_ups_used": 0,
            "turns": [self._turn(s, q.code, "agent", "question", text)],
        }

    def record_answer(self, s: InterviewState, answer: str) -> dict:
        q = self._question(s)
        return {"turns": [self._turn(s, q.code, "participant", "answer", answer)]}

    def interpret(self, s: InterviewState) -> dict:
        q = self._question(s)
        turns = self._turns_for(s, q.code)
        system, user = prompts.interpret(q, turns)
        meta, fallback = None, False
        try:
            interp, meta = self.d.llm.structured(
                prompt_id=prompts.INTERPRET_ID, prompt_version=prompts.INTERPRET_VERSION,
                system=system, user=user, schema=AnswerInterpretation,
            )
        except LLMError as e:
            interp, fallback = heuristic_interpret(turns[-1]["content"]), True
            interp.rationale += f" ({e})"

        step = decide_next_step(interp, s.get("follow_ups_used", 0), self.d.max_follow_ups)
        self._trace(
            s, q,
            decision_type="answer_interpreted",
            sources=self._sources(s, q.code),
            model_name=meta.model_name if meta else None,
            prompt_id=meta.prompt_id if meta else "rule:keyword_fallback",
            prompt_version=meta.prompt_version if meta else "0.1.0",
            output={"interpretation": interp.model_dump(mode="json"), "next_step": step.model_dump(mode="json")},
            rationale=f"{interp.rationale} → {step.reason} [{step.rule_id}]",
            confidence=interp.confidence,
            requires_human_review=step.requires_human_review,
            latency_ms=meta.latency_ms if meta else None,
            fallback_used=fallback,
        )
        return {"last_interpretation": interp.model_dump(mode="json"), "last_step": step.model_dump(mode="json")}

    def clarify(self, s: InterviewState) -> dict:
        q = self._question(s)
        system, user = prompts.clarify(q, self._turns_for(s, q.code)[-1]["content"])
        try:
            out, _ = self.d.llm.structured(
                prompt_id=prompts.CLARIFY_ID, prompt_version=prompts.CLARIFY_VERSION,
                system=system, user=user, schema=Clarification,
            )
            text = out.explanation.strip() or q.clarification
        except LLMError:
            text = q.clarification
        text = f"{text}\n\n{q.text}"
        return {"pending_message": text, "turns": [self._turn(s, q.code, "agent", "clarification", text)]}

    def follow_up(self, s: InterviewState) -> dict:
        q = self._question(s)
        step = NextStep.model_validate(s["last_step"])
        missing = step.missing or Missing.redirect
        quote = s["last_interpretation"].get("key_quote") or self._turns_for(s, q.code)[-1]["content"][:80]
        system, user = prompts.follow_up(q, self._turns_for(s, q.code), quote, missing)
        try:
            out, _ = self.d.llm.structured(
                prompt_id=prompts.FOLLOW_UP_ID, prompt_version=prompts.FOLLOW_UP_VERSION,
                system=system, user=user, schema=FollowUpQuestion,
            )
            text = out.question.strip()
            if not text.endswith("?") or len(text) > 400:
                raise LLMError("follow-up is not a single short question")
        except LLMError:
            text = prompts.FALLBACK_FOLLOW_UPS[missing].format(quote=quote, question=q.text)

        if missing is Missing.evidence:
            self._trace(
                s, q, decision_type="evidence_requested", sources=self._sources(s, q.code),
                prompt_id=step.rule_id, prompt_version="0.1.0",
                output={"request": text, "evidence_examples": q.evidence_examples},
                rationale=step.reason,
            )
        return {
            "pending_message": text,
            "follow_ups_used": s.get("follow_ups_used", 0) + 1,
            "turns": [self._turn(s, q.code, "agent", "follow_up", text)],
        }

    def close_control(self, s: InterviewState) -> dict:
        q = self._question(s)
        step = NextStep.model_validate(s["last_step"])
        interp = AnswerInterpretation.model_validate(s["last_interpretation"])
        sources = self._sources(s, q.code)
        result = ControlResult(
            question_code=q.code,
            status=step.status,
            reason=step.reason,
            summary=interp.summary,
            follow_ups_used=s.get("follow_ups_used", 0),
            requires_human_review=step.requires_human_review,
            evidence_pending=step.status.value in ("implemented", "partially_implemented"),
            supporting_turns=[int(src.ref.split(":")[1]) for src in sources],
        )
        self._trace(
            s, q, decision_type="status_assessed", sources=sources,
            prompt_id=step.rule_id, prompt_version="0.1.0",
            output=result.model_dump(mode="json"), rationale=step.reason,
            confidence=interp.confidence, requires_human_review=step.requires_human_review,
        )
        return {"results": {q.code: result.model_dump(mode="json")}, "current_index": s["current_index"] + 1}

    # -------------------------------------------------------------- routes
    @staticmethod
    def route_after_interpret(s: InterviewState) -> str:
        return Action(s["last_step"]["action"]).value  # "clarify" | "follow_up" | "close"

    @staticmethod
    def route_after_close(s: InterviewState) -> str:
        return "next" if s["current_index"] < len(s["question_codes"]) else "done"
