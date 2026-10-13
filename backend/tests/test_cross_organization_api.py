"""A member of one organization must not read or change another organization's data through the API."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.db.models import ControlResultReview
from app.db.session import get_engine
from app.main import app
from app.schemas.assessments import DEFAULT_KB_VERSION
from app.security.auth import get_current_user
from app.services.reports.source import DEMO_ASSESSMENT_ID
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
    org_a, user_a, assessment_a, _, result_a, trace_a = make_review_context(db)
    org_b, user_b, assessment_b, _, result_b, trace_b = make_review_context(db)
    return SimpleNamespace(
        org_a=org_a, user_a=user_a, assessment_a=assessment_a, result_a=result_a, trace_a=trace_a,
        org_b=org_b, user_b=user_b, assessment_b=assessment_b, result_b=result_b, trace_b=trace_b,
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


@pytest.mark.parametrize("suffix", ["/report", "/report.pdf"])
def test_report_of_another_organization_is_not_found(as_user_a, two_organizations, suffix):
    response = as_user_a.get(org_url(two_organizations.org_b, f"/assessments/{DEMO_ASSESSMENT_ID}{suffix}"))

    assert response.status_code == 404


@pytest.mark.parametrize("suffix", ["/report", "/report.pdf"])
def test_report_for_foreign_assessment_is_not_found_through_own_organization(as_user_a, two_organizations, suffix):
    foreign_id = two_organizations.assessment_b.id

    response = as_user_a.get(org_url(two_organizations.org_a, f"/assessments/{foreign_id}{suffix}"))

    assert response.status_code == 404


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
