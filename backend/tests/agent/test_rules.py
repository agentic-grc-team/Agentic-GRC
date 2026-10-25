from pathlib import Path

import pytest
import yaml

from app.agent.rules import decide_next_step
from app.agent.schemas import (
    Action,
    AnswerCategory,
    AnswerInterpretation,
    ControlStatus,
    Intent,
    Missing,
    Specificity,
)


def interp(intent="answer", category="unsure", specificity="vague", scope=False, evidence=False, confidence=0.9):
    return AnswerInterpretation(
        intent=Intent(intent), category=AnswerCategory(category), specificity=Specificity(specificity),
        mentions_scope=scope, mentions_evidence=evidence, summary="s", rationale="r", confidence=confidence,
    )


def test_no_closes_without_follow_up():
    step = decide_next_step(interp(category="no"), 0, 3)
    assert step.action is Action.close and step.status is ControlStatus.not_implemented


def test_vague_yes_asks_for_scope_then_evidence():
    assert decide_next_step(interp(category="yes"), 0, 3).missing is Missing.scope
    assert decide_next_step(interp(category="yes", scope=True), 0, 3).missing is Missing.evidence


def test_detailed_yes_gets_one_evidence_request_then_closes():
    i = interp(category="yes", specificity="detailed", scope=True)
    first = decide_next_step(i, 0, 3)
    assert first.action is Action.follow_up and first.missing is Missing.evidence
    assert first.rule_id == "rule:yes_detailed_ask_evidence"
    # already asked: do not insist
    second = decide_next_step(i, 1, 3, evidence_asked=True)
    assert second.status is ControlStatus.implemented and not second.requires_human_review
    assert second.rule_id == "rule:yes_detailed"


def test_evidence_request_does_not_depend_on_the_model_flag():
    named = interp(category="yes", specificity="detailed", scope=True, evidence=True)
    assert decide_next_step(named, 0, 3).missing is Missing.evidence


def test_vague_yes_after_evidence_request_asks_for_detail_not_evidence_again():
    vague_with_scope = interp(category="yes", scope=True)
    assert decide_next_step(vague_with_scope, 0, 3).missing is Missing.evidence
    step = decide_next_step(vague_with_scope, 1, 3, evidence_asked=True)
    assert step.missing is Missing.detail and step.rule_id == "rule:yes_vague_ask_detail"


def test_detailed_yes_requests_evidence_even_when_no_follow_ups_left():
    step = decide_next_step(interp(category="yes", specificity="detailed", scope=True), 3, 3)
    assert step.action is Action.follow_up
    assert step.missing is Missing.evidence
    assert step.rule_id == "rule:yes_detailed_ask_evidence"


def test_vague_yes_at_limit_is_not_marked_compliant():
    step = decide_next_step(interp(category="yes"), 3, 3)
    assert step.action is Action.close
    assert step.status is ControlStatus.not_assessed and step.requires_human_review


def test_partial_at_limit_keeps_partial_with_review():
    step = decide_next_step(interp(category="partial"), 3, 3)
    assert step.status is ControlStatus.partially_implemented and step.requires_human_review


def test_not_applicable_requires_justification():
    assert decide_next_step(interp(category="not_applicable"), 0, 3).missing is Missing.justification
    ok = decide_next_step(interp(category="not_applicable", specificity="detailed"), 0, 3)
    assert ok.status is ControlStatus.not_applicable


def test_clarification_never_closes_even_at_limit():
    assert decide_next_step(interp(intent="clarification_request"), 3, 3).action is Action.clarify


def test_low_confidence_answer_requires_clarification_before_human_review():
    step = decide_next_step(interp(category="no", confidence=0.3), 0, 3)
    assert step.action is Action.clarify
    assert not step.requires_human_review

    unresolved = decide_next_step(
        interp(category="no", confidence=0.3), 0, 3, ambiguity_clarifications_used=1
    )
    assert unresolved.status is ControlStatus.not_assessed
    assert unresolved.requires_human_review


def test_same_input_same_decision():
    i = interp(category="partial", specificity="detailed")
    assert decide_next_step(i, 1, 3) == decide_next_step(i, 1, 3)


CASES = yaml.safe_load((Path(__file__).parents[2] / "evals" / "interpret_cases.yaml").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_labels_agree_with_rules(case, kb):
    """A label set that the rules would route differently is a labelling (or rules) bug."""
    kb.get(case["question"])  # question exists
    e = case["expected"]
    detailed = e.get("specificity", "detailed") == "detailed"
    i = interp(intent=e["intent"], category=e.get("category", "unsure"),
               specificity="detailed" if detailed else "vague", scope=detailed,
               evidence=e.get("mentions_evidence", False))
    step = decide_next_step(i, 0, 3, evidence_asked=case.get("evidence_asked", False))
    assert step.action.value == e["action"]
