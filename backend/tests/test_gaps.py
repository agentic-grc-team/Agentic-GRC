"""Gap list of an assessment (HU-17). Pure unit tests on the service, no database."""

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.report import (
    AssessmentInfo,
    ControlInScope,
    OrganizationInfo,
    ReportInput,
    ResultReview,
    ResultVersion,
)
from app.services.gaps import build_gap_list
from app.services.risk_classification import (
    CONTROL_RULES,
    RULE_ID,
    RULE_VERSION,
    ControlRule,
)

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
TITLES = {
    "PR.AA-01": "Identities managed",
    "PR.AA-03": "Users authenticated",
    "PR.AA-05": "Access permissions managed",
}


def consultant_version(status, version_no=1, **changes):
    fields = {
        "version_no": version_no,
        "author_actor": "aligo_consultant",
        "author_name": "Aligo consultant",
        "control_status": status,
        "explanation": f"Consultant set {status}.",
        "created_at": NOW,
    }
    if status == "not_assessed":
        fields["not_assessed_reason"] = "Nobody could answer."
    if status == "not_applicable":
        fields["justification"] = "Out of scope."
    fields.update(changes)
    return ResultVersion(**fields)


def agent_version(status, review_outcome=None, version_no=1):
    review = None
    if review_outcome:
        review = ResultReview(
            outcome=review_outcome, reviewer_name="Aligo consultant", reviewed_at=NOW
        )
    return ResultVersion(
        version_no=version_no,
        author_actor="agent",
        control_status=status,
        explanation=f"Agent assessed {status}.",
        created_at=NOW,
        review=review,
    )


def report_input(**versions_by_code):
    return ReportInput(
        organization=OrganizationInfo(
            id=uuid4(), name="Org", sector="Other", size="Unknown"
        ),
        assessment=AssessmentInfo(
            id=uuid4(), title="Q4", kb_version="demo-0.2", status="in_progress"
        ),
        controls=[
            ControlInScope(code=code, title=TITLES.get(code, code), versions=versions)
            for code, versions in versions_by_code.items()
        ],
    )


def codes(gap_list):
    return [gap.control_code for gap in gap_list.gaps]


def test_only_final_partially_or_not_implemented_results_are_gaps():
    data = report_input(
        **{
            "PR.AA-01": [consultant_version("implemented")],
            "PR.AA-03": [consultant_version("not_assessed")],
            "PR.AA-05": [consultant_version("partially_implemented")],
        }
    )

    gap_list = build_gap_list(data, NOW)

    assert codes(gap_list) == ["PR.AA-05"]


def test_an_unreviewed_agent_draft_is_not_a_gap_but_counts_as_pending():
    data = report_input(
        **{
            "PR.AA-01": [agent_version("not_implemented")],
            "PR.AA-03": [agent_version("not_implemented", review_outcome="accepted")],
        }
    )

    gap_list = build_gap_list(data, NOW)

    assert codes(gap_list) == ["PR.AA-03"]
    assert gap_list.gaps[0].basis == "accepted_agent_result"
    assert gap_list.pending_controls == 1


def test_the_latest_version_decides_and_is_cited():
    # The agent said not implemented, the consultant's version 2 says implemented: no gap.
    fixed = report_input(
        **{
            "PR.AA-03": [
                agent_version("not_implemented", "modified"),
                consultant_version("implemented", 2),
            ]
        }
    )
    assert build_gap_list(fixed, NOW).gaps == []

    # The other way round: the gap cites version 2, the one it is based on.
    found = report_input(
        **{
            "PR.AA-03": [
                agent_version("implemented", "modified"),
                consultant_version("not_implemented", 2),
            ]
        }
    )
    (gap,) = build_gap_list(found, NOW).gaps
    assert gap.result_version == 2
    assert gap.basis == "consultant_version"


def test_gaps_are_ordered_by_criticality_and_carry_the_classification():
    data = report_input(
        **{
            "PR.AA-05": [consultant_version("partially_implemented")],
            "PR.AA-03": [consultant_version("not_implemented")],
            "PR.AA-01": [consultant_version("partially_implemented")],
        }
    )

    gap_list = build_gap_list(data, NOW)

    # Same priority and worst risk for all three, so not implemented first, then by control code.
    assert codes(gap_list) == ["PR.AA-03", "PR.AA-01", "PR.AA-05"]
    first = gap_list.gaps[0]
    assert first.classified is True
    assert first.priority == "High"
    assert [(risk.name, risk.severity) for risk in first.risks] == [
        ("Unauthorized access", "Extreme"),
        ("System compromise", "Extreme"),
    ]
    assert first.reason == CONTROL_RULES["PR.AA-03"].reason
    assert (gap_list.rules_id, gap_list.rules_version, gap_list.rules_provisional) == (
        RULE_ID,
        RULE_VERSION,
        True,
    )


def test_priority_comes_before_status_in_the_order(monkeypatch):
    monkeypatch.setitem(
        CONTROL_RULES,
        "PR.AA-05",
        ControlRule(
            priority="Critical", risks=("Unauthorized access",), reason="Test rule."
        ),
    )
    data = report_input(
        **{
            "PR.AA-03": [consultant_version("not_implemented")],
            "PR.AA-05": [consultant_version("partially_implemented")],
        }
    )

    assert codes(build_gap_list(data, NOW)) == ["PR.AA-05", "PR.AA-03"]


def test_a_control_without_a_rule_is_listed_as_not_classified_after_the_others(
    monkeypatch,
):
    monkeypatch.delitem(CONTROL_RULES, "PR.AA-01")
    data = report_input(
        **{
            "PR.AA-01": [consultant_version("not_implemented")],
            "PR.AA-05": [consultant_version("partially_implemented")],
        }
    )

    gap_list = build_gap_list(data, NOW)

    assert codes(gap_list) == ["PR.AA-05", "PR.AA-01"]
    unclassified = gap_list.gaps[1]
    assert unclassified.classified is False
    assert unclassified.priority is None
    assert unclassified.risks == []
    assert unclassified.reason is None


def test_no_results_give_no_gaps():
    gap_list = build_gap_list(report_input(**{"PR.AA-01": [], "PR.AA-03": []}), NOW)

    assert gap_list.gaps == []
    assert gap_list.pending_controls == 2
