import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security.auth import get_current_user


@pytest.fixture
def authenticated_client(monkeypatch):
    def fake_current_user():
        return object()

    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        fake_current_user,
    )

    return TestClient(app)


def test_lists_pending_reviews(authenticated_client):
    response = authenticated_client.get(
        "/api/v1/expert-reviews/pending"
    )

    assert response.status_code == 200

    reviews = response.json()

    assert len(reviews) == 1
    assert reviews[0]["result_id"] == "result-demo-001"
    assert reviews[0]["control_code"] == "PR.AA-03"
    assert reviews[0]["requires_human_review"] is True


def test_accepts_review_decision(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": "accepted",
            "comment": "The evidence supports the result.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "result_id": "result-demo-001",
        "outcome": "accepted",
        "comment": "The evidence supports the result.",
        "message": "Review decision received successfully.",
    }


def test_rejects_unknown_result(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-does-not-exist/decision",
        json={
            "outcome": "rejected",
            "comment": "Unknown result.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Review result not found."


def test_rejects_invalid_outcome(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": "approved",
            "comment": "",
        },
    )

    assert response.status_code == 422


def test_pending_reviews_require_authentication(monkeypatch):
    monkeypatch.delitem(
        app.dependency_overrides,
        get_current_user,
        raising=False,
    )

    client = TestClient(app)

    response = client.get("/api/v1/expert-reviews/pending")

    assert response.status_code in (401, 403)


def test_review_decision_requires_authentication(monkeypatch):
    monkeypatch.delitem(
        app.dependency_overrides,
        get_current_user,
        raising=False,
    )

    client = TestClient(app)

    response = client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": "accepted",
            "comment": "The evidence supports the result.",
        },
    )

    assert response.status_code in (401, 403)