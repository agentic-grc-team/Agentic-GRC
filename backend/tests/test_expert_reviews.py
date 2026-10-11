from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_lists_pending_reviews():
    response = client.get("/api/v1/expert-reviews/pending")

    assert response.status_code == 200

    reviews = response.json()

    assert len(reviews) == 1
    assert reviews[0]["result_id"] == "result-demo-001"
    assert reviews[0]["control_code"] == "PR.AA-03"
    assert reviews[0]["requires_human_review"] is True


def test_accepts_review_decision():
    response = client.post(
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


def test_rejects_unknown_result():
    response = client.post(
        "/api/v1/expert-reviews/result-does-not-exist/decision",
        json={
            "outcome": "rejected",
            "comment": "Unknown result.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Review result not found."


def test_rejects_invalid_outcome():
    response = client.post(
        "/api/v1/expert-reviews/result-demo-001/decision",
        json={
            "outcome": "approved",
            "comment": "",
        },
    )

    assert response.status_code == 422