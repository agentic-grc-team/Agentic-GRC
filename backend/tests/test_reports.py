from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID, uuid4

import pdfplumber
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.dependencies import get_db_session
from app.core.config import Settings
from app.main import app
from app.schemas.report import (
    AssessmentInfo,
    ControlInScope,
    EvidenceReference,
    OrganizationInfo,
    ReportInput,
    ResultReview,
    ResultVersion,
)
from app.security.auth import get_current_user
from app.services.reports.builder import build_report_view
from app.services.reports.pdf import render_report_pdf
from app.services.reports.source import (
    DEMO_ASSESSMENT_ID,
    CompositeReportSource,
    DbReportSource,
    DemoReportSource,
    get_report_source,
)

client = TestClient(app)

MEMBER_ORG_ID = UUID("11111111-1111-4111-8111-111111111111")
NON_MEMBER_ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
KNOWN_ASSESSMENT_ID = UUID("33333333-3333-4333-8333-333333333333")
UNKNOWN_ASSESSMENT_ID = UUID("44444444-4444-4444-8444-444444444444")
MEMBER_USER_ID = UUID("55555555-5555-4555-8555-555555555555")

FIXED_DT = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeUser:
    def __init__(self, id: UUID, is_platform_admin: bool = False):
        self.id = id
        self.is_platform_admin = is_platform_admin


def make_test_report_input(controls: list[ControlInScope] | None = None, is_demo_data: bool = False) -> ReportInput:
    if controls is None:
        controls = [
            ControlInScope(
                code="PR.AA-01",
                title="Identities and credentials",
                versions=[
                    ResultVersion(
                        version_no=1,
                        author_actor="agent",
                        control_status="implemented",
                        explanation="Centrally managed identities.",
                        created_at=FIXED_DT,
                        review=ResultReview(
                            outcome="accepted",
                            reviewer_name="Consultant Alice",
                            reviewed_at=FIXED_DT,
                            comment="Looks good.",
                        ),
                        evidence=[
                            EvidenceReference(
                                source_type="document_span",
                                reference="Policy.pdf",
                                excerpt="All users registered.",
                                nature="intent",
                            )
                        ],
                    )
                ],
            ),
            ControlInScope(
                code="PR.AA-05",
                title="Access permissions",
                versions=[
                    ResultVersion(
                        version_no=1,
                        author_actor="agent",
                        control_status="implemented",
                        explanation="Role-based access.",
                        created_at=FIXED_DT,
                        review=None,
                    )
                ],
            ),
        ]

    return ReportInput(
        organization=OrganizationInfo(
            id=MEMBER_ORG_ID,
            name="Acme Corp",
            sector="Financial services",
            size="51-250 employees",
        ),
        assessment=AssessmentInfo(
            id=KNOWN_ASSESSMENT_ID,
            title="Access Security Assessment",
            framework="NIST CSF 2.0",
            kb_version="kb-1.0",
            status="awaiting_review",
            started_at=FIXED_DT,
        ),
        controls=controls,
        is_demo_data=is_demo_data,
    )


class FakeReportSource:
    def load(self, db, organization_id: UUID, assessment_id: UUID) -> ReportInput | None:
        if assessment_id != KNOWN_ASSESSMENT_ID:
            return None
        return make_test_report_input()


def extract_pdf_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = " ".join((page.extract_text() or "") for page in pdf.pages)
    return " ".join(text.split())


@pytest.fixture(autouse=True)
def isolate_dependency_overrides(monkeypatch):
    saved_overrides = dict(app.dependency_overrides)

    default_user = FakeUser(id=MEMBER_USER_ID, is_platform_admin=False)
    app.dependency_overrides[get_current_user] = lambda: default_user
    app.dependency_overrides[get_db_session] = lambda: iter([None])
    app.dependency_overrides[get_report_source] = lambda: FakeReportSource()

    def fake_membership(db, organization_id, user_id):
        if organization_id == MEMBER_ORG_ID:
            return True
        return None

    monkeypatch.setattr("app.api.v1.endpoints.reports._active_membership", fake_membership)

    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved_overrides)


# --- 1. Schema Tests ---

def test_schema_not_applicable_without_justification_raises():
    with pytest.raises(ValidationError):
        ResultVersion(
            version_no=1,
            author_actor="aligo_consultant",
            author_name="Alice",
            control_status="not_applicable",
            explanation="Not relevant to our cloud.",
            justification=None,
            created_at=FIXED_DT,
        )


def test_schema_consultant_version_without_author_name_raises():
    with pytest.raises(ValidationError):
        ResultVersion(
            version_no=1,
            author_actor="aligo_consultant",
            author_name=None,
            control_status="implemented",
            explanation="Implemented fully.",
            created_at=FIXED_DT,
        )


def test_schema_invalid_control_code_raises():
    with pytest.raises(ValidationError):
        ControlInScope(code="PRAA03", title="Users authenticated")


def test_schema_control_with_duplicate_version_no_raises():
    with pytest.raises(ValidationError, match="duplicate version_no"):
        ControlInScope(
            code="PR.AA-01",
            title="Identities and credentials",
            versions=[
                ResultVersion(
                    version_no=2,
                    author_actor="agent",
                    control_status="implemented",
                    explanation="First version with version_no=2",
                    created_at=FIXED_DT,
                ),
                ResultVersion(
                    version_no=2,
                    author_actor="aligo_consultant",
                    author_name="Alice",
                    control_status="implemented",
                    explanation="Second version with version_no=2",
                    created_at=FIXED_DT,
                ),
            ],
        )


# --- 2. Builder Tests ---

def test_builder_agent_version_accepted_becomes_final_result():
    ctrl = ControlInScope(
        code="PR.AA-01",
        title="Identities and credentials",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation="Centrally managed identities.",
                created_at=FIXED_DT,
                review=ResultReview(
                    outcome="accepted",
                    reviewer_name="Reviewer Bob",
                    reviewed_at=FIXED_DT,
                ),
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 1
    res = view.results[0]
    assert res.code == "PR.AA-01"
    assert res.basis == "accepted_agent_result"
    assert res.reviewed_by == "Reviewer Bob"
    assert res.control_status == "implemented"


def test_builder_agent_v1_and_consultant_v2_highest_decides():
    ctrl = ControlInScope(
        code="PR.AA-03",
        title="Authentication",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation="Agent says implemented.",
                created_at=FIXED_DT,
                review=ResultReview(
                    outcome="modified",
                    reviewer_name="Consultant",
                    reviewed_at=FIXED_DT,
                ),
            ),
            ResultVersion(
                version_no=2,
                author_actor="aligo_consultant",
                author_name="Consultant Jane",
                control_status="partially_implemented",
                explanation="Consultant modified: MFA partial.",
                created_at=FIXED_DT,
            ),
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 1
    res = view.results[0]
    assert res.basis == "consultant_version"
    assert res.control_status == "partially_implemented"
    assert res.reviewed_by == "Consultant Jane"


def test_builder_agent_version_without_review_is_pending():
    ctrl = ControlInScope(
        code="PR.AA-05",
        title="Access permissions",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation="RBAC in place.",
                created_at=FIXED_DT,
                review=None,
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 0
    assert len(view.pending) == 1
    assert view.pending[0].reason == "awaiting_review"


def test_builder_agent_version_rejected_is_pending_rejected():
    ctrl = ControlInScope(
        code="ID.AM-01",
        title="Hardware inventories",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="not_implemented",
                explanation="No hardware inventory.",
                created_at=FIXED_DT,
                review=ResultReview(
                    outcome="rejected",
                    reviewer_name="Auditor Sam",
                    reviewed_at=FIXED_DT,
                ),
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 0
    assert len(view.pending) == 1
    assert view.pending[0].reason == "rejected_awaiting_new_version"


def test_builder_consultant_v1_then_agent_v2_without_review_highest_decides():
    ctrl = ControlInScope(
        code="PR.AA-01",
        title="Identities and credentials",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="aligo_consultant",
                author_name="Consultant Jane",
                control_status="implemented",
                explanation="Old consultant version.",
                created_at=FIXED_DT,
            ),
            ResultVersion(
                version_no=2,
                author_actor="agent",
                control_status="partially_implemented",
                explanation="New agent draft.",
                created_at=FIXED_DT,
                review=None,
            ),
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 0
    assert len(view.pending) == 1
    assert view.pending[0].reason == "awaiting_review"


def test_builder_control_without_versions_is_no_result():
    ctrl = ControlInScope(
        code="DE.CM-01",
        title="Network monitoring",
        versions=[],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 0
    assert len(view.pending) == 1
    assert view.pending[0].reason == "no_result"


def test_builder_final_not_applicable_becomes_exclusion():
    ctrl = ControlInScope(
        code="PR.PS-06",
        title="Secure software development",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="aligo_consultant",
                author_name="Consultant Dave",
                control_status="not_applicable",
                explanation="No in-house development.",
                justification="Organization does not develop software.",
                created_at=FIXED_DT,
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 0
    assert len(view.exclusions) == 1
    assert view.exclusions[0].code == "PR.PS-06"
    assert view.exclusions[0].justification == "Organization does not develop software."
    assert view.summary.status_counts == {
        "implemented": 0,
        "partially_implemented": 0,
        "not_implemented": 0,
        "not_assessed": 0,
    }


def test_builder_summary_numbers():
    controls = [
        ControlInScope(
            code="PR.AA-01",
            title="Identities and credentials",
            versions=[
                ResultVersion(
                    version_no=1,
                    author_actor="agent",
                    control_status="implemented",
                    explanation="Implemented.",
                    created_at=FIXED_DT,
                    review=ResultReview(outcome="accepted", reviewer_name="Alice", reviewed_at=FIXED_DT),
                )
            ],
        ),
        ControlInScope(
            code="PR.AA-03",
            title="Authentication",
            versions=[
                ResultVersion(
                    version_no=1,
                    author_actor="aligo_consultant",
                    author_name="Bob",
                    control_status="partially_implemented",
                    explanation="Partially implemented.",
                    created_at=FIXED_DT,
                )
            ],
        ),
        ControlInScope(
            code="PR.PS-06",
            title="Secure development",
            versions=[
                ResultVersion(
                    version_no=1,
                    author_actor="aligo_consultant",
                    author_name="Bob",
                    control_status="not_applicable",
                    explanation="No code.",
                    justification="No software built.",
                    created_at=FIXED_DT,
                )
            ],
        ),
        ControlInScope(
            code="DE.CM-01",
            title="Network monitoring",
            versions=[],
        ),
    ]
    inp = make_test_report_input(controls=controls)
    view = build_report_view(inp, FIXED_DT)

    assert view.summary.controls_in_scope == 4
    assert view.summary.finalized == 3  # 2 results + 1 exclusion
    assert view.summary.pending == 1
    assert view.summary.coverage_pct == 75.0
    assert set(view.summary.status_counts.keys()) == {
        "implemented",
        "partially_implemented",
        "not_implemented",
        "not_assessed",
    }
    assert view.summary.status_counts["implemented"] == 1
    assert view.summary.status_counts["partially_implemented"] == 1
    assert view.summary.status_counts["not_implemented"] == 0
    assert view.summary.status_counts["not_assessed"] == 0


def test_builder_draft_text_never_leaks_into_report_view():
    draft_marker = "DRAFT-MARKER-123-SECRET"
    ctrl = ControlInScope(
        code="PR.AA-05",
        title="Access permissions",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation=draft_marker,
                created_at=FIXED_DT,
                review=None,
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    json_data = view.model_dump_json()
    assert draft_marker not in json_data


def test_builder_evidence_pending_accepted_result():
    ctrl = ControlInScope(
        code="PR.AA-01",
        title="Identities and credentials",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation="Identities managed based on participant statement.",
                created_at=FIXED_DT,
                evidence_pending=True,
                review=ResultReview(
                    outcome="accepted",
                    reviewer_name="Consultant Alice",
                    reviewed_at=FIXED_DT,
                ),
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 1
    res = view.results[0]
    assert res.basis == "accepted_agent_result"
    assert res.evidence_pending is True
    assert view.summary.final_with_evidence_pending == 1


def test_builder_agent_version_modified_without_consultant_version_is_pending_modified():
    secret_draft = "SECRET-AGENT-DRAFT-12345"
    ctrl = ControlInScope(
        code="PR.AA-03",
        title="Authentication",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation=secret_draft,
                created_at=FIXED_DT,
                review=ResultReview(
                    outcome="modified",
                    reviewer_name="Consultant Jane",
                    reviewed_at=FIXED_DT,
                ),
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)

    assert len(view.results) == 0
    assert len(view.pending) == 1
    item = view.pending[0]
    assert item.code == "PR.AA-03"
    assert item.reason == "modified_awaiting_consultant_version"
    assert item.reason_label == "Modified by reviewer — consultant version pending"

    json_data = view.model_dump_json()
    assert secret_draft not in json_data


# --- 3. PDF Tests ---

def test_pdf_starts_with_pdf_magic_bytes():
    inp = make_test_report_input()
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)

    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_contains_required_sections_and_strings():
    controls = [
        ControlInScope(
            code="PR.AA-03",
            title="Authentication",
            versions=[
                ResultVersion(
                    version_no=1,
                    author_actor="aligo_consultant",
                    author_name="Bob Consultant",
                    control_status="partially_implemented",
                    explanation="MFA configured partially.",
                    created_at=FIXED_DT,
                )
            ],
        ),
        ControlInScope(
            code="PR.AA-05",
            title="Access permissions",
            versions=[
                ResultVersion(
                    version_no=1,
                    author_actor="agent",
                    control_status="implemented",
                    explanation="Awaiting agent review.",
                    created_at=FIXED_DT,
                    review=None,
                )
            ],
        ),
        ControlInScope(
            code="PR.PS-06",
            title="Software development",
            versions=[
                ResultVersion(
                    version_no=1,
                    author_actor="aligo_consultant",
                    author_name="Bob Consultant",
                    control_status="not_applicable",
                    explanation="No software.",
                    justification="Custom exclusion reason XYZ",
                    created_at=FIXED_DT,
                )
            ],
        ),
    ]
    inp = make_test_report_input(controls=controls)
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)
    text = extract_pdf_text(pdf_bytes)

    assert "NIST CSF 2.0 Assessment Report" in text
    assert "Acme Corp" in text
    assert "Partially implemented" in text
    assert "Pending review" in text
    assert "Awaiting expert review" in text
    assert "Custom exclusion reason XYZ" in text


def test_pdf_draft_marker_never_appears_in_pdf():
    draft_marker = "DRAFT-MARKER-123-UNREVIEWED"
    ctrl = ControlInScope(
        code="PR.AA-05",
        title="Access permissions",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation=draft_marker,
                created_at=FIXED_DT,
                review=None,
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)
    text = extract_pdf_text(pdf_bytes)

    assert draft_marker not in text


def test_pdf_special_characters_render_valid_pdf():
    ctrl = ControlInScope(
        code="PR.AA-01",
        title="Identities and credentials",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="aligo_consultant",
                author_name="Alice <Consultant>",
                control_status="implemented",
                explanation="<script> & </b> characters are tested here.",
                created_at=FIXED_DT,
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)

    assert pdf_bytes.startswith(b"%PDF")
    text = extract_pdf_text(pdf_bytes)
    assert "<script> & </b>" in text


def test_pdf_result_with_no_evidence_shows_notice():
    ctrl = ControlInScope(
        code="PR.AA-01",
        title="Identities and credentials",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="aligo_consultant",
                author_name="Alice",
                control_status="implemented",
                explanation="No evidence provided.",
                evidence=[],
                created_at=FIXED_DT,
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)
    text = extract_pdf_text(pdf_bytes)

    assert "No evidence on file." in text


def test_pdf_with_demo_data_shows_notice():
    inp = make_test_report_input(is_demo_data=True)
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)
    text = extract_pdf_text(pdf_bytes)

    assert "DEMO DATA" in text


EVIDENCE_PENDING_PARAGRAPH = (
    "Results marked “evidence pending” were accepted by an Aligo consultant on the basis of the "
    "participant's statement; the supporting evidence has not been validated yet."
)


def test_pdf_preserves_spanish_characters():
    ctrl = ControlInScope(
        code="PR.AA-01",
        title="Identities and credentials",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation="Política de contraseñas con autenticación multifactor; ¿cobertura total? ¡Aún no!",
                created_at=FIXED_DT,
                review=ResultReview(
                    outcome="accepted",
                    reviewer_name="José Muñoz Güell",
                    reviewed_at=FIXED_DT,
                ),
            )
        ],
    )
    inp = ReportInput(
        organization=OrganizationInfo(
            id=MEMBER_ORG_ID,
            name="Compañía Ñandú Ltda.",
            sector="Financial services",
            size="51-250 employees",
        ),
        assessment=AssessmentInfo(
            id=KNOWN_ASSESSMENT_ID,
            title="Evaluación de Seguridad",
            framework="NIST CSF 2.0",
            kb_version="kb-1.0",
            status="completed",
            started_at=FIXED_DT,
        ),
        controls=[ctrl],
    )
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)
    text = extract_pdf_text(pdf_bytes)

    assert "Compañía Ñandú Ltda." in text
    assert "José Muñoz Güell" in text
    assert "autenticación" in text
    assert "¿cobertura total?" in text
    assert "¡Aún no!" in text


def test_pdf_with_evidence_pending_contains_notice_and_row():
    ctrl = ControlInScope(
        code="PR.AA-01",
        title="Identities and credentials",
        versions=[
            ResultVersion(
                version_no=1,
                author_actor="agent",
                control_status="implemented",
                explanation="Identities managed based on statement.",
                created_at=FIXED_DT,
                evidence_pending=True,
                review=ResultReview(
                    outcome="accepted",
                    reviewer_name="Consultant Alice",
                    reviewed_at=FIXED_DT,
                ),
            )
        ],
    )
    inp = make_test_report_input(controls=[ctrl])
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)
    text = extract_pdf_text(pdf_bytes)

    # Only the Status cell uses parentheses; the paragraph uses quotes and the detail notice neither.
    assert "(evidence pending)" in text
    assert "Final results with evidence pending 1" in text
    assert EVIDENCE_PENDING_PARAGRAPH in text


