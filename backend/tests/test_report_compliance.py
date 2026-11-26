"""HU-23 (AGRC-132): one compliance figure for an assessment, the same in preview, PDF and JSON."""

import json

import pytest

from app.schemas.report import COMPLIANCE_DEFINITION, ControlInScope, ResultReview, ResultVersion
from app.services.reports.builder import build_report_view, compute_compliance
from app.services.reports.pdf import render_report_pdf
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


def _counts(implemented=0, partial=0, not_implemented=0, not_assessed=0) -> dict[str, int]:
    return {
        "implemented": implemented,
        "partially_implemented": partial,
        "not_implemented": not_implemented,
        "not_assessed": not_assessed,
    }


def _final(code: str, status: str, *, accepted: bool = True) -> ControlInScope:
    """A control whose only version is an agent result, accepted (final) or still unreviewed."""
    return ControlInScope(
        code=code,
        title=f"Control {code}",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status=status,
                explanation="Result.",
                justification="Out of scope for this organization." if status == "not_applicable" else None,
                not_assessed_reason="No participant could answer." if status == "not_assessed" else None,
                created_at=FIXED_DT,
                review=ResultReview(outcome="accepted", reviewer_name="Consultant", reviewed_at=FIXED_DT)
                if accepted
                else None,
            )
        ],
    )


# --- Calculation rule ---


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        (_counts(implemented=2), 100.0),
        (_counts(not_implemented=3), 0.0),
        (_counts(implemented=1, partial=1, not_implemented=1), 50.0),  # (1 + 0.5) / 3
        (_counts(implemented=2, partial=1), 83.3),  # 2.5 / 3, rounded to 1 decimal
        (_counts(partial=1), 50.0),
    ],
)
def test_compliance_rule(counts, expected):
    compliance = compute_compliance(counts, exclusions=0, pending=0)
    assert compliance.available is True
    assert compliance.value_pct == expected


def test_compliance_reports_numerator_and_denominator():
    compliance = compute_compliance(_counts(implemented=2, partial=1, not_implemented=1), 0, 0)
    assert compliance.numerator == 2.5
    assert compliance.denominator == 4
    assert compliance.definition == COMPLIANCE_DEFINITION


def test_not_applicable_not_assessed_and_pending_stay_outside_the_figure():
    compliance = compute_compliance(
        _counts(implemented=1, not_implemented=1, not_assessed=4), exclusions=3, pending=5
    )
    assert compliance.value_pct == 50.0
    assert compliance.denominator == 2
    assert compliance.excluded_not_applicable == 3
    assert compliance.not_assessed == 4
    assert compliance.pending == 5


@pytest.mark.parametrize(
    ("counts", "exclusions", "pending"),
    [
        (_counts(), 0, 0),  # nothing at all
        (_counts(), 0, 4),  # everything still pending review
        (_counts(not_assessed=2), 1, 0),  # only not assessed and not applicable
    ],
)
def test_compliance_is_unavailable_without_eligible_final_results(counts, exclusions, pending):
    compliance = compute_compliance(counts, exclusions, pending)
    assert compliance.available is False
    assert compliance.value_pct is None  # never shown as 0% or 100%
    assert compliance.denominator == 0


# --- Builder: only final reviewed results count ---


def test_builder_sets_compliance_from_final_results_only():
    data = make_test_report_input(
        controls=[
            _final("PR.AA-01", "implemented"),
            _final("PR.AA-02", "not_implemented"),
            _final("PR.AA-03", "implemented", accepted=False),  # pending review: outside the figure
            _final("PR.AA-04", "not_applicable"),
            _final("PR.AA-05", "not_assessed"),
        ]
    )
    compliance = build_report_view(data, FIXED_DT).summary.compliance
    assert compliance.value_pct == 50.0
    assert (compliance.implemented, compliance.not_implemented) == (1, 1)
    assert compliance.pending == 1
    assert compliance.excluded_not_applicable == 1
    assert compliance.not_assessed == 1


def test_builder_compliance_follows_a_consultant_version():
    """A consultant's final review that changes the status changes the figure."""
    control = _final("PR.AA-01", "not_implemented")
    control.versions.append(
        ResultVersion(
            version_no=2,
            author_actor="aligo_consultant",
            author_name="Consultant",
            control_status="implemented",
            explanation="MFA is enforced for every account.",
            created_at=FIXED_DT,
        )
    )
    compliance = build_report_view(make_test_report_input(controls=[control]), FIXED_DT).summary.compliance
    assert compliance.value_pct == 100.0


# --- PDF ---


def test_pdf_shows_the_compliance_figure_and_its_definition():
    data = make_test_report_input(controls=[_final("PR.AA-01", "implemented"), _final("PR.AA-02", "partially_implemented")])
    text = extract_pdf_text(render_report_pdf(build_report_view(data, FIXED_DT)))
    assert "Compliance 75.0%" in text
    assert "Partially implemented) / (Implemented" in text


def test_pdf_says_unavailable_instead_of_zero():
    data = make_test_report_input(controls=[_final("PR.AA-01", "implemented", accepted=False)])
    text = extract_pdf_text(render_report_pdf(build_report_view(data, FIXED_DT)))
    assert "Compliance Unavailable" in text
    assert "0.0%" not in text.split("Controls in scope")[0]


# --- API: same value in preview and JSON, members only ---


def test_preview_and_json_export_carry_the_same_compliance():
    base = f"/api/v1/organizations/{MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}"
    preview = client.get(f"{base}/report").json()["summary"]["compliance"]
    exported = json.loads(client.get(f"{base}/report.json").text)["report"]["summary"]["compliance"]
    assert preview == exported
    # Default fake data: one accepted Implemented result, one still pending review.
    assert preview["available"] is True
    assert preview["value_pct"] == 100.0
    assert preview["pending"] == 1


def test_non_member_cannot_read_the_compliance_figure():
    response = client.get(
        f"/api/v1/organizations/{NON_MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}/report"
    )
    assert response.status_code == 404
