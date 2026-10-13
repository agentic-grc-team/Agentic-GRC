from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints import expert_reviews as endpoints
from app.main import app
from app.schemas.expert_review import ReviewItem
from app.security.auth import get_current_user


RESULT_ID = UUID("00000000-0000-4000-8000-000000000011")
ASSESSMENT_ID = UUID("00000000-0000-4000-8000-000000000012")
USER_ID = UUID("00000000-0000-4000-8000-000000000013")

PENDING_URL = "/api/v1/expert-reviews/pending"
DECISION_URL = f"/api/v1/expert-reviews/{RESULT_ID}/decision"


@pytest.fixture
def api_context(monkeypatch):
    db = Mock(spec=Session)
    user = SimpleNamespace(id=USER_ID)

    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: user,
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        get_db_session,
        lambda: db,
    )

    list_reviews = Mock(
        return_value=[
            ReviewItem(
                result_id=str(RESULT_ID),
                assessment_id=str(ASSESSMENT_ID),
                control_code="PR.AA-03",
                control_title="Users, services, and hardware are authenticated",
                control_status="partially_implemented",
                maturity_current=2,
                confidence=0.78,
                explanation="MFA is enabled for some accounts.",
                evidence_summary="Configuration evidence.",
                requires_human_review=True,
            )
        ]
    )

    def fake_save(db_session, result_id, decision, current_user):
        return SimpleNamespace(
            control_result_id=result_id,
            outcome=decision.outcome,
            comment=decision.comment,
        )

    save_review = Mock(side_effect=fake_save)

    monkeypatch.setattr(
        endpoints,
        "list_pending_reviews",
        list_reviews,
    )
    monkeypatch.setattr(
        endpoints,
        "save_review_decision",
        save_review,
    )

    return SimpleNamespace(
        client=TestClient(app),
        db=db,
        user=user,
        list_reviews=list_reviews,
        save_review=save_review,
    )


def test_lists_pending_reviews(api_context):
    context = api_context

    response = context.client.get(PENDING_URL)

    assert response.status_code == 200
    reviews = response.json()
    assert len(reviews) == 1
    assert reviews[0]["result_id"] == str(RESULT_ID)
    assert reviews[0]["control_code"] == "PR.AA-03"

    context.list_reviews.assert_called_once_with(
        context.db,
        context.user,
    )


def test_returns_empty_pending_queue(api_context):
    api_context.list_reviews.return_value = []

    response = api_context.client.get(PENDING_URL)

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("outcome", ["accepted", "rejected", "modified"])
def test_saves_valid_decision_and_commits(api_context, outcome):
    context = api_context
    payload = {
        "outcome": outcome,
        "comment": "  Evidence checked.  ",
    }

    if outcome == "modified":
        payload["modified_result"] = {
            "control_status": "partially_implemented",
            "explanation": "  MFA coverage is incomplete.  ",
        }

    response = context.client.post(
        DECISION_URL,
        json=payload,
    )

    assert response.status_code == 200
    assert response.json() == {
        "result_id": str(RESULT_ID),
        "outcome": outcome,
        "comment": "Evidence checked.",
        "message": "Review decision saved successfully.",
    }

    context.save_review.assert_called_once()
    db, result_id, decision, user = (
        context.save_review.call_args.args
    )

    assert db is context.db
    assert result_id == RESULT_ID
    assert user is context.user
    assert decision.comment == "Evidence checked."

    if outcome == "modified":
        assert decision.modified_result.explanation == (
            "MFA coverage is incomplete."
        )

    context.db.commit.assert_called_once()
    context.db.rollback.assert_not_called()


def test_accepts_without_comment(api_context):
    response = api_context.client.post(
        DECISION_URL,
        json={"outcome": "accepted"},
    )

    assert response.status_code == 200
    assert response.json()["comment"] == ""


@pytest.mark.parametrize("outcome", ["modified", "rejected"])
@pytest.mark.parametrize("comment", ["", "   "])
def test_requires_non_blank_comment(api_context, outcome, comment):
    response = api_context.client.post(
        DECISION_URL,
        json={
            "outcome": outcome,
            "comment": comment,
        },
    )

    assert response.status_code == 422
    api_context.save_review.assert_not_called()
    api_context.db.commit.assert_not_called()


@pytest.mark.parametrize("outcome", ["modified", "rejected"])
def test_requires_comment_when_omitted(api_context, outcome):
    response = api_context.client.post(
        DECISION_URL,
        json={"outcome": outcome},
    )

    assert response.status_code == 422
    api_context.save_review.assert_not_called()


