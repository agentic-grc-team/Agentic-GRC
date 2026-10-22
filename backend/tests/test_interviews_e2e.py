"""Authenticated interview API round-trip against the testing PostgreSQL database."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from agentic_grc_agent.llm import FakeLLM
from agentic_grc_agent.schemas import AnswerCategory, AnswerInterpretation, Intent
from app.api.v1.dependencies import get_db_session
from app.db.models import InterviewTurn
from app.db.session import get_engine
from app.main import app
from app.security import auth as auth_module
from app.security.supabase import SupabaseIdentity
from app.services.langgraph_checkpointer import open_interview_checkpointer
from tests.test_assessments_db import make_control
from tests.test_expert_review_db import make_assessment_context


@pytest.fixture
def interview_api(monkeypatch):
    """Use the configured test DB in a rollback transaction and a deterministic model."""
    try:
        connection = get_engine().connect()
    except (OSError, SQLAlchemyError, RuntimeError):
        pytest.skip("PostgreSQL is unavailable for interview API integration tests.")

    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    organization, user, assessment, control = make_assessment_context(db)
    make_control(
        db,
        organization,
        assessment,
        control_code="PR.AA-05",
        in_scope=True,
    )
    make_control(
        db,
        organization,
        assessment,
        control_code="PR.AA-01",
        in_scope=False,
        scope_rationale="Outside the synthetic interview test scope.",
    )

    fake_llm = FakeLLM(
        {
            "interpret_answer": lambda _user: AnswerInterpretation(
                intent=Intent.answer,
                category=AnswerCategory.no,
                summary="The control is not implemented.",
                rationale="The participant says the control is not in place.",
                confidence=0.92,
                key_quote="No, never",
            )
        }
    )
    monkeypatch.setattr(
        "agentic_grc_agent.llm.OllamaLLM",
        lambda *_args, **_kwargs: fake_llm,
    )
    monkeypatch.setattr(
        auth_module,
        "get_verified_identity",
        lambda token, _settings: SupabaseIdentity(
            id=user.id,
            email=user.email,
            email_verified=(token == "synthetic-test-token"),
        ),
    )

    saved_overrides = dict(app.dependency_overrides)
    # Some legacy test modules install module-level overrides. Exercise the real
    # bearer-auth dependency here, with get_verified_identity stubbed above.
    app.dependency_overrides.pop(auth_module.get_current_user, None)
    app.dependency_overrides[get_db_session] = lambda: db
    thread_ids: list[uuid.UUID] = []
    try:
        yield TestClient(app), organization, user, assessment, control, thread_ids, fake_llm, db
    finally:
        try:
            if thread_ids:
                with open_interview_checkpointer() as checkpointer:
                    for thread_id in thread_ids:
                        checkpointer.delete_thread(str(thread_id))
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(saved_overrides)
            db.close()
            transaction.rollback()
            connection.close()


def test_authenticated_interview_persists_agent_turns_and_resumes(interview_api):
    client, organization, _user, assessment, control, thread_ids, fake_llm, db = interview_api
    auth = {"Authorization": "Bearer synthetic-test-token"}
    base = (
        f"/api/v1/organizations/{organization.id}"
        f"/assessments/{assessment.id}/interview"
    )

    assert client.post(base, json={"session_type": "kickoff"}).status_code == 401
    assert client.get(
        f"/api/v1/organizations/{uuid.uuid4()}"
        f"/assessments/{assessment.id}/interview",
        headers=auth,
    ).status_code == 404

    opened = client.post(base, headers=auth, json={"session_type": "kickoff"})
    assert opened.status_code == 201, opened.text
    opened_body = opened.json()
    assert opened_body["organization_id"] == str(organization.id)
    assert opened_body["assessment_id"] == str(assessment.id)
    assert [item["code"] for item in opened_body["in_scope_controls"]] == [
        "PR.AA-03",
        "PR.AA-05",
    ]
    assert len(opened_body["turns"]) == 1
    first_question = opened_body["turns"][0]
    assert first_question["speaker"] == "agent"
    assert first_question["turn_type"] == "question"
    thread_id = uuid.UUID(opened_body["session"]["id"])
    thread_ids.append(thread_id)

    request_id = uuid.uuid4()
    answer_body = {
        "session_id": str(thread_id),
        "content": "No, never",
        "question_id": first_question["question_id"],
        "replies_to_turn_id": first_question["id"],
        "client_request_id": str(request_id),
    }
    answered = client.post(f"{base}/turns", headers=auth, json=answer_body)
    assert answered.status_code == 201, answered.text
    receipt = answered.json()
    assert receipt["idempotent_replay"] is False
    assert receipt["turn"]["speaker"] == "participant"
    assert receipt["turn"]["content"] == "No, never"
    assert receipt["agent_turns"]
    assert receipt["draft_results"]
    draft = receipt["draft_results"][0]
    assert draft["assessment_control_id"] == str(control.id)
    assert draft["status"] == "not_implemented"
    assert draft["confidence"] == pytest.approx(0.92)
    assert draft["requires_human_review"] is False
    assert draft["evidence_pending"] is False
    assert draft["trace_id"]
    assert "interpret_answer" in [prompt_id for prompt_id, _ in fake_llm.calls]

    restored = client.get(base, headers=auth, params={"session_id": str(thread_id)})
    assert restored.status_code == 200, restored.text
    restored_body = restored.json()
    assert restored_body["session"]["id"] == str(thread_id)
    assert [turn["id"] for turn in restored_body["turns"]] == [
        first_question["id"],
        receipt["turn"]["id"],
        *[turn["id"] for turn in receipt["agent_turns"]],
    ]
    restored_answer = next(
        turn for turn in restored_body["turns"] if turn["speaker"] == "participant"
    )
    assert restored_answer["source_references"] == [
        {
            "type": "interview_turn",
            "ref": f"interview_turn:{restored_answer['id']}",
        }
    ]

    replay = client.post(f"{base}/turns", headers=auth, json=answer_body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["turn"]["id"] == receipt["turn"]["id"]

    resumed = client.post(base, headers=auth, json={"session_type": "kickoff"})
    assert resumed.status_code == 200, resumed.text
    resumed_body = resumed.json()
    assert resumed_body["resumed"] is True
    assert resumed_body["session"]["id"] == str(thread_id)
    assert [turn["id"] for turn in resumed_body["turns"]] == [
        turn["id"] for turn in restored_body["turns"]
    ]
    assert len(
        [turn for turn in resumed_body["turns"] if turn["speaker"] == "participant"]
    ) == 1
    assert len(fake_llm.calls) == 1

    db_turns = list(
        db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == thread_id)
            .order_by(InterviewTurn.sequence_no)
        )
    )
    assert len(db_turns) == len(resumed_body["turns"])
    assert db_turns[1].speaker == "participant"
    assert str(db_turns[1].participant_id) == resumed_body["participant_id"]
