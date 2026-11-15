"""Remediation recommendations for gaps (HU-18, part 1). Pure unit tests, no database."""

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agent.knowledge import load_kb
from app.schemas.decision_trace import TraceSource
from app.services.assessment_scope import KB_SCOPES
from app.services.remediation import (
    DEPENDENCIES,
    REMEDIATION_TEMPLATES,
    RULE_ID,
    RULE_VERSION,
    TIME_HORIZONS,
    build_remediation_trace,
    group_by_time_horizon,
    recommend_for_gaps,
    recommend_remediation,
)
from app.services.risk_classification import GapClassification, classify_gap

KB_PATH = Path(__file__).resolve().parents[1] / "app" / "agent" / "data" / "kb_demo.yaml"


def gap(code, status="not_implemented"):
    return classify_gap(code, status)


# --- The templates themselves ---------------------------------------------------------------


def test_every_control_in_the_kb_scope_has_a_template():
    in_scope = {code for codes in KB_SCOPES.values() for code in codes}

    assert set(REMEDIATION_TEMPLATES) == in_scope


def test_every_template_uses_aligo_values_and_has_both_sets_of_steps():
    for code, template in REMEDIATION_TEMPLATES.items():
        assert template.dependency in DEPENDENCIES, code
        assert template.time_horizon in TIME_HORIZONS, code
        for text in (
            template.statement,
            template.issue,
            template.requirement,
            template.task,
            template.task_description,
            template.basis,
        ):
            assert text.strip(), code
        assert len(template.how_to) >= 3, code
        assert len(template.partial_how_to) >= 3, code
        assert all(step.strip() for step in template.how_to + template.partial_how_to), code
        assert template.how_to != template.partial_how_to, code


def test_each_template_answers_the_kb_question_mapped_to_its_control():
    kb = load_kb(KB_PATH)
    questions = {question.code: question for question in kb.questions}

    for code, template in REMEDIATION_TEMPLATES.items():
        question = questions[template.question_code]
        assert code in [mapping.node_code for mapping in question.mappings], code
        # The proof that closes the gap is the evidence the interview asks for.
        assert list(template.evidence_to_close) == question.evidence_examples, code


# --- recommend_remediation ------------------------------------------------------------------


def test_a_not_implemented_gap_gets_the_full_steps():
    recommendation = recommend_remediation(gap("PR.AA-03", "not_implemented"))
    template = REMEDIATION_TEMPLATES["PR.AA-03"]

    assert recommendation.how_to == template.how_to
    assert recommendation.task == template.task
    assert recommendation.task_description == template.task_description
    assert recommendation.dependency == "Technology"
    assert recommendation.time_horizon == "Short term"


def test_a_partially_implemented_gap_starts_from_what_already_exists():
    recommendation = recommend_remediation(gap("PR.AA-03", "partially_implemented"))
    template = REMEDIATION_TEMPLATES["PR.AA-03"]

    assert recommendation.how_to == template.partial_how_to
    assert recommendation.task_description.startswith("Part of this is already in place.")
    assert recommendation.task == template.task


def test_priority_and_risks_come_unchanged_from_the_classification():
    classified = gap("PR.AA-05", "partially_implemented")

    recommendation = recommend_remediation(classified)

    assert recommendation.priority == classified.priority
    assert recommendation.risks == classified.risks


def test_the_justification_cites_the_status_question_task_and_priority_reason():
    classified = gap("PR.AA-01", "not_implemented")

    recommendation = recommend_remediation(classified)

    text = recommendation.justification
    assert text.startswith("PR.AA-01 was assessed as not implemented (question IAM-03).")
    assert REMEDIATION_TEMPLATES["PR.AA-01"].issue in text
    assert "Recommended: Define and enforce an offboarding procedure" in text
    assert f"Priority {classified.priority}: {classified.reason}" in text


def test_the_same_gap_always_gets_the_same_recommendation():
    assert recommend_remediation(gap("PR.AA-05")) == recommend_remediation(gap("PR.AA-05"))


def test_a_control_without_a_template_is_refused_instead_of_given_a_recommendation():
    unknown = GapClassification(
        control_code="DE.CM-01",
        control_status="not_implemented",
        priority="Medium",
        risks=(("Unauthorized access", "Extreme"),),
        reason="Test rule.",
    )

    with pytest.raises(ValueError, match="No remediation template for control DE.CM-01"):
        recommend_remediation(unknown)


def test_a_status_that_is_not_a_gap_is_refused():
    not_a_gap = GapClassification(
        control_code="PR.AA-03",
        control_status="implemented",
        priority="High",
        risks=(("Unauthorized access", "Extreme"),),
        reason="Test rule.",
    )

    with pytest.raises(ValueError, match="is not a gap"):
        recommend_remediation(not_a_gap)


# --- Ordering and roadmap buckets -----------------------------------------------------------


def test_recommendations_follow_the_hu17_order_of_the_gaps():
    gaps = [
        gap("PR.AA-05", "partially_implemented"),
        gap("PR.AA-03", "not_implemented"),
        gap("PR.AA-01", "not_implemented"),
    ]

    recommendations = recommend_for_gaps(gaps)

    assert [item.control_code for item in recommendations] == ["PR.AA-01", "PR.AA-03", "PR.AA-05"]


def test_no_gaps_give_no_recommendations():
    assert recommend_for_gaps([]) == []


def test_recommendations_are_grouped_by_time_horizon_keeping_their_order():
    recommendations = recommend_for_gaps(
        [gap("PR.AA-05"), gap("PR.AA-03"), gap("PR.AA-01")]
    )

    groups = group_by_time_horizon(recommendations)

    assert list(groups) == list(TIME_HORIZONS)
    assert [item.control_code for item in groups["Short term"]] == ["PR.AA-01", "PR.AA-03"]
    assert [item.control_code for item in groups["Mid term"]] == ["PR.AA-05"]
    assert groups["Long term"] == []


# --- Decision trace -------------------------------------------------------------------------


def test_remediation_trace_is_a_valid_rule_decision_that_needs_review():
    recommendation = recommend_remediation(gap("PR.AA-03", "partially_implemented"))
    source = TraceSource(type="interview_turn", ref=f"interview_turn:{uuid4()}")

    trace = build_remediation_trace(uuid4(), uuid4(), recommendation, "demo-0.2", [source])

    assert trace.decision_type == "finding_generated"
    assert trace.prompt_id == RULE_ID
    assert trace.prompt_version == RULE_VERSION
    assert trace.model_name is None
    assert trace.control_ids == ["PR.AA-03"]
    assert trace.sources == [source]
    assert trace.requires_human_review is True
    assert trace.rationale == recommendation.justification
    assert trace.output["kind"] == "remediation"
    assert trace.output["control_status"] == "partially_implemented"
    assert trace.output["how_to"] == list(REMEDIATION_TEMPLATES["PR.AA-03"].partial_how_to)
    assert trace.output["risks"] == [
        {"name": "Unauthorized access", "severity": "Extreme"},
        {"name": "System compromise", "severity": "Extreme"},
    ]
    assert trace.output["is_preliminary"] is True
    assert trace.output["rules_provisional"] is True


def test_remediation_trace_without_a_source_is_rejected():
    recommendation = recommend_remediation(gap("PR.AA-03"))

    with pytest.raises(ValidationError, match="must cite at least one source"):
        build_remediation_trace(uuid4(), uuid4(), recommendation, "demo-0.2", [])