def test_modified_requires_modified_result(api_context):
    response = api_context.client.post(
        DECISION_URL,
        json={
            "outcome": "modified",
            "comment": "Correction needed.",
        },
    )

    assert response.status_code == 422
    api_context.save_review.assert_not_called()


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
            "explanation": "Does not apply.",
            "justification": "   ",
        },
        {
            "control_status": "not_assessed",
            "explanation": "Could not assess.",
            "not_assessed_reason": "   ",
        },
    ],
)
def test_rejects_invalid_modified_result(
    api_context,
    modified_result,
):
    response = api_context.client.post(
        DECISION_URL,
        json={
            "outcome": "modified",
            "comment": "Updated after review.",
            "modified_result": modified_result,
        },
    )

    assert response.status_code == 422
    api_context.save_review.assert_not_called()


@pytest.mark.parametrize("outcome", ["accepted", "rejected"])
def test_other_outcomes_cannot_include_modified_result(
    api_context,
    outcome,
):
    response = api_context.client.post(
        DECISION_URL,
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
    api_context.save_review.assert_not_called()


@pytest.mark.parametrize(
    "control_status,extra_fields",
    [
        ("implemented", {}),
        ("partially_implemented", {}),
        ("not_implemented", {}),
        (
            "not_applicable",
            {"justification": "The control does not apply."},
        ),
        (
            "not_assessed",
            {"not_assessed_reason": "Evidence is unavailable."},
        ),
    ],
)
def test_accepts_valid_modified_status(
    api_context,
    control_status,
    extra_fields,
):
    modified_result = {
        "control_status": control_status,
        "explanation": "Updated explanation.",
    }
    modified_result.update(extra_fields)

    response = api_context.client.post(
        DECISION_URL,
        json={
            "outcome": "modified",
            "comment": "Consultant correction.",
            "modified_result": modified_result,
        },
    )

    assert response.status_code == 200


def test_rejects_invalid_outcome(api_context):
    response = api_context.client.post(
        DECISION_URL,
        json={"outcome": "approved"},
    )

    assert response.status_code == 422
    api_context.save_review.assert_not_called()


def test_rejects_invalid_result_uuid(api_context):
    response = api_context.client.post(
        "/api/v1/expert-reviews/not-a-uuid/decision",
        json={"outcome": "accepted"},
    )

    assert response.status_code == 422
    api_context.save_review.assert_not_called()


@pytest.mark.parametrize("status_code", [403, 404, 409])
def test_rolls_back_service_http_errors(api_context, status_code):
    context = api_context
    context.save_review.side_effect = HTTPException(
        status_code=status_code,
        detail="Review unavailable.",
    )

    response = context.client.post(
        DECISION_URL,
        json={"outcome": "accepted"},
    )

    assert response.status_code == status_code
    assert response.json()["detail"] == "Review unavailable."
    context.db.rollback.assert_called_once()
    context.db.commit.assert_not_called()


def test_rolls_back_integrity_error(api_context):
    context = api_context
    context.save_review.side_effect = IntegrityError(
        "INSERT",
        {},
        Exception("Constraint conflict."),
    )

    response = context.client.post(
        DECISION_URL,
        json={"outcome": "accepted"},
    )

    assert response.status_code == 409
    context.db.rollback.assert_called_once()
    context.db.commit.assert_not_called()


def test_rolls_back_database_error(api_context):
    context = api_context
    context.save_review.side_effect = SQLAlchemyError(
        "Database unavailable."
    )

    response = context.client.post(
        DECISION_URL,
        json={"outcome": "accepted"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "The review could not be saved."
    context.db.rollback.assert_called_once()
    context.db.commit.assert_not_called()


def test_rolls_back_when_commit_fails(api_context):
    context = api_context
    context.db.commit.side_effect = SQLAlchemyError(
        "Commit failed."
    )

    response = context.client.post(
        DECISION_URL,
        json={"outcome": "accepted"},
    )

    assert response.status_code == 500
    context.db.commit.assert_called_once()
    context.db.rollback.assert_called_once()


@pytest.mark.parametrize("operation", ["pending", "decision"])
def test_requires_authentication(api_context, monkeypatch, operation):
    monkeypatch.delitem(
        app.dependency_overrides,
        get_current_user,
        raising=False,
    )

    if operation == "pending":
        response = api_context.client.get(PENDING_URL)
    else:
        response = api_context.client.post(
            DECISION_URL,
            json={"outcome": "accepted"},
        )

    assert response.status_code in (401, 403)
    api_context.list_reviews.assert_not_called()
    api_context.save_review.assert_not_called()