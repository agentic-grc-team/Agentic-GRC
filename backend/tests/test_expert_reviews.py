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

@pytest.mark.parametrize("outcome", ["modified", "rejected"])
@pytest.mark.parametrize("comment", ["", "   "])
def test_requires_comment_for_modified_or_rejected(
    authenticated_client,
    outcome,
    comment,
):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": outcome,
            "comment": comment,
        },
    )

    assert response.status_code == 422
    assert any(
        "A review comment is required" in error["msg"]
        for error in response.json()["detail"]
    )


@pytest.mark.parametrize("outcome", ["modified", "rejected"])
def test_requires_comment_when_omitted(
    authenticated_client,
    outcome,
):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={"outcome": outcome},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("outcome", ["accepted", "modified", "rejected"])
def test_trims_review_comment(authenticated_client, outcome):
    payload = {
        "outcome": outcome,
        "comment": "  Evidence checked.  ",
    }

    if outcome == "modified":
        payload["modified_result"] = {
            "control_status": "partially_implemented",
            "explanation": "MFA is enabled for some accounts.",
        }

    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["comment"] == "Evidence checked."


def test_accepts_decision_without_comment(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={"outcome": "accepted"},
    )

    assert response.status_code == 200
    assert response.json()["comment"] == ""

def test_modified_decision_requires_modified_result(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": "modified",
            "comment": "The proposed status needs correction.",
        },
    )

    assert response.status_code == 422
    assert any(
        "A modified result is required" in error["msg"]
        for error in response.json()["detail"]
    )

@pytest.mark.parametrize(
    "modified_result",
    [
        {
            "control_status": "approved",
            "explanation": "Updated result.",
        },
        {
            "control_status": "implemented",
            "explanation": "   ",
        },
        {
            "control_status": "not_applicable",
            "explanation": "This control does not apply.",
            "justification": "   ",
        },
        {
            "control_status": "not_assessed",
            "explanation": "Assessment could not be completed.",
            "not_assessed_reason": "   ",
        },
    ],
)
def test_rejects_invalid_modified_result(
    authenticated_client,
    modified_result,
):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": "modified",
            "comment": "Updated after review.",
            "modified_result": modified_result,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize("outcome", ["accepted", "rejected"])
def test_other_decisions_cannot_include_modified_result(
    authenticated_client,
    outcome,
):
    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": outcome,
            "comment": "Evidence checked.",
            "modified_result": {
                "control_status": "implemented",
                "explanation": "Updated result.",
            },
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "control_status,extra_fields",
    [
        ("implemented", {}),
        ("partially_implemented", {}),
        ("not_implemented", {}),
        (
            "not_applicable",
            {"justification": "The organization does not develop software."},
        ),
        (
            "not_assessed",
            {"not_assessed_reason": "Configuration evidence is unavailable."},
        ),
    ],
)
def test_accepts_valid_modified_result(
    authenticated_client,
    control_status,
    extra_fields,
):
    modified_result = {
        "control_status": control_status,
        "explanation": "Updated after checking the evidence.",
    }
    modified_result.update(extra_fields)

    response = authenticated_client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": "modified",
            "comment": "Consultant correction.",
            "modified_result": modified_result,
        },
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "modified"