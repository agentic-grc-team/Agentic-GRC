"""A member of one organization must not read or change another organization's data through the API."""

import hashlib
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.db.models import ControlResultReview, EvidenceControlLink
from app.db.session import get_engine
from app.main import app
from app.schemas.assessments import DEFAULT_KB_VERSION
from app.schemas.report import AssessmentInfo, OrganizationInfo, ReportInput
from app.security.auth import get_current_user
from app.services.evidence import store_evidence_file
from app.services.evidence_links import link_evidence_to_control
from app.services.reports.source import DEMO_ASSESSMENT_ID, get_report_source
from tests.test_expert_review_db import make_review_context


@pytest.fixture
def db():
    """A session inside a transaction that is rolled back after each test, so nothing is left behind."""
    try:
        engine = get_engine()
        connection = engine.connect()
    except (OSError, SQLAlchemyError, RuntimeError):
        pytest.skip("PostgreSQL is unavailable for integration tests.")
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def two_organizations(db):
    """Organization A (the caller's) and organization B (somebody else's), each with a consultant and data."""
    org_a, user_a, assessment_a, control_a, result_a, trace_a = make_review_context(db)
    org_b, user_b, assessment_b, control_b, result_b, trace_b = make_review_context(db)
    return SimpleNamespace(
        org_a=org_a, user_a=user_a, assessment_a=assessment_a, control_a=control_a, result_a=result_a, trace_a=trace_a,
        org_b=org_b, user_b=user_b, assessment_b=assessment_b, control_b=control_b, result_b=result_b, trace_b=trace_b,
    )


@pytest.fixture
def as_user_a(db, two_organizations):
    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: two_organizations.user_a
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


def org_url(org, suffix=""):
    return f"/api/v1/organizations/{org.id}{suffix}"


def test_organization_of_another_tenant_is_not_found(as_user_a, two_organizations):
    assert as_user_a.get(org_url(two_organizations.org_a)).status_code == 200
    assert as_user_a.get(org_url(two_organizations.org_b)).status_code == 404


def test_organization_list_contains_only_own_organization(as_user_a, two_organizations):
    response = as_user_a.get("/api/v1/organizations")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(two_organizations.org_a.id)]


