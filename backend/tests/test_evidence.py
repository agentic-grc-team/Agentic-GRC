import hashlib
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.security.auth import get_current_user
from app.api.v1.dependencies import get_db_session

client = TestClient(app)
TEST_ORG_ID = str(uuid.uuid4())
USER_ID = uuid.uuid4()
ASSESSMENT_ID = uuid.uuid4()
URL = "/api/v1/evidence/"

def mock_get_db_session():
    yield None

def mock_get_current_user():
    class MockUser:
        id = USER_ID
    return MockUser()

def mock_active_membership(db, org_id, user_id):
    if str(org_id) == TEST_ORG_ID:
        return True 
    return None 

app.dependency_overrides[get_db_session] = mock_get_db_session
app.dependency_overrides[get_current_user] = mock_get_current_user

@pytest.fixture(autouse=True)
def patch_auth(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.v1.endpoints.evidence._active_membership", mock_active_membership)
    monkeypatch.setattr("app.api.v1.endpoints.evidence.UPLOAD_DIR", str(tmp_path))

@pytest.fixture
def stored(monkeypatch):
    calls = []

    def fake_store(db, **fields):
        calls.append(fields)
        return SimpleNamespace(id=uuid.uuid4(), **fields)

    monkeypatch.setattr("app.api.v1.endpoints.evidence.store_evidence_file", fake_store)
    return calls

@pytest.fixture
def known_assessment(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.evidence.get_assessment",
        lambda db, org_id, assessment_id: SimpleNamespace(id=assessment_id) if assessment_id == ASSESSMENT_ID else None,
    )

def test_unauthorized_access():
    app.dependency_overrides.pop(get_current_user, None)
    
    response = client.post(URL, data={"organization_id": TEST_ORG_ID}, files={"file": ("test.txt", b"test data", "text/plain")})
    assert response.status_code == 401
    
    app.dependency_overrides[get_current_user] = mock_get_current_user

def test_forbidden_organization(stored):
    fake_org_id = str(uuid.uuid4())
    response = client.post(URL, data={"organization_id": fake_org_id}, files={"file": ("test.txt", b"test data", "text/plain")})
    assert response.status_code == 403
    assert stored == []

def test_unsupported_extension(stored):
    response = client.post(URL, data={"organization_id": TEST_ORG_ID}, files={"file": ("virus.exe", b"bad code", "application/x-msdownload")})
    assert response.status_code == 400
    assert stored == []

def test_invalid_document(stored, tmp_path):
    response = client.post(URL, data={"organization_id": TEST_ORG_ID}, files={"file": ("empty.txt", b"   ", "text/plain")})
    assert response.status_code == 422
    assert stored == []
    assert os.listdir(tmp_path) == []

def test_valid_upload(stored):
    response = client.post(URL, data={"organization_id": TEST_ORG_ID}, files={"file": ("policy.txt", b"Valid compliance rules.", "text/plain")})
    assert response.status_code == 200
    assert "Valid compliance rules." in response.json()["extracted_content_preview"]

def test_valid_upload_stores_file_metadata(stored, tmp_path):
    content = b"Valid compliance rules."
    response = client.post(URL, data={"organization_id": TEST_ORG_ID}, files={"file": ("policy.txt", content, "text/plain")})

    assert response.status_code == 200
    assert len(stored) == 1
    record = stored[0]
    assert record["organization_id"] == uuid.UUID(TEST_ORG_ID)
    assert record["uploaded_by_user_id"] == USER_ID
    assert record["assessment_id"] is None
    assert record["original_filename"] == "policy.txt"
    assert record["file_extension"] == ".txt"
    assert record["content_type"] == "text/plain"
    assert record["size_bytes"] == len(content)
    assert record["sha256"] == hashlib.sha256(content).hexdigest()
    assert record["extracted_text"] == "Valid compliance rules."
    assert os.listdir(tmp_path) == [record["stored_filename"]]

    body = response.json()
    assert body["id"]
    assert body["size_bytes"] == len(content)
    assert body["sha256"] == record["sha256"]
    assert body["stored_filename"] == record["stored_filename"]

def test_original_filename_drops_directories(stored):
    response = client.post(
        URL,
        data={"organization_id": TEST_ORG_ID},
        files={"file": ("C:\\Users\\someone\\docs\\policy.txt", b"Valid compliance rules.", "text/plain")},
    )

    assert response.status_code == 200
    assert stored[0]["original_filename"] == "policy.txt"

def test_upload_linked_to_assessment(stored, known_assessment):
    response = client.post(
        URL,
        data={"organization_id": TEST_ORG_ID, "assessment_id": str(ASSESSMENT_ID)},
        files={"file": ("policy.txt", b"Valid compliance rules.", "text/plain")},
    )

    assert response.status_code == 200
    assert stored[0]["assessment_id"] == ASSESSMENT_ID
    assert response.json()["assessment_id"] == str(ASSESSMENT_ID)

def test_upload_rejects_unknown_assessment(stored, known_assessment, tmp_path):
    response = client.post(
        URL,
        data={"organization_id": TEST_ORG_ID, "assessment_id": str(uuid.uuid4())},
        files={"file": ("policy.txt", b"Valid compliance rules.", "text/plain")},
    )

    assert response.status_code == 404
    assert stored == []
    assert os.listdir(tmp_path) == []

def test_upload_rejects_invalid_assessment_id(stored):
    response = client.post(
        URL,
        data={"organization_id": TEST_ORG_ID, "assessment_id": "not-a-uuid"},
        files={"file": ("policy.txt", b"Valid compliance rules.", "text/plain")},
    )

    assert response.status_code == 400
    assert stored == []

def test_upload_removes_file_when_metadata_cannot_be_saved(monkeypatch, tmp_path):
    def failing_store(db, **fields):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.api.v1.endpoints.evidence.store_evidence_file", failing_store)

    response = client.post(URL, data={"organization_id": TEST_ORG_ID}, files={"file": ("policy.txt", b"Valid compliance rules.", "text/plain")})

    assert response.status_code == 500
    assert os.listdir(tmp_path) == []

def test_list_requires_membership(monkeypatch):
    monkeypatch.setattr("app.api.v1.endpoints.evidence.list_evidence_files", lambda *args: pytest.fail("must not be queried"))

    response = client.get(URL, params={"organization_id": str(uuid.uuid4())})

    assert response.status_code == 403

def test_list_returns_only_requested_organization(monkeypatch):
    seen = []

    def fake_list(db, organization_id, assessment_id):
        seen.append((organization_id, assessment_id))
        return [
            SimpleNamespace(
                id=uuid.uuid4(),
                organization_id=organization_id,
                assessment_id=assessment_id,
                uploaded_by_user_id=USER_ID,
                original_filename="policy.txt",
                content_type="text/plain",
                file_extension=".txt",
                size_bytes=23,
                sha256="a" * 64,
                created_at=datetime.now(timezone.utc),
                extracted_text="never exposed",
            )
        ]

    monkeypatch.setattr("app.api.v1.endpoints.evidence.list_evidence_files", fake_list)

    response = client.get(URL, params={"organization_id": TEST_ORG_ID, "assessment_id": str(ASSESSMENT_ID)})

    assert response.status_code == 200
    assert seen == [(uuid.UUID(TEST_ORG_ID), ASSESSMENT_ID)]
    items = response.json()
    assert items[0]["original_filename"] == "policy.txt"
    assert items[0]["organization_id"] == TEST_ORG_ID
    assert "extracted_text" not in items[0]
