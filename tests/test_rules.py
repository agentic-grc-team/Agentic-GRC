from pathlib import Path

import pytest
import yaml

from agentic_grc_agent.rules import decide_next_step
from agentic_grc_agent.schemas import (
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


def test_detailed_yes_with_scope_is_implemented():
    step = decide_next_step(interp(category="yes", specificity="detailed", scope=True), 0, 3)
    assert step.status is ControlStatus.implemented and not step.requires_human_review


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


def test_low_confidence_close_goes_to_human():
    step = decide_next_step(interp(category="no", confidence=0.3), 0, 3)
    assert step.requires_human_review


def test_same_input_same_decision():
    i = interp(category="partial", specificity="detailed")
    assert decide_next_step(i, 1, 3) == decide_next_step(i, 1, 3)


CASES = yaml.safe_load((Path(__file__).parents[1] / "evals" / "interpret_cases.yaml").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_labels_agree_with_rules(case, kb):
    """A label set that the rules would route differently is a labelling (or rules) bug."""
    kb.get(case["question"])  # question exists
    e = case["expected"]
    detailed = e.get("specificity", "detailed") == "detailed"
    i = interp(intent=e["intent"], category=e.get("category", "unsure"),
               specificity="detailed" if detailed else "vague", scope=detailed)
    assert decide_next_step(i, 0, 3).action.value == e["action"]
