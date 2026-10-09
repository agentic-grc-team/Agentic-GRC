import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_unauthorized_access(): 
    response = client.post("/evidence/", files={"file": ("test.txt", b"test data", "text/plain")})
    assert response.status_code == 401

def test_missing_organization():
    headers = {"Authorization": "Bearer fake-token"}
    response = client.post("/evidence/", files={"file": ("test.txt", b"test data", "text/plain")}, headers=headers)
    assert response.status_code == 403

def test_unsupported_extension():
    headers = {"Authorization": "Bearer fake-token", "X-Organization-ID": "org-123"}
    response = client.post("/evidence/", files={"file": ("virus.exe", b"bad code", "application/x-msdownload")}, headers=headers)
    assert response.status_code == 400

def test_invalid_document():
    headers = {"Authorization": "Bearer fake-token", "X-Organization-ID": "org-123"}
    response = client.post("/evidence/", files={"file": ("empty.txt", b"   ", "text/plain")}, headers=headers)
    assert response.status_code == 422

def test_valid_upload():
    headers = {"Authorization": "Bearer fake-token", "X-Organization-ID": "org-123"}
    response = client.post("/evidence/", files={"file": ("policy.txt", b"Valid compliance rules.", "text/plain")}, headers=headers)
    assert response.status_code == 200
    assert "Valid compliance rules." in response.json()["extracted_content_preview"]
    assert response.json()["organization_id"] == "org-123"