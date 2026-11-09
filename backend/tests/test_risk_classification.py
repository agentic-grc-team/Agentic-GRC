"""Risk classification and ordering of gaps (HU-17). Pure unit tests, no database."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.decision_trace import TraceSource
from app.services.assessment_scope import KB_SCOPES
from app.services.risk_classification import (
    CONTROL_RULES,
    PRIORITY_ORDER,
    RISK_SEVERITIES,
    RISKS_WITHOUT_SEVERITY,
    RULE_ID,
    RULE_VERSION,
    SEVERITY_ORDER,
    ControlRule,
    GapClassification,
    build_classification_trace,
    classify_gap,
    order_gaps,
)


def make_gap(code, status="not_implemented", priority="High", risks=(("Unauthorized access", "Extreme"),)):
    return GapClassification(
        control_code=code,
        control_status=status,
        priority=priority,
        risks=risks,
        reason="Test rule.",
    )


# --- The rules themselves -------------------------------------------------------------------


def test_every_control_in_the_kb_scope_has_a_rule():
    in_scope = {code for codes in KB_SCOPES.values() for code in codes}

    assert set(CONTROL_RULES) == in_scope


def test_risk_severities_are_the_ones_from_aligo_materials():
    assert RISK_SEVERITIES == {
        "Unauthorized access": "Extreme",
        "System compromise": "Extreme",
        "Privilege escalation": "High",
        "Improper assignment of privileged functions": "High",
    }
    assert not set(RISK_SEVERITIES) & set(RISKS_WITHOUT_SEVERITY)


def test_every_rule_uses_aligo_values_and_only_risks_with_a_known_severity():
    for code, rule in CONTROL_RULES.items():
        assert rule.priority in PRIORITY_ORDER, code
        assert rule.risks, code
        assert len(rule.risks) == len(set(rule.risks)), code
        assert set(rule.risks) <= set(RISK_SEVERITIES), code
        assert rule.reason.strip(), code
    assert set(RISK_SEVERITIES.values()) <= set(SEVERITY_ORDER)


# --- classify_gap ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["implemented", "not_applicable", "not_assessed"])
def test_a_control_that_is_not_a_gap_gets_no_classification(status):
    assert classify_gap("PR.AA-05", status) is None


def test_a_gap_gets_the_control_priority_and_its_risks_most_severe_first():
    gap = classify_gap("PR.AA-05", "partially_implemented")

    assert gap.priority == "High"
    assert gap.risks == (
        ("Unauthorized access", "Extreme"),
        ("Privilege escalation", "High"),
        ("Improper assignment of privileged functions", "High"),
    )
    assert gap.worst_severity == "Extreme"


def test_risks_are_sorted_by_severity_whatever_order_the_rule_lists_them(monkeypatch):
    monkeypatch.setitem(
        CONTROL_RULES,
        "PR.AA-05",
        ControlRule(priority="High", risks=("Privilege escalation", "Unauthorized access"), reason="Test rule."),
    )

    gap = classify_gap("PR.AA-05", "not_implemented")

    assert gap.risks == (("Unauthorized access", "Extreme"), ("Privilege escalation", "High"))


def test_priority_does_not_depend_on_the_status():
    partial = classify_gap("PR.AA-03", "partially_implemented")
    missing = classify_gap("PR.AA-03", "not_implemented")

    assert partial.priority == missing.priority
    assert partial.risks == missing.risks


def test_a_control_without_a_rule_is_refused_instead_of_given_a_priority():
    with pytest.raises(ValueError, match="No risk classification rule for control DE.CM-01"):
        classify_gap("DE.CM-01", "not_implemented")


# --- order_gaps -----------------------------------------------------------------------------


def test_gaps_are_ordered_by_priority_first():
    low = make_gap("PR.AA-01", priority="Low")
    critical = make_gap("PR.AA-03", priority="Critical")
    medium = make_gap("PR.AA-05", priority="Medium")

    assert order_gaps([low, medium, critical]) == [critical, medium, low]


def test_equal_priority_is_ordered_by_the_most_severe_risk():
    high_risk = make_gap("PR.AA-01", risks=(("Privilege escalation", "High"),))
    extreme_risk = make_gap("PR.AA-05", risks=(("Unauthorized access", "Extreme"),))

    assert order_gaps([high_risk, extreme_risk]) == [extreme_risk, high_risk]


def test_equal_priority_and_risk_puts_not_implemented_first_then_control_code():
    partial = make_gap("PR.AA-01", status="partially_implemented")
    missing_b = make_gap("PR.AA-05")
    missing_a = make_gap("PR.AA-03")

    assert order_gaps([partial, missing_b, missing_a]) == [missing_a, missing_b, partial]


def test_demo_controls_are_ordered_with_the_current_rules():
    gaps = [
        classify_gap("PR.AA-05", "partially_implemented"),
        classify_gap("PR.AA-03", "not_implemented"),
        classify_gap("PR.AA-01", "not_implemented"),
    ]

    ordered = order_gaps(gaps)

    assert [gap.control_code for gap in ordered] == ["PR.AA-01", "PR.AA-03", "PR.AA-05"]


def test_no_gaps_give_an_empty_list():
    assert order_gaps([]) == []


# --- Decision trace -------------------------------------------------------------------------


def test_classification_trace_is_a_valid_rule_decision():
    gap = classify_gap("PR.AA-03", "not_implemented")
    source = TraceSource(type="interview_turn", ref=f"interview_turn:{uuid4()}")

    trace = build_classification_trace(uuid4(), uuid4(), gap, "demo-0.2", [source])

    assert trace.decision_type == "finding_generated"
    assert trace.prompt_id == RULE_ID
    assert trace.prompt_version == RULE_VERSION
    assert trace.model_name is None
    assert trace.control_ids == ["PR.AA-03"]
    assert trace.sources == [source]
    assert trace.output["priority"] == "High"
    assert trace.output["risks"] == [
        {"name": "Unauthorized access", "severity": "Extreme"},
        {"name": "System compromise", "severity": "Extreme"},
    ]
    assert trace.output["rules_provisional"] is True
    assert trace.rationale.startswith("PR.AA-03 is High:")


def test_classification_trace_without_a_source_is_rejected():
    gap = classify_gap("PR.AA-03", "not_implemented")

    with pytest.raises(ValidationError, match="must cite at least one source"):
        build_classification_trace(uuid4(), uuid4(), gap, "demo-0.2", [])
