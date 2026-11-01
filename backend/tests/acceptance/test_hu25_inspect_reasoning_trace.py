"""Acceptance tests for HU-25 — Inspect reasoning traces and source references (Jira AGRC-82, task AGRC-65).

User story: As an authorized administrator or expert reviewer, I want to inspect the reasoning trace and
source references for an assessment result in the correct organization context, so that I can understand
how the agent produced a draft and verify its provenance before relying on it.

Each test is one acceptance criterion of HU-25, written as Given / When / Then. They run through the HTTP
API against PostgreSQL: the assessment is created through the API, a representative answers the interview
and the agent saves a draft result with its decision trace. Only the Supabase login is replaced by a fixed
user and the language model by a deterministic fake. Results are recorded in docs/testing/acceptance-tests.md.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.llm import FakeLLM
from app.agent.schemas import AnswerCategory, AnswerInterpretation, Intent
from app.api.v1.dependencies import get_db_session
from app.db.models import AssessmentControl, ControlResult, InterviewTurn, OrganizationMembership
from app.db.session import get_engine
from app.main import app
from app.security.auth import get_current_user
from app.services.langgraph_checkpointer import (
    initialize_interview_checkpointer,
    open_interview_checkpointer,
)
from tests.test_assessments_db import make_organization, make_user
from tests.test_expert_review_db import make_result

ANSWER = "No, we have never enforced it."


@pytest.fixture
def db():
    """A session inside a transaction that is rolled back after each test, so nothing is left behind."""
    try:
        engine = get_engine()
        connection = engine.connect()
    except (OSError, SQLAlchemyError, RuntimeError):
        pytest.skip("PostgreSQL is unavailable for acceptance tests.")
    initialize_interview_checkpointer()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def api(db, monkeypatch):
    """HTTP client on the real app and database. `api.login(user)` sets who is calling."""
    fake_llm = FakeLLM(
        {
            "interpret_answer": lambda _user: AnswerInterpretation(
                intent=Intent.answer,
                category=AnswerCategory.no,
                summary="The control is not implemented.",
                rationale="The participant says the control has never been in place.",
                confidence=0.92,
                key_quote=ANSWER,
            )
        }
    )
    monkeypatch.setattr("app.agent.llm.OllamaLLM", lambda *_args, **_kwargs: fake_llm)
    monkeypatch.setitem(app.dependency_overrides, get_db_session, lambda: db)
    client = TestClient(app)
    client.thread_ids = []

    def login(user, platform_admin=False):
        signed_in = SimpleNamespace(id=user.id, email=user.email, is_platform_admin=platform_admin)
        monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: signed_in)

    client.login = login
    yield client
    if client.thread_ids:
        with open_interview_checkpointer() as checkpointer:
            for thread_id in client.thread_ids:
                checkpointer.delete_thread(str(thread_id))


def member(db, organization, role, status="active"):
    user = make_user(db)
    db.add(OrganizationMembership(organization_id=organization.id, user_id=user.id, role=role, status=status))
    db.commit()
    return user


def agent_draft(db, api):
    """An assessment created through the API whose first question was answered in the interview.

    Returns the organization, its consultant, its representative, the assessment and the result
    the expert opens in Expert reviews, plus the participant's interview turn.
    """
    organization = make_organization(db)
    consultant = member(db, organization, "consultant")
    representative = member(db, organization, "representative")

    api.login(consultant)
    assessment = api.post(
        f"/api/v1/organizations/{organization.id}/assessments", json={"title": "Q4 identity review"}
    ).json()
    interview_url = f"/api/v1/organizations/{organization.id}/assessments/{assessment['id']}/interview"

    api.login(representative)
    opened = api.post(interview_url, json={"session_type": "kickoff"})
    assert opened.status_code == 201, opened.text
    session_id = opened.json()["session"]["id"]
    api.thread_ids.append(session_id)
    question = opened.json()["turns"][0]
    answered = api.post(
        f"{interview_url}/turns",
        json={
            "session_id": session_id,
            "content": ANSWER,
            "question_id": question["question_id"],
            "replies_to_turn_id": question["id"],
            "client_request_id": str(uuid.uuid4()),
        },
    )
    assert answered.status_code == 201, answered.text
    participant_turn = answered.json()["turn"]

    api.login(consultant)
    pending = api.get("/api/v1/expert-reviews/pending")
    assert pending.status_code == 200, pending.text
    (item,) = [entry for entry in pending.json() if entry["assessment_id"] == assessment["id"]]
    return SimpleNamespace(
        organization=organization,
        consultant=consultant,
        representative=representative,
        assessment=assessment,
        item=item,
        participant_turn=participant_turn,
    )


def trace_url(result_id):
    return f"/api/v1/expert-reviews/{result_id}/trace"


def test_hu25_ac1_result_context_is_identifiable(db, api):
    """AC 1
    Given an authorized administrator or expert opens a result,
    when the trace view is selected,
    then the assessment, control, result version, and organization context are identifiable.
    """
    draft = agent_draft(db, api)
    platform_admin = make_user(db)

    for user, is_platform_admin in ((draft.consultant, False), (platform_admin, True)):
        api.login(user, platform_admin=is_platform_admin)
        response = api.get(trace_url(draft.item["result_id"]))

        assert response.status_code == 200, response.text
        view = response.json()
        assert view["result_id"] == draft.item["result_id"]
        assert view["organization_id"] == str(draft.organization.id)
        assert view["organization_name"] == draft.organization.name
        assert view["assessment_id"] == draft.assessment["id"]
        assert view["assessment_title"] == "Q4 identity review"
        assert view["control_code"] == draft.item["control_code"]
        assert view["control_title"] == draft.item["control_title"]
        assert view["result_version"] == 1
        assert view["result_author"] == "agent"

    # After the expert corrects the draft, the trace view identifies the new version and its author.
    api.login(draft.consultant)
    decision = api.post(
        f"/api/v1/expert-reviews/{draft.item['result_id']}/decision",
        json={
            "outcome": "modified",
            "comment": "Only part of the accounts are covered.",
            "modified_result": {"control_status": "partially_implemented", "explanation": "MFA covers admins only."},
        },
    )
    assert decision.status_code == 200, decision.text
    original = db.get(ControlResult, uuid.UUID(draft.item["result_id"]))
    new_result_id = db.scalar(
        select(ControlResult.id).where(
            ControlResult.assessment_control_id == original.assessment_control_id,
            ControlResult.version_no == 2,
        )
    )

    corrected = api.get(trace_url(new_result_id)).json()
    assert corrected["result_version"] == 2
    assert corrected["result_author"] == "aligo_consultant"
    assert corrected["assessment_id"] == draft.assessment["id"]
    assert corrected["control_code"] == draft.item["control_code"]


def test_hu25_ac2_trace_steps_and_source_references_are_shown(db, api):
    """AC 2
    Given a trace is available,
    when the authorized reviewer opens it,
    then the view shows the trace steps and source references linked to the result.
    """
    draft = agent_draft(db, api)

    api.login(draft.consultant)
    view = api.get(trace_url(draft.item["result_id"])).json()

    steps = view["steps"]
    assert steps, "an agent result must come with its recorded decisions"
    assert all(draft.item["control_code"] in step["control_ids"] for step in steps)
    assert all(step["assessment_id"] == draft.assessment["id"] for step in steps)
    created = [step["created_at"] for step in steps]
    assert created == sorted(created)

    # The decision that produced this result is one of the steps.
    own_decision = next(step for step in steps if step["id"] == view["result_trace_id"])
    assert own_decision["decision_type"] == "status_assessed"
    assert own_decision["output"]["status"] == draft.item["control_status"]

    # Its source reference leads back to the participant's own answer in the interview.
    expected_ref = f"interview_turn:{draft.participant_turn['id']}"
    assert expected_ref in [source["ref"] for source in own_decision["sources"]]
    turn = db.scalar(select(InterviewTurn).where(InterviewTurn.id == uuid.UUID(draft.participant_turn["id"])))
    assert turn.content == ANSWER
    assert str(turn.organization_id) == view["organization_id"]


def test_hu25_ac3_no_trace_gives_an_unavailable_state_and_nothing_is_invented(db, api):
    """AC 3
    Given no trace exists or trace loading fails,
    when the view is opened,
    then the user sees a clear unavailable state and the system does not display a fabricated trace.
    """
    draft = agent_draft(db, api)
    # A second control of the same assessment with a result that has no recorded decision behind it.
    control = db.scalar(
        select(AssessmentControl).where(
            AssessmentControl.assessment_id == uuid.UUID(draft.assessment["id"]),
            AssessmentControl.control_code != draft.item["control_code"],
        )
    )
    untraced = make_result(db, draft.organization, control, trace_id=None)

    api.login(draft.consultant)
    response = api.get(trace_url(untraced.id))

    assert response.status_code == 200, response.text
    view = response.json()
    assert view["control_code"] == control.control_code
    assert view["result_trace_id"] is None
    # The other control's decisions are not borrowed to fill the empty trace.
    assert view["steps"] == []

    # A result that does not exist is reported as not found, not as an empty trace.
    missing = api.get(trace_url(uuid.uuid4()))
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Review result not found."}


def test_hu25_ac4_users_without_access_get_no_trace_data(db, api):
    """AC 4
    Given the user lacks access to the organization or assessment,
    when they request a trace or export,
    then access is denied and trace data is not disclosed.
    """
    draft = agent_draft(db, api)
    api.login(draft.consultant)
    trace_ids = [step["id"] for step in api.get(trace_url(draft.item["result_id"])).json()["steps"]]
    assert trace_ids

    other_organization = make_organization(db)
    outsider = member(db, other_organization, "consultant")
    suspended = member(db, draft.organization, "consultant", status="suspended")
    assessment_traces = (
        f"/api/v1/organizations/{draft.organization.id}/assessments/{draft.assessment['id']}/traces"
    )
    # The outsider's own organization with this assessment's id: the filter is by organization too.
    cross_traces = f"/api/v1/organizations/{other_organization.id}/assessments/{draft.assessment['id']}/traces"

    denied = {
        outsider: 404,
        suspended: 404,
        draft.representative: 403,  # HU-03: representatives do not see the agent's internal traces
    }
    for user, expected_status in denied.items():
        api.login(user)
        for url in (trace_url(draft.item["result_id"]), assessment_traces, f"{assessment_traces}/export"):
            response = api.get(url)
            assert response.status_code == expected_status, (url, response.text)
            for trace_id in trace_ids:
                assert trace_id not in response.text
            assert ANSWER not in response.text

    api.login(outsider)
    for url in (cross_traces, f"{cross_traces}/export"):
        response = api.get(url)
        assert response.status_code == 200
        for trace_id in trace_ids:
            assert trace_id not in response.text
    assert api.get(cross_traces).json() == []
    assert api.get(f"{cross_traces}/export").json()["trace_count"] == 0
