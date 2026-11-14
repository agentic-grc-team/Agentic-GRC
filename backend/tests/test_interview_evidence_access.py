from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services import interviews
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints import evidence
from app.main import app
from app.security.auth import get_current_user

@pytest.fixture
def context(monkeypatch):
    assessment = SimpleNamespace(status="in_progress")
    monkeypatch.setattr(
        interviews,
        "_require_assessment_access",
        lambda *args: (None, assessment, None),
    )
    return SimpleNamespace(
        db=Mock(spec=Session),
        organization_id=uuid4(),
        assessment_id=uuid4(),
        session_id=uuid4(),
        request_turn_id=uuid4(),
        user=SimpleNamespace(id=uuid4()),
        assessment=assessment,
    )


def validate(context):
    interviews.require_active_evidence_request(
        context.db,
        context.organization_id,
        context.assessment_id,
        context.session_id,
        context.request_turn_id,
        context.user,
    )


def test_accepts_active_evidence_request(context):
    context.db.scalar.side_effect = [
        SimpleNamespace(ended_at=None),
        uuid4(),
        SimpleNamespace(
            id=context.request_turn_id,
            speaker="agent",
            turn_type="evidence_request",
        ),
    ]

    validate(context)

    context.db.commit.assert_not_called()
    context.db.rollback.assert_not_called()


@pytest.mark.parametrize("session_exists", [False, True])
def test_rejects_missing_session_or_participation(context, session_exists):
    context.db.scalar.side_effect = (
        [SimpleNamespace(ended_at=None), None]
        if session_exists
        else [None]
    )

    with pytest.raises(HTTPException) as error:
        validate(context)

    assert error.value.status_code == 404


@pytest.mark.parametrize("ended", [False, True])
def test_rejects_inactive_interview(context, ended):
    context.assessment.status = "in_progress" if ended else "completed"
    context.db.scalar.side_effect = [
        SimpleNamespace(ended_at=object() if ended else None),
        uuid4(),
    ]

    with pytest.raises(HTTPException) as error:
        validate(context)

    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "latest",
    [None, "different_request", "participant_answer", "regular_question"],
)
def test_rejects_request_that_is_not_current(context, latest):
    turn = None
    if latest is not None:
        turn = SimpleNamespace(
            id=uuid4() if latest == "different_request" else context.request_turn_id,
            speaker="participant" if latest == "participant_answer" else "agent",
            turn_type="question" if latest == "regular_question" else "evidence_request",
        )

    context.db.scalar.side_effect = [
        SimpleNamespace(ended_at=None),
        uuid4(),
        turn,
    ]

    with pytest.raises(HTTPException) as error:
        validate(context)

    assert error.value.status_code == 409
@pytest.mark.parametrize("failure", [None, "link", "commit"])
def test_interview_upload_transaction(monkeypatch, tmp_path, failure):
    db = Mock(spec=Session)
    organization_id = uuid4()
    assessment_id = uuid4()
    session_id = uuid4()
    request_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    control = SimpleNamespace(id=uuid4())

    monkeypatch.setitem(app.dependency_overrides, get_db_session, lambda: db)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: user)
    monkeypatch.setattr(evidence, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(evidence, "_active_membership", lambda *args: object())
    monkeypatch.setattr(
        evidence, "get_assessment",
        lambda *args: SimpleNamespace(id=assessment_id),
    )

    validate_request = Mock()
    monkeypatch.setattr(
        evidence, "require_active_evidence_request", validate_request,
    )
    monkeypatch.setattr(
        evidence, "resolve_requested_evidence_control", lambda *args: control,
    )

    stored = SimpleNamespace(
        id=uuid4(),
        original_filename="mfa.txt",
        sha256="synthetic-hash",
    )
    store = Mock(return_value=stored)
    link = Mock(return_value=(object(), True))
    if failure == "link":
        link.side_effect = RuntimeError("Simulated linking failure")
    if failure == "commit":
        db.commit.side_effect = RuntimeError("Simulated commit failure")

    monkeypatch.setattr(evidence, "store_evidence_file", store)
    monkeypatch.setattr(evidence, "link_evidence_to_control", link)

    response = TestClient(app).post(
        "/api/v1/evidence/",
        data={
            "organization_id": str(organization_id),
            "assessment_id": str(assessment_id),
            "interview_session_id": str(session_id),
            "evidence_request_turn_id": str(request_id),
        },
        files={"file": ("mfa.txt", b"Synthetic MFA policy.", "text/plain")},
    )

    validate_request.assert_called_once_with(
        db, organization_id, assessment_id, session_id, request_id, user,
    )
    assert store.call_args.kwargs["commit"] is False
    link.assert_called_once_with(
        db, organization_id, stored.id, control.id, user.id, commit=False,
    )

    if failure is None:
        assert response.status_code == 200
        db.commit.assert_called_once()
        db.rollback.assert_not_called()
        assert len(list(tmp_path.iterdir())) == 1
    else:
        assert response.status_code == 500
        db.rollback.assert_called_once()
        assert list(tmp_path.iterdir()) == []
        if failure == "link":
            db.commit.assert_not_called()
        else:
            db.commit.assert_called_once()