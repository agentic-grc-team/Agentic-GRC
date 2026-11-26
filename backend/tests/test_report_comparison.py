"""HU-24 (AGRC-144): compare an assessment with an earlier completed one of the same organization."""

import json
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.main import app
from app.schemas.report import AssessmentInfo, ComparisonCandidate
from app.services.reports.builder import build_report_view
from app.services.reports.comparison import build_comparison, classify_change
from app.services.reports.source import get_report_source
from tests.test_report_compliance import _final
from tests.test_reports import (
    FIXED_DT,
    KNOWN_ASSESSMENT_ID,
    MEMBER_ORG_ID,
    NON_MEMBER_ORG_ID,
    client,
    extract_pdf_text,
    isolate_dependency_overrides,
    make_test_report_input,
)

PREVIOUS_ID = UUID("66666666-6666-4666-8666-666666666666")
OTHER_ID = UUID("77777777-7777-4777-8777-777777777777")
COMPLETED_AT = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


def _previous_input(**assessment_changes):
    data = make_test_report_input(
        controls=[
            _final("PR.AA-01", "not_implemented"),
            _final("PR.AA-02", "partially_implemented"),
            _final("PR.AA-03", "implemented"),
            _final("PR.AA-04", "implemented"),  # removed from the current scope
        ]
    )
    fields = {
        "id": PREVIOUS_ID,
        "title": "First access assessment",
        "framework": "NIST CSF 2.0",
        "kb_version": "kb-1.0",
        "status": "completed",
        "started_at": FIXED_DT,
        "completed_at": COMPLETED_AT,
    }
    fields.update(assessment_changes)
    data.assessment = AssessmentInfo(**fields)
    return data


def _current_input():
    data = make_test_report_input(
        controls=[
            _final("PR.AA-01", "implemented"),  # improved
            _final("PR.AA-02", "not_implemented"),  # declined
            _final("PR.AA-03", "implemented"),  # unchanged
            _final("PR.AA-05", "implemented"),  # added to the scope
        ]
    )
    data.assessment = data.assessment.model_copy(update={"status": "completed", "completed_at": FIXED_DT})
    return data


def _views(previous=None, current=None):
    return (
        build_report_view(current or _current_input(), FIXED_DT),
        build_report_view(previous or _previous_input(), FIXED_DT),
    )


# --- Pure comparison ---


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ("not_implemented", "implemented", "improved"),
        ("partially_implemented", "implemented", "improved"),
        ("implemented", "partially_implemented", "declined"),
        ("implemented", "implemented", "unchanged"),
        ("pending", "pending", "unchanged"),
        ("not_applicable", "implemented", "not_comparable"),
        ("pending", "implemented", "not_comparable"),
        ("not_assessed", "not_implemented", "not_comparable"),
    ],
)
def test_classify_change(previous, current, expected):
    assert classify_change(previous, current) == expected


def test_comparison_lists_status_changes_of_common_controls():
    comparison = build_comparison(*_views())
    changes = {item.code: item.change for item in comparison.controls}
    assert changes == {"PR.AA-01": "improved", "PR.AA-02": "declined", "PR.AA-03": "unchanged"}
    assert comparison.changed_controls == 2
    assert comparison.scope.added == ["PR.AA-05"]
    assert comparison.scope.removed == ["PR.AA-04"]
    assert comparison.scope.common == 3


def test_comparison_uses_the_same_compliance_rule_and_shows_the_change():
    comparison = build_comparison(*_views())
    # Previous: (2 + 0.5) / 4 = 62.5. Current: 3 / 4 = 75.0.
    assert comparison.previous.compliance.value_pct == 62.5
    assert comparison.current.compliance.value_pct == 75.0
    assert comparison.compliance_change_pct == 12.5


def test_comparison_warns_when_scope_or_versions_differ():
    previous = _previous_input(framework="NIST CSF 1.1", kb_version="kb-0.9")
    codes = {warning.code for warning in build_comparison(*_views(previous=previous)).warnings}
    assert {"framework_differs", "kb_version_differs", "scope_differs"} <= codes
    assert "current_not_completed" not in codes