def test_assessment_list_contains_only_own_assessments(as_user_a, two_organizations):
    response = as_user_a.get(org_url(two_organizations.org_a, "/assessments"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(two_organizations.assessment_a.id)]


def test_assessment_list_of_another_organization_is_not_found(as_user_a, two_organizations):
    response = as_user_a.get(org_url(two_organizations.org_b, "/assessments"))

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found."


def test_assessment_of_another_organization_is_not_found_through_either_path(as_user_a, two_organizations):
    foreign_id = two_organizations.assessment_b.id

    own_path = as_user_a.get(org_url(two_organizations.org_a, f"/assessments/{foreign_id}"))
    foreign_path = as_user_a.get(org_url(two_organizations.org_b, f"/assessments/{foreign_id}"))

    assert own_path.status_code == 404
    assert foreign_path.status_code == 404


def test_own_assessment_is_readable(as_user_a, two_organizations):
    response = as_user_a.get(org_url(two_organizations.org_a, f"/assessments/{two_organizations.assessment_a.id}"))

    assert response.status_code == 200
    assert response.json()["organization_id"] == str(two_organizations.org_a.id)


def test_started_assessment_stores_date_and_framework_version(as_user_a, two_organizations):
    before = datetime.now(timezone.utc)

    created = as_user_a.post(org_url(two_organizations.org_a, "/assessments"), json={"title": "Q4 assessment"})

    assert created.status_code == 201
    read_back = as_user_a.get(org_url(two_organizations.org_a, f"/assessments/{created.json()['id']}")).json()
    assert read_back["organization_id"] == str(two_organizations.org_a.id)
    assert read_back["status"] == "in_progress"
    assert read_back["framework_code"] == "NIST-CSF"
    assert read_back["framework_version"] == "2.0"
    assert read_back["kb_version"] == DEFAULT_KB_VERSION
    started_at = datetime.fromisoformat(read_back["started_at"])
    assert started_at.tzinfo is not None
    assert before <= started_at <= datetime.now(timezone.utc)


def test_assessment_cannot_be_started_in_another_organization(as_user_a, two_organizations):
    response = as_user_a.post(org_url(two_organizations.org_b, "/assessments"), json={"title": "Not allowed"})

    assert response.status_code == 404


def test_traces_of_another_organization_are_not_found(as_user_a, two_organizations):
    assessment_id = two_organizations.assessment_b.id

    listed = as_user_a.get(org_url(two_organizations.org_b, f"/assessments/{assessment_id}/traces"))
    exported = as_user_a.get(org_url(two_organizations.org_b, f"/assessments/{assessment_id}/traces/export"))

    assert listed.status_code == 404
    assert exported.status_code == 404


def test_traces_of_foreign_assessment_are_not_returned_through_own_organization(as_user_a, two_organizations):
    foreign_id = two_organizations.assessment_b.id

    response = as_user_a.get(org_url(two_organizations.org_a, f"/assessments/{foreign_id}/traces"))

    assert response.status_code == 200
    assert response.json() == []


def test_own_traces_are_readable(as_user_a, two_organizations):
    response = as_user_a.get(org_url(two_organizations.org_a, f"/assessments/{two_organizations.assessment_a.id}/traces"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(two_organizations.trace_a.id)]


class MatchingReportSource:
    """Serves a report only when organization and assessment IDs match a known pair."""

    def __init__(self, known):
        self.known = known

    def load(self, db, organization_id, assessment_id):
        if (organization_id, assessment_id) not in self.known:
            return None
        organization, assessment = self.known[(organization_id, assessment_id)]
        return ReportInput(
            organization=OrganizationInfo(
                id=organization.id,
                name=organization.name,
                sector="other",
                size="unknown",
            ),
            assessment=AssessmentInfo(
                id=assessment.id,
                title=assessment.title,
                framework="NIST CSF 2.0",
                kb_version=assessment.kb_version,
                status=assessment.status,
                started_at=assessment.started_at,
                completed_at=assessment.completed_at,
            ),
            controls=[],
            is_demo_data=False,
        )


@pytest.fixture
def matching_report_source(two_organizations):
    saved = app.dependency_overrides.get(get_report_source)
    app.dependency_overrides[get_report_source] = lambda: MatchingReportSource(
        {
            (two_organizations.org_a.id, two_organizations.assessment_a.id): (
                two_organizations.org_a,
                two_organizations.assessment_a,
            ),
            (two_organizations.org_b.id, two_organizations.assessment_b.id): (
                two_organizations.org_b,
                two_organizations.assessment_b,
            ),
        }
    )
    try:
        yield
    finally:
        if saved is None:
            app.dependency_overrides.pop(get_report_source, None)
        else:
            app.dependency_overrides[get_report_source] = saved


@pytest.mark.parametrize("suffix", ["/report", "/report.pdf"])
def test_report_of_another_organization_is_not_found(as_user_a, two_organizations, suffix):
    response = as_user_a.get(org_url(two_organizations.org_b, f"/assessments/{DEMO_ASSESSMENT_ID}{suffix}"))

    assert response.status_code == 404


@pytest.mark.parametrize("suffix", ["/report", "/report.pdf"])
def test_own_assessment_report_is_readable_and_foreign_assessment_is_not(
    as_user_a, two_organizations, matching_report_source, suffix
):
    own = as_user_a.get(
        org_url(two_organizations.org_a, f"/assessments/{two_organizations.assessment_a.id}{suffix}")
    )
    foreign = as_user_a.get(
        org_url(two_organizations.org_a, f"/assessments/{two_organizations.assessment_b.id}{suffix}")
    )
    other_org = as_user_a.get(
        org_url(two_organizations.org_b, f"/assessments/{two_organizations.assessment_b.id}{suffix}")
    )

    assert own.status_code == 200
    if suffix == "/report":
        assert own.json()["assessment"]["id"] == str(two_organizations.assessment_a.id)
    else:
        assert own.headers["content-type"] == "application/pdf"
        assert own.content.startswith(b"%PDF")

    assert foreign.status_code == 404
    assert other_org.status_code == 404


def test_pending_reviews_contain_only_own_results(as_user_a, two_organizations):
    response = as_user_a.get("/api/v1/expert-reviews/pending")

    assert response.status_code == 200
    result_ids = {item["result_id"] for item in response.json()}
    assert str(two_organizations.result_a.id) in result_ids
    assert str(two_organizations.result_b.id) not in result_ids


def test_review_decision_on_result_of_another_organization_is_rejected(as_user_a, two_organizations, db):
    response = as_user_a.post(
        f"/api/v1/expert-reviews/{two_organizations.result_b.id}/decision",
        json={"outcome": "accepted"},
    )

    assert response.status_code == 404
    reviews = db.query(ControlResultReview).filter_by(control_result_id=two_organizations.result_b.id).count()
    assert reviews == 0


def test_evidence_upload_to_another_organization_is_forbidden(as_user_a, two_organizations, tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.v1.endpoints.evidence.UPLOAD_DIR", str(tmp_path))

    response = as_user_a.post(
        "/api/v1/evidence/",
        data={"organization_id": str(two_organizations.org_b.id)},
        files={"file": ("policy.txt", b"Valid compliance rules.", "text/plain")},
    )

    assert response.status_code == 403
    assert list(tmp_path.iterdir()) == []


def store_evidence_for(db, organization, assessment):
    content = b"Valid compliance rules."
    return store_evidence_file(
        db,
        organization_id=organization.id,
        uploaded_by_user_id=None,
        assessment_id=assessment.id,
        original_filename="policy.txt",
        stored_filename=f"{organization.id}_{uuid.uuid4()}.txt",
        content_type="text/plain",
        file_extension=".txt",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        extracted_text=content.decode(),
    )


def link_url(evidence):
    return f"/api/v1/evidence/{evidence.id}/controls"


def test_own_evidence_can_be_linked_to_own_control(db, as_user_a, two_organizations):
    evidence = store_evidence_for(db, two_organizations.org_a, two_organizations.assessment_a)

    response = as_user_a.post(
        link_url(evidence),
        json={
            "organization_id": str(two_organizations.org_a.id),
            "assessment_control_id": str(two_organizations.control_a.id),
        },
    )

    assert response.status_code == 201
    assert db.query(EvidenceControlLink).filter_by(organization_id=two_organizations.org_a.id).count() == 1


def test_evidence_link_in_another_organization_is_forbidden(db, as_user_a, two_organizations):
    evidence_b = store_evidence_for(db, two_organizations.org_b, two_organizations.assessment_b)

    response = as_user_a.post(
        link_url(evidence_b),
        json={
            "organization_id": str(two_organizations.org_b.id),
            "assessment_control_id": str(two_organizations.control_b.id),
        },
    )

    assert response.status_code == 403
    assert db.query(EvidenceControlLink).count() == 0


def test_evidence_of_another_organization_is_not_found_under_own_organization(db, as_user_a, two_organizations):
    evidence_b = store_evidence_for(db, two_organizations.org_b, two_organizations.assessment_b)

    response = as_user_a.post(
        link_url(evidence_b),
        json={
            "organization_id": str(two_organizations.org_a.id),
            "assessment_control_id": str(two_organizations.control_a.id),
        },
    )

    assert response.status_code == 404
    assert db.query(EvidenceControlLink).count() == 0


def test_control_of_another_organization_is_not_found_under_own_organization(db, as_user_a, two_organizations):
    evidence_a = store_evidence_for(db, two_organizations.org_a, two_organizations.assessment_a)

    response = as_user_a.post(
        link_url(evidence_a),
        json={
            "organization_id": str(two_organizations.org_a.id),
            "assessment_control_id": str(two_organizations.control_b.id),
        },
    )

    assert response.status_code == 404
    assert db.query(EvidenceControlLink).count() == 0


def test_evidence_link_of_another_organization_cannot_be_removed_or_listed(db, as_user_a, two_organizations):
    evidence_b = store_evidence_for(db, two_organizations.org_b, two_organizations.assessment_b)
    link_evidence_to_control(
        db, two_organizations.org_b.id, evidence_b.id, two_organizations.control_b.id, two_organizations.user_b.id
    )

    removed = as_user_a.delete(
        f"{link_url(evidence_b)}/{two_organizations.control_b.id}",
        params={"organization_id": str(two_organizations.org_b.id)},
    )
    listed = as_user_a.get(
        "/api/v1/evidence/",
        params={
            "organization_id": str(two_organizations.org_b.id),
            "assessment_control_id": str(two_organizations.control_b.id),
        },
    )
    removed_under_own_organization = as_user_a.delete(
        f"{link_url(evidence_b)}/{two_organizations.control_b.id}",
        params={"organization_id": str(two_organizations.org_a.id)},
    )

    assert removed.status_code == 403
    assert listed.status_code == 403
    assert removed_under_own_organization.status_code == 404
    assert db.query(EvidenceControlLink).count() == 1


def test_unknown_user_without_membership_sees_nothing(db, two_organizations):
    stranger = SimpleNamespace(id=uuid.uuid4(), is_platform_admin=False)
    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        client = TestClient(app)
        assert client.get(org_url(two_organizations.org_a, "/assessments")).status_code == 404
        assert client.get(org_url(two_organizations.org_b, "/assessments")).status_code == 404
        assert client.get("/api/v1/organizations").json() == []
        assert client.get("/api/v1/expert-reviews/pending").json() == []
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
