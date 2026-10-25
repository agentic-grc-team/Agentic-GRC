"""Unit tests for assessments API with dependency overrides and mocks (AGRC-61)."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_db_session
from app.db.models import Organization
import app.db.models as db_models
import app.schemas.decision_trace as trace_schemas
from app.main import app
from app.schemas.assessments import DEFAULT_KB_VERSION, AssessmentCreate
from app.security.auth import get_current_user
from app.services.assessments import start_assessment as real_start_assessment

client = TestClient(app)
ORG_ID = uuid.uuid4()
ASSESSMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
URL = f"/api/v1/organizations/{ORG_ID}/assessments"


def stored_assessment(assessment_id=None, organization_id=ORG_ID, **changes):
    fields = dict(
        id=assessment_id or ASSESSMENT_ID,
        organization_id=organization_id,
        title="NIST CSF Initial Assessment",
        framework_code="NIST-CSF",
        framework_version="2.0",
        kb_version="demo-0.2",
        status="in_progress",
        created_by_user_id=USER_ID,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        created_at=datetime.now(timezone.utc),
    )
    fields.update(changes)
    return SimpleNamespace(**fields)


def make_user(is_platform_admin=False, user_id=None):
    return SimpleNamespace(id=user_id or USER_ID, is_platform_admin=is_platform_admin)


def membership(role):
    return lambda db, organization_id, user_id: SimpleNamespace(role=role)


def no_membership(db, organization_id, user_id):
    return None


class FakeDB:
    def get(self, model, ident):
        if model is Organization and ident == ORG_ID:
            return SimpleNamespace(id=ORG_ID, name="Known Org")
        return None


@pytest.fixture(autouse=True)
def api(monkeypatch):
    """Fake database and user for every test, then restore what other test files set."""
    saved_overrides = dict(app.dependency_overrides)

    def fake_db():
        yield FakeDB()

    app.dependency_overrides[get_db_session] = fake_db
    app.dependency_overrides[get_current_user] = make_user

    monkeypatch.setattr(
        "app.api.v1.endpoints.assessments.start_assessment",
        lambda db, organization_id, created_by_user_id, data: stored_assessment(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            title=data.title,
            kb_version=data.kb_version or DEFAULT_KB_VERSION,
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.assessments.list_assessments",
        lambda db, organization_id: [stored_assessment(), stored_assessment(assessment_id=uuid.uuid4())],
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.assessments.get_assessment",
        lambda db, organization_id, assessment_id: stored_assessment(assessment_id=assessment_id)
        if assessment_id == ASSESSMENT_ID
        else None,
    )

    yield monkeypatch

    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved_overrides)


def test_consultant_can_start_assessment(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("consultant"))
    captured = {}

    def mock_start(db, organization_id, created_by_user_id, data):
        captured["organization_id"] = organization_id
        captured["created_by_user_id"] = created_by_user_id
        captured["data"] = data
        return stored_assessment(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            title=data.title,
            kb_version=data.kb_version or DEFAULT_KB_VERSION,
        )

    api.setattr("app.api.v1.endpoints.assessments.start_assessment", mock_start)

    response = client.post(URL, json={"title": "Test Assessment", "kb_version": "demo-0.2"})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["framework_code"] == "NIST-CSF"
    assert captured["organization_id"] == ORG_ID
    assert captured["created_by_user_id"] == USER_ID
    assert captured["data"].title == "Test Assessment"
    assert captured["data"].kb_version == "demo-0.2"


def test_administrator_can_start_assessment(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("administrator"))
    response = client.post(URL, json={"title": "Admin Assessment"})
    assert response.status_code == 201


def test_representative_cannot_start_assessment(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("representative"))
    response = client.post(URL, json={"title": "Rep Assessment"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Only administrators and consultants can start an assessment."


def test_non_member_cannot_start_assessment(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", no_membership)
    response = client.post(URL, json={"title": "Non-member Assessment"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found."


def test_platform_admin_can_start_assessment_without_membership(api):
    app.dependency_overrides[get_current_user] = lambda: make_user(is_platform_admin=True)
    api.setattr("app.api.v1.endpoints.assessments._active_membership", no_membership)
    response = client.post(URL, json={"title": "Platform Admin Assessment"})
    assert response.status_code == 201


def test_platform_admin_cannot_start_assessment_if_org_missing(api):
    app.dependency_overrides[get_current_user] = lambda: make_user(is_platform_admin=True)
    unknown_org_id = uuid.uuid4()
    response = client.post(f"/api/v1/organizations/{unknown_org_id}/assessments", json={"title": "Missing Org"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found."


def test_blank_title_rejected(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("consultant"))
    response = client.post(URL, json={"title": "   "})
    assert response.status_code == 422


def test_unknown_kb_version_rejected(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("consultant"))
    response = client.post(URL, json={"title": "Unknown KB", "kb_version": "custom-1.0"})
    assert response.status_code == 422
    assert "Unknown knowledge-base version" in str(response.json()["detail"])


def test_no_kb_version_defaults_to_none_in_request_and_service_sets_default(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("consultant"))
    captured_data = {}

    def mock_start(db, organization_id, created_by_user_id, data):
        captured_data["kb_version"] = data.kb_version
        return stored_assessment()

    api.setattr("app.api.v1.endpoints.assessments.start_assessment", mock_start)

    response = client.post(URL, json={"title": "No KB Version"})
    assert response.status_code == 201
    assert captured_data["kb_version"] is None

    class RecordingFakeDB:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        def add_all(self, objs):
            self.added.extend(objs)

        def flush(self):
            pass

        def commit(self):
            pass

        def rollback(self):
            pass

        def refresh(self, obj):
            pass

    fake_db = RecordingFakeDB()
    created_assessment = real_start_assessment(
        fake_db, ORG_ID, USER_ID, AssessmentCreate(title="Real Service Test")
    )
    assert len(fake_db.added) == 4  # the assessment and its three KB controls
    assert fake_db.added[0] is created_assessment
    assert [control.control_code for control in fake_db.added[1:]] == ["PR.AA-01", "PR.AA-03", "PR.AA-05"]
    assert created_assessment.kb_version == DEFAULT_KB_VERSION
    assert created_assessment.status == "in_progress"
    assert created_assessment.started_at is not None
    assert created_assessment.started_at.tzinfo is not None


def test_representative_can_list_assessments(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("representative"))
    response = client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2


def test_non_member_cannot_list_assessments(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", no_membership)
    response = client.get(URL)
    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found."


def test_get_unknown_assessment_returns_404(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("consultant"))
    unknown_id = uuid.uuid4()
    response = client.get(f"{URL}/{unknown_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Assessment not found."


def test_request_without_login_is_unauthorized(api):
    app.dependency_overrides.pop(get_current_user)
    response = client.get(URL)
    assert response.status_code == 401


def test_invalid_uuid_rejected(api):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("consultant"))
    response = client.get(f"/api/v1/organizations/{ORG_ID}/assessments/not-a-uuid")
    assert response.status_code == 422


def test_platform_admin_cannot_list_assessments_if_org_missing(api):
    app.dependency_overrides[get_current_user] = lambda: make_user(is_platform_admin=True)
    unknown_org_id = uuid.uuid4()
    response = client.get(f"/api/v1/organizations/{unknown_org_id}/assessments")
    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found."


def test_models_and_schemas_control_statuses_match():
    assert db_models.CONTROL_STATUSES == trace_schemas.CONTROL_STATUSES


SCOPE_URL = f"{URL}/{ASSESSMENT_ID}/scope"


def stored_control(code, title, in_scope=True):
    return SimpleNamespace(control_code=code, control_title=title, in_scope=in_scope)


@pytest.fixture
def scope_controls(api):
    api.setattr(
        "app.api.v1.endpoints.assessments.list_in_scope_controls",
        lambda db, organization_id, assessment_id: [
            stored_control("PR.AA-01", "Identities are managed"),
            stored_control("PR.AA-03", "Users are authenticated"),
        ],
    )


def test_representative_can_see_the_assessment_scope(api, scope_controls):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("representative"))

    response = client.get(SCOPE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["organization_name"] == "Known Org"
    assert body["assessment"]["id"] == str(ASSESSMENT_ID)
    assert body["control_count"] == 2
    assert [f["code"] for f in body["functions"]] == ["PR"]
    assert [c["code"] for c in body["functions"][0]["categories"][0]["controls"]] == ["PR.AA-01", "PR.AA-03"]


def test_non_member_cannot_see_the_assessment_scope(api, scope_controls):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", no_membership)

    response = client.get(SCOPE_URL)

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found."


def test_scope_of_unknown_assessment_returns_404(api, scope_controls):
    api.setattr("app.api.v1.endpoints.assessments._active_membership", membership("consultant"))

    response = client.get(f"{URL}/{uuid.uuid4()}/scope")

    assert response.status_code == 404
    assert response.json()["detail"] == "Assessment not found."


def test_scope_requires_login(api, scope_controls):
    app.dependency_overrides.pop(get_current_user)

    response = client.get(SCOPE_URL)

    assert response.status_code == 401
