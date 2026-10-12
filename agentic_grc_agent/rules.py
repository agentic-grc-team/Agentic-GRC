"""Deterministic interview rules (HU-05, HU-06, HU-08).

The LLM interprets; this module decides. Keeping the decision here makes it
testable, repeatable and easy to explain in a trace (each branch has a rule_id).
"""

from __future__ import annotations

from .schemas import (
    Action,
    AnswerCategory,
    AnswerInterpretation,
    ControlStatus,
    Intent,
    Missing,
    NextStep,
    Specificity,
)

LOW_CONFIDENCE = 0.5


def decide_next_step(
    interp: AnswerInterpretation, follow_ups_used: int, max_follow_ups: int
) -> NextStep:
    can_follow_up = follow_ups_used < max_follow_ups
    step = _decide(interp, can_follow_up)

    # A closing decision built on a shaky interpretation goes to a human.
    if step.action is Action.close and interp.confidence < LOW_CONFIDENCE:
        step.requires_human_review = True
        step.reason += " Low-confidence interpretation."
    return step


def _close(status: ControlStatus, reason: str, rule_id: str, review: bool = False) -> NextStep:
    return NextStep(
        action=Action.close, status=status, reason=reason, rule_id=rule_id, requires_human_review=review
    )


def _ask(missing: Missing, reason: str, rule_id: str) -> NextStep:
    return NextStep(action=Action.follow_up, missing=missing, reason=reason, rule_id=rule_id)


def _decide(i: AnswerInterpretation, can_follow_up: bool) -> NextStep:
    # Clarification does not count as a follow-up and never closes the control (HU-05).
    if i.intent is Intent.clarification_request:
        return NextStep(action=Action.clarify, reason="The participant asked what the question means.", rule_id="rule:clarify")

    if i.intent is Intent.off_topic:
        if can_follow_up:
            return _ask(Missing.redirect, "Off-topic answer.", "rule:off_topic_redirect")
        return _close(ControlStatus.not_assessed, "No relevant answer after the maximum number of follow-ups.",
                      "rule:off_topic_limit", review=True)

    c, detailed = i.category, i.specificity is Specificity.detailed

    # Total absence: no unnecessary follow-up (HU-06 criterion 2).
    if c is AnswerCategory.no:
        return _close(ControlStatus.not_implemented, "The participant states the control does not exist.", "rule:no")

    if c is AnswerCategory.yes:
        if detailed and i.mentions_scope:
            return _close(ControlStatus.implemented,
                          "Affirmative answer with scope described; evidence still to be validated.", "rule:yes_detailed")
        if can_follow_up:
            missing = Missing.evidence if i.mentions_scope else Missing.scope
            return _ask(missing, "Affirmative answer without enough detail.", f"rule:yes_vague_ask_{missing.value}")
        # An unsupported "yes" is an attestation, not proof: do not mark it compliant.
        return _close(ControlStatus.not_assessed, "Affirmative answer with no verifiable detail after the maximum number of follow-ups.",
                      "rule:yes_vague_limit", review=True)

    if c is AnswerCategory.partial:
        if detailed:
            return _close(ControlStatus.partially_implemented, "The participant describes what is missing.", "rule:partial_detailed")
        if can_follow_up:
            return _ask(Missing.gap, "Partial answer without stating the gap.", "rule:partial_ask_gap")
        return _close(ControlStatus.partially_implemented, "Partial implementation; the gap was not described.",
                      "rule:partial_limit", review=True)

    if c is AnswerCategory.not_applicable:
        # HU-08: not applicable needs a written justification.
        if detailed:
            return _close(ControlStatus.not_applicable, "Not applicable, with a justification.", "rule:na_justified")
        if can_follow_up:
            return _ask(Missing.justification, "Declared not applicable without a justification.", "rule:na_ask_justification")
        return _close(ControlStatus.not_assessed, "Declared not applicable without a justification.", "rule:na_limit", review=True)

    # unsure
    if can_follow_up:
        return _ask(Missing.knowledge_owner, "The participant does not know the answer.", "rule:unsure_ask_owner")
    return _close(ControlStatus.not_assessed, "Nobody in the session could answer.", "rule:unsure_limit")
