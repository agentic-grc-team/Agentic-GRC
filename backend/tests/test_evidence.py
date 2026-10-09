import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.security.auth import get_authenticated_identity
from app.api.v1.endpoints.organizations import _resolve_user, _active_membership
import uuid

client = TestClient(app)
TEST_ORG_ID = str(uuid.uuid4())

def mock_get_authenticated_identity():
    class MockIdentity:
        email = "test@example.com"
        issuer = "test_issuer"
        subject = "test_subject"
    return MockIdentity()

def mock_resolve_user(*args, **kwargs):
    class MockUser:
        id = uuid.uuid4()
    return MockUser()

def mock_active_membership(db, org_id, user_id):
    if str(org_id) == TEST_ORG_ID:
        return True
    return None

app.dependency_overrides[get_authenticated_identity] = mock_get_authenticated_identity

@pytest.fixture(autouse=True)
def patch_auth(monkeypatch):
    monkeypatch.setattr("app.api.v1.endpoints.evidence._resolve_user", mock_resolve_user)
    monkeypatch.setattr("app.api.v1.endpoints.evidence._active_membership", mock_active_membership)

def test_unauthorized_access():
    app.dependency_overrides.clear()
    response = client.post("/api/v1/evidence/", data={"organization_id": TEST_ORG_ID}, files={"file": ("test.txt", b"test data", "text/plain")})
    assert response.status_code == 401
    app.dependency_overrides[get_authenticated_identity] = mock_get_authenticated_identity # Vraćamo mock

def test_forbidden_organization():
    fake_org_id = str(uuid.uuid4())
    response = client.post("/api/v1/evidence/", data={"organization_id": fake_org_id}, files={"file": ("test.txt", b"test data", "text/plain")})
    assert response.status_code == 403

def test_unsupported_extension():
    response = client.post("/api/v1/evidence/", data={"organization_id": TEST_ORG_ID}, files={"file": ("virus.exe", b"bad code", "application/x-msdownload")})
    assert response.status_code == 400

def test_invalid_document():
    response = client.post("/api/v1/evidence/", data={"organization_id": TEST_ORG_ID}, files={"file": ("empty.txt", b"   ", "text/plain")})
    assert response.status_code == 422

def test_valid_upload():
    response = client.post("/api/v1/evidence/", data={"organization_id": TEST_ORG_ID}, files={"file": ("policy.txt", b"Valid compliance rules.", "text/plain")})
    assert response.status_code == 200
    assert "Valid compliance rules." in response.json()["extracted_content_preview"]