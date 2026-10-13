"""Evidence eligibility remains membership-based, including for platform administrators."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_db_session
from app.main import app
from app.security.auth import get_current_user


@pytest.fixture
def api(monkeypatch, tmp_path):
    saved = dict(app.dependency_overrides)
    statements = []

    class DB:
        def execute(self, statement):
            statements.append(statement)
            return SimpleNamespace(all=lambda: [])

    app.dependency_overrides[get_db_session] = lambda: DB()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), is_platform_admin=True)
    monkeypatch.setattr("app.api.v1.endpoints.evidence.UPLOAD_DIR", str(tmp_path))
    try:
        yield TestClient(app), statements
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


def test_membership_query_filters_platform_admin_organizations(api):
    client, statements = api
    assert client.get("/api/v1/organizations?active_memberships_only=true").status_code == 200
    assert "organization_memberships.id IS NOT NULL" in str(statements[-1].whereclause)
    assert client.get("/api/v1/organizations").status_code == 200
    assert statements[-1].whereclause is None


@pytest.mark.parametrize("has_membership, expected", [(False, 403), (True, 200)])
def test_platform_admin_upload_requires_active_membership(api, monkeypatch, has_membership, expected):
    client, _ = api
    monkeypatch.setattr("app.api.v1.endpoints.evidence._active_membership", lambda *args: object() if has_membership else None)
    monkeypatch.setattr(
        "app.api.v1.endpoints.evidence.store_evidence_file",
        lambda db, **fields: SimpleNamespace(id=uuid4(), **fields),
    )
    response = client.post("/api/v1/evidence/", data={"organization_id": str(uuid4())}, files={"file": ("policy.txt", b"Synthetic evidence", "text/plain")})
    assert response.status_code == expected
