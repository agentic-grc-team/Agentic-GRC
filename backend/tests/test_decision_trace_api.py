import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_db_session
from app.main import app
from app.security.auth import get_current_user

client = TestClient(app)
ORG_ID = uuid.uuid4()
ASSESSMENT_ID = uuid.uuid4()
URL = f"/api/v1/organizations/{ORG_ID}/assessments/{ASSESSMENT_ID}/traces"


def stored_trace():
    """A trace as it comes back from the database."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        organization_id=ORG_ID,
        assessment_id=ASSESSMENT_ID,
        decision_type="status_assessed",
        control_ids=["PR.AA-03"],
        module="Access",
        sources=[{"type": "interview_turn", "ref": "interview_turn:1", "excerpt": "No MFA for admins."}],
        evidence_nature=None,
        actor_type="agent",
        actor_user_id=None,
        model_name=None,
        prompt_id="rule:close-on-no",
        prompt_version="0.1.0",
        kb_version="csf2.0-kb-0.1",
        output={"status": "not_implemented"},
        rationale="The participant said MFA is not enforced for admins.",
        confidence=0.85,
        requires_human_review=False,
        latency_ms=None,
        fallback_used=False,
        reviews_trace_id=None,
        review_outcome=None,
        supersedes_trace_id=None,
    )


def make_user(is_platform_admin=False):
    return SimpleNamespace(id=uuid.uuid4(), is_platform_admin=is_platform_admin)


def membership(role):
    return lambda db, organization_id, user_id: SimpleNamespace(role=role)


def no_membership(db, organization_id, user_id):
    return None


@pytest.fixture(autouse=True)
def api(monkeypatch):
    """Fake database and user for every test, then restore what other test files set."""
    saved_overrides = dict(app.dependency_overrides)

    def fake_db():
        yield None

    app.dependency_overrides[get_db_session] = fake_db
    app.dependency_overrides[get_current_user] = make_user
    monkeypatch.setattr(
        "app.api.v1.endpoints.traces.list_traces",
        lambda db, organization_id, assessment_id: [stored_trace(), stored_trace()],
    )
    yield monkeypatch
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved_overrides)


def test_consultant_gets_traces(api):
    # Arrange
    api.setattr("app.api.v1.endpoints.traces._active_membership", membership("consultant"))

    # Act
    response = client.get(URL)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["decision_type"] == "status_assessed"
    assert body[0]["control_ids"] == ["PR.AA-03"]


def test_platform_admin_gets_traces_without_membership(api):
    app.dependency_overrides[get_current_user] = lambda: make_user(is_platform_admin=True)
    api.setattr("app.api.v1.endpoints.traces._active_membership", no_membership)

    response = client.get(URL)

    assert response.status_code == 200


def test_representative_is_forbidden(api):
    api.setattr("app.api.v1.endpoints.traces._active_membership", membership("representative"))

    response = client.get(URL)

    assert response.status_code == 403


def test_user_from_another_organization_gets_not_found(api):
    api.setattr("app.api.v1.endpoints.traces._active_membership", no_membership)

    response = client.get(URL)

    assert response.status_code == 404


def test_request_without_login_is_unauthorized(api):
    app.dependency_overrides.pop(get_current_user)

    response = client.get(URL)

    assert response.status_code == 401


def test_invalid_assessment_id_is_rejected(api):
    api.setattr("app.api.v1.endpoints.traces._active_membership", membership("consultant"))

    response = client.get(f"/api/v1/organizations/{ORG_ID}/assessments/not-a-uuid/traces")

    assert response.status_code == 422


def test_export_is_a_json_file_download(api):
    api.setattr("app.api.v1.endpoints.traces._active_membership", membership("administrator"))

    response = client.get(f"{URL}/export")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == f'attachment; filename="traces-{ASSESSMENT_ID}.json"'
    body = response.json()
    assert body["schema_version"] == "0.2"
    assert body["assessment_id"] == str(ASSESSMENT_ID)
    assert body["trace_count"] == 2
    assert len(body["traces"]) == 2


def test_export_is_forbidden_for_representative(api):
    api.setattr("app.api.v1.endpoints.traces._active_membership", membership("representative"))

    response = client.get(f"{URL}/export")

    assert response.status_code == 403