def test_pdf_without_evidence_pending_does_not_contain_explanatory_paragraph():
    inp = make_test_report_input()
    view = build_report_view(inp, FIXED_DT)
    assert view.summary.final_with_evidence_pending == 0
    pdf_bytes = render_report_pdf(view)
    text = extract_pdf_text(pdf_bytes)

    assert EVIDENCE_PENDING_PARAGRAPH not in text
    assert "(evidence pending)" not in text
    # The summary row is always present, with a zero count.
    assert "Final results with evidence pending 0" in text


def test_pdf_assessment_status_label_rendered_instead_of_raw_value():
    inp = make_test_report_input()
    assert inp.assessment.status == "awaiting_review"
    view = build_report_view(inp, FIXED_DT)
    pdf_bytes = render_report_pdf(view)
    text = extract_pdf_text(pdf_bytes)

    assert "Awaiting review" in text
    assert "awaiting_review" not in text


# --- 4. API Tests ---

def test_api_no_auth_returns_401():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.get(
        f"/api/v1/organizations/{MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}/report"
    )
    assert response.status_code == 401


def test_api_non_member_org_returns_404():
    response = client.get(
        f"/api/v1/organizations/{NON_MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}/report"
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Assessment not found."


def test_api_member_unknown_assessment_returns_404():
    response = client.get(
        f"/api/v1/organizations/{MEMBER_ORG_ID}/assessments/{UNKNOWN_ASSESSMENT_ID}/report"
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Assessment not found."


def test_api_member_known_assessment_pdf_returns_200():
    response = client.get(
        f"/api/v1/organizations/{MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}/report.pdf"
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    content_disp = response.headers.get("content-disposition", "")
    assert "attachment" in content_disp
    assert f"agentic-grc-report-{KNOWN_ASSESSMENT_ID}.pdf" in content_disp
    assert response.content.startswith(b"%PDF")


def test_api_member_json_report_returns_200():
    response = client.get(
        f"/api/v1/organizations/{MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}/report"
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "pending" in data
    assert any(p["code"] == "PR.AA-05" for p in data["pending"])
    assert not any(r["code"] == "PR.AA-05" for r in data["results"])


def test_api_platform_admin_without_membership_returns_200():
    admin_user = FakeUser(id=uuid4(), is_platform_admin=True)
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = client.get(
        f"/api/v1/organizations/{NON_MEMBER_ORG_ID}/assessments/{KNOWN_ASSESSMENT_ID}/report"
    )
    assert response.status_code == 200


def test_api_invalid_uuid_returns_422():
    response = client.get(
        "/api/v1/organizations/not-a-valid-uuid/assessments/also-invalid/report"
    )
    assert response.status_code == 422


# --- 5. Demo Source Tests ---

def test_demo_source_loads_expected_structure():
    class FakeSector:
        label = "Financial services"

    class FakeSize:
        label = "51-250 employees"

    class FakeOrg:
        name = "Demo Corp"
        industry_sector = FakeSector()
        organization_size = FakeSize()

    class FakeDB:
        def get(self, model, ident):
            if ident == MEMBER_ORG_ID:
                return FakeOrg()
            return None

    source = DemoReportSource()
    data = source.load(FakeDB(), MEMBER_ORG_ID, DEMO_ASSESSMENT_ID)
    assert data is not None

    view = build_report_view(data, FIXED_DT)

    result_codes = [r.code for r in view.results]
    pending_codes = [p.code for p in view.pending]
    exclusion_codes = [e.code for e in view.exclusions]

    assert result_codes == ["PR.AA-01", "PR.AA-03"]
    assert pending_codes == ["DE.CM-01", "ID.AM-01", "PR.AA-05"]
    assert exclusion_codes == ["PR.PS-06"]


def test_demo_source_unknown_assessment_returns_none():
    class FakeDB:
        def get(self, model, ident):
            return None

    source = DemoReportSource()
    res = source.load(FakeDB(), MEMBER_ORG_ID, uuid4())
    assert res is None


# --- 6. Composite Source Tests ---

def test_composite_source_disallows_demo_outside_allowed():
    source = CompositeReportSource(allow_demo=False)
    res = source.load(None, MEMBER_ORG_ID, DEMO_ASSESSMENT_ID)
    assert res is None


def test_composite_source_allows_demo_when_enabled():
    class FakeSector:
        label = "Financial services"

    class FakeSize:
        label = "51-250 employees"

    class FakeOrg:
        name = "Demo Corp"
        industry_sector = FakeSector()
        organization_size = FakeSize()

    class FakeDB:
        def get(self, model, ident):
            if ident == MEMBER_ORG_ID:
                return FakeOrg()
            return None

    source = CompositeReportSource(allow_demo=True)
    res = source.load(FakeDB(), MEMBER_ORG_ID, DEMO_ASSESSMENT_ID)
    assert res is not None
    assert res.is_demo_data is True
    assert res.organization.name == "Demo Corp"


def test_composite_source_delegates_non_demo_to_db_source(monkeypatch):
    sentinel = make_test_report_input()
    source = CompositeReportSource(allow_demo=True)

    def fake_db_load(self, db, org_id, assess_id):
        return sentinel

    monkeypatch.setattr(DbReportSource, "load", fake_db_load)
    res = source.load(None, MEMBER_ORG_ID, KNOWN_ASSESSMENT_ID)
    assert res is sentinel


def test_get_report_source_default_settings_disallows_demo(monkeypatch):
    class FakeSector:
        label = "Financial services"

    class FakeSize:
        label = "51-250 employees"

    class FakeOrg:
        name = "Demo Corp"
        industry_sector = FakeSector()
        organization_size = FakeSize()

    class FakeDB:
        def get(self, model, ident):
            if ident == MEMBER_ORG_ID:
                return FakeOrg()
            return None

    dev_settings = Settings(_env_file=None, app_environment="development")
    monkeypatch.setattr("app.services.reports.source.get_settings", lambda: dev_settings)

    source = get_report_source()
    res = source.load(FakeDB(), MEMBER_ORG_ID, DEMO_ASSESSMENT_ID)
    assert res is None


def test_get_report_source_allow_demo_report_returns_demo_data(monkeypatch):
    class FakeSector:
        label = "Financial services"

    class FakeSize:
        label = "51-250 employees"

    class FakeOrg:
        name = "Demo Corp"
        industry_sector = FakeSector()
        organization_size = FakeSize()

    class FakeDB:
        def get(self, model, ident):
            if ident == MEMBER_ORG_ID:
                return FakeOrg()
            return None

    dev_settings = Settings(_env_file=None, app_environment="development", allow_demo_report=True)
    monkeypatch.setattr("app.services.reports.source.get_settings", lambda: dev_settings)

    source = get_report_source()
    res = source.load(FakeDB(), MEMBER_ORG_ID, DEMO_ASSESSMENT_ID)
    assert res is not None
    assert res.is_demo_data is True
    assert res.organization.name == "Demo Corp"


def test_settings_production_refuses_allow_demo_report():
    with pytest.raises(ValidationError, match="ALLOW_DEMO_REPORT"):
        Settings(
            _env_file=None,
            app_environment="production",
            allow_demo_report=True,
            app_base_url="https://app.example.com",
            supabase_url="https://project.example.supabase.co/",
            supabase_publishable_key="sb_publishable_public-key",
            supabase_secret_key="sb_secret_server-key",
            smtp_host="smtp.example.com",
            smtp_sender_email="noreply@example.com",
            smtp_starttls=True,
        )