def test_comparison_warns_when_the_current_assessment_is_not_completed():
    current = _current_input()
    current.assessment = current.assessment.model_copy(update={"status": "awaiting_review", "completed_at": None})
    codes = {warning.code for warning in build_comparison(*_views(current=current)).warnings}
    assert "current_not_completed" in codes


def test_comparison_has_no_change_when_a_figure_is_unavailable():
    current = make_test_report_input(controls=[_final("PR.AA-01", "implemented", accepted=False)])
    comparison = build_comparison(*_views(current=current))
    assert comparison.compliance_change_pct is None
    assert "compliance_unavailable" in {warning.code for warning in comparison.warnings}


# --- API ---


class TwoAssessmentsSource:
    def load(self, db, organization_id, assessment_id):
        if organization_id != MEMBER_ORG_ID:
            return None
        if assessment_id == KNOWN_ASSESSMENT_ID:
            return _current_input()
        if assessment_id == PREVIOUS_ID:
            return _previous_input()
        return None


@pytest.fixture
def two_assessments(monkeypatch):
    app.dependency_overrides[get_report_source] = lambda: TwoAssessmentsSource()
    seen = []

    def fake_candidates(db, organization_id, assessment_id):
        seen.append((organization_id, assessment_id))
        if organization_id != MEMBER_ORG_ID or assessment_id != KNOWN_ASSESSMENT_ID:
            return []
        return [
            ComparisonCandidate(
                id=PREVIOUS_ID,
                title="First access assessment",
                completed_at=COMPLETED_AT,
                framework="NIST CSF 2.0",
                kb_version="kb-1.0",
            )
        ]

    monkeypatch.setattr("app.api.v1.endpoints.reports.list_comparison_candidates", fake_candidates)
    return seen


BASE = f"/api/v1/organizations/{MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}"


def test_api_lists_comparison_candidates(two_assessments):
    response = client.get(f"{BASE}/comparison/candidates")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(PREVIOUS_ID)]


def test_api_candidates_for_non_member_return_404(two_assessments):
    response = client.get(
        f"/api/v1/organizations/{NON_MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}/comparison/candidates"
    )
    assert response.status_code == 404
    assert two_assessments == []  # no query ran for the other organization


def test_api_returns_the_comparison(two_assessments):
    response = client.get(f"{BASE}/comparison", params={"previous": str(PREVIOUS_ID)})
    assert response.status_code == 200
    body = response.json()
    assert body["previous"]["id"] == str(PREVIOUS_ID)
    assert body["compliance_change_pct"] == 12.5
    assert body["changed_controls"] == 2


def test_api_rejects_an_assessment_that_is_not_an_eligible_candidate(two_assessments):
    response = client.get(f"{BASE}/comparison", params={"previous": str(OTHER_ID)})
    assert response.status_code == 404


def test_api_comparison_for_non_member_returns_404(two_assessments):
    response = client.get(
        f"/api/v1/organizations/{NON_MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}/comparison",
        params={"previous": str(PREVIOUS_ID)},
    )
    assert response.status_code == 404


def test_api_comparison_requires_the_previous_id(two_assessments):
    assert client.get(f"{BASE}/comparison").status_code == 422


def test_json_export_includes_the_comparison_only_when_asked(two_assessments):
    plain = json.loads(client.get(f"{BASE}/report.json").text)
    assert plain["comparison"] is None

    compared = json.loads(client.get(f"{BASE}/report.json", params={"compare_with": str(PREVIOUS_ID)}).text)
    assert compared["export_version"] == "1.2"
    assert compared["comparison"]["previous"]["id"] == str(PREVIOUS_ID)
    assert compared["comparison"]["current"]["compliance"] == compared["report"]["summary"]["compliance"]


def test_pdf_export_with_comparison_has_the_comparison_section(two_assessments):
    response = client.get(f"{BASE}/report.pdf", params={"compare_with": str(PREVIOUS_ID)})
    assert response.status_code == 200
    text = extract_pdf_text(response.content)
    assert "7. Comparison with First access assessment" in text
    assert "+12.5 percentage points" in text
    assert "Improved" in text and "Declined" in text


def test_exports_reject_an_ineligible_comparison(two_assessments):
    response = client.get(f"{BASE}/report.pdf", params={"compare_with": str(OTHER_ID)})
    assert response.status_code == 404
