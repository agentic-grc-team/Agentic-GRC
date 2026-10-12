"""Integration tests for decision traces on a real PostgreSQL database (AGRC-27).

They run in CI against a temporary database. Locally they are skipped unless
backend/.env points to a database with the migrations applied.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import DecisionTraceRecord, Organization, User
from app.db.session import get_engine
from app.schemas.decision_trace import DecisionTrace
from app.services.decision_traces import list_traces, record_trace


@pytest.fixture
def db():
    """A session inside a transaction that is rolled back after each test, so nothing is left behind."""
    try:
        engine = get_engine()
        connection = engine.connect()
    except (OSError, SQLAlchemyError, RuntimeError):
        pytest.skip("PostgreSQL is unavailable for integration tests.")
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def make_organization(db: Session) -> Organization:
    organization = Organization(name=f"Test org {uuid.uuid4()}", sector_code="other", size_code="unknown")
    db.add(organization)
    db.commit()
    return organization


def make_user(db: Session) -> User:
    """A consultant profile. Every profile needs a Supabase auth.users row (stubbed in CI)."""
    user_id = uuid.uuid4()
    email = f"consultant-{user_id}@example.com"
    now = datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, "
            "raw_app_meta_data, raw_user_meta_data, created_at, updated_at) "
            "VALUES (:id, 'authenticated', 'authenticated', :email, '', :now, '{}'::jsonb, '{}'::jsonb, :now, :now)"
        ),
        {"id": user_id, "email": email, "now": now},
    )
    user = User(id=user_id, email=email)
    db.add(user)
    db.commit()
    return user


def make_trace(organization_id, assessment_id, **changes) -> DecisionTrace:
    fields = {
        "organization_id": organization_id,
        "assessment_id": assessment_id,
        "decision_type": "status_assessed",
        "control_ids": ["PR.AA-03"],
        "module": "Access",
        "sources": [{"type": "interview_turn", "ref": "interview_turn:1", "excerpt": "No MFA for admins."}],
        "actor_type": "agent",
        "prompt_id": "rule:close-on-no",
        "prompt_version": "0.1.0",
        "kb_version": "csf2.0-kb-0.1",
        "output": {"status": "not_implemented"},
        "rationale": "The participant said MFA is not enforced for admins.",
        "confidence": 0.85,
    }
    fields.update(changes)
    return DecisionTrace(**fields)


# --- persistence --------------------------------------------------------------

def test_recorded_trace_is_stored_with_all_fields(db):
    # Arrange
    organization = make_organization(db)
    assessment_id = uuid.uuid4()

    # Act
    record = record_trace(db, make_trace(organization.id, assessment_id))

    # Assert
    assert record.id is not None
    assert record.created_at is not None
    assert record.control_ids == ["PR.AA-03"]
    assert record.sources[0]["ref"] == "interview_turn:1"
    assert float(record.confidence) == 0.85
    assert record.fallback_used is False


def test_trace_is_readable_from_a_new_session(db):
    organization = make_organization(db)
    assessment_id = uuid.uuid4()
    saved = record_trace(db, make_trace(organization.id, assessment_id))

    with Session(bind=db.connection()) as new_session:
        traces = list_traces(new_session, organization.id, assessment_id)

    assert [trace.id for trace in traces] == [saved.id]


def test_traces_are_listed_oldest_first(db):
    organization = make_organization(db)
    assessment_id = uuid.uuid4()
    first = record_trace(db, make_trace(organization.id, assessment_id, decision_type="answer_interpreted",
                                        prompt_id="interpret_answer", model_name="llama3.1:8b"))
    second = record_trace(db, make_trace(organization.id, assessment_id))

    traces = list_traces(db, organization.id, assessment_id)

    assert [trace.id for trace in traces] == [first.id, second.id]


# --- organization isolation ---------------------------------------------------

def test_traces_of_another_organization_are_not_listed(db):
    organization_a = make_organization(db)
    organization_b = make_organization(db)
    assessment_id = uuid.uuid4()
    record_trace(db, make_trace(organization_a.id, assessment_id))

    traces_for_b = list_traces(db, organization_b.id, assessment_id)

    assert traces_for_b == []


def test_trace_for_unknown_organization_is_rejected(db):
    with pytest.raises(IntegrityError):
        record_trace(db, make_trace(uuid.uuid4(), uuid.uuid4()))


# --- append-only --------------------------------------------------------------

def test_update_of_a_trace_is_rejected(db):
    organization = make_organization(db)
    record = record_trace(db, make_trace(organization.id, uuid.uuid4()))

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE decision_traces SET rationale = 'changed' WHERE id = :id"), {"id": record.id})


def test_delete_of_a_trace_is_rejected(db):
    organization = make_organization(db)
    record = record_trace(db, make_trace(organization.id, uuid.uuid4()))

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM decision_traces WHERE id = :id"), {"id": record.id})


def test_truncate_of_traces_is_rejected(db):
    organization = make_organization(db)
    record_trace(db, make_trace(organization.id, uuid.uuid4()))

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("TRUNCATE decision_traces"))


# --- transactions -------------------------------------------------------------

def test_record_trace_leaves_commit_to_caller(db):
    organization = make_organization(db)
    assessment_id = uuid.uuid4()
    record_trace(db, make_trace(organization.id, assessment_id))

    db.rollback()

    assert list_traces(db, organization.id, assessment_id) == []


# --- references between traces (reviews and replacements) ---------------------

def make_review(organization_id, assessment_id, reviewed_trace_id, reviewer: User) -> DecisionTrace:
    return make_trace(
        organization_id, assessment_id,
        decision_type="human_review", actor_type="aligo_consultant", actor_user_id=reviewer.id,
        sources=[], prompt_id=None, prompt_version=None, model_name=None, confidence=None,
        reviews_trace_id=reviewed_trace_id, review_outcome="accepted",
        output={}, rationale="Agrees with the agent.",
    )


def test_review_of_trace_in_same_assessment_is_accepted(db):
    organization = make_organization(db)
    assessment_id = uuid.uuid4()
    reviewed = record_trace(db, make_trace(organization.id, assessment_id))

    review = record_trace(db, make_review(organization.id, assessment_id, reviewed.id, make_user(db)))

    assert review.reviews_trace_id == reviewed.id


def test_review_of_trace_from_another_organization_is_rejected(db):
    organization_a = make_organization(db)
    organization_b = make_organization(db)
    assessment_id = uuid.uuid4()
    reviewed = record_trace(db, make_trace(organization_a.id, assessment_id))

    with pytest.raises(IntegrityError, match="reviews_same_assessment"):
        record_trace(db, make_review(organization_b.id, assessment_id, reviewed.id, make_user(db)))


def test_review_of_trace_from_another_assessment_is_rejected(db):
    organization = make_organization(db)
    reviewed = record_trace(db, make_trace(organization.id, uuid.uuid4()))

    with pytest.raises(IntegrityError, match="reviews_same_assessment"):
        record_trace(db, make_review(organization.id, uuid.uuid4(), reviewed.id, make_user(db)))


def test_replacement_of_trace_from_another_organization_is_rejected(db):
    organization_a = make_organization(db)
    organization_b = make_organization(db)
    assessment_id = uuid.uuid4()
    old = record_trace(db, make_trace(organization_a.id, assessment_id))

    with pytest.raises(IntegrityError, match="supersedes_same_assessment"):
        record_trace(db, make_trace(organization_b.id, assessment_id, supersedes_trace_id=old.id))


def test_replacement_of_trace_from_another_assessment_is_rejected(db):
    organization = make_organization(db)
    old = record_trace(db, make_trace(organization.id, uuid.uuid4()))

    with pytest.raises(IntegrityError, match="supersedes_same_assessment"):
        record_trace(db, make_trace(organization.id, uuid.uuid4(), supersedes_trace_id=old.id))


# --- database rules (second line of defence behind Pydantic) -----------------

def test_database_rejects_human_decision_without_user(db):
    organization = make_organization(db)
    row = DecisionTraceRecord(
        organization_id=organization.id,
        assessment_id=uuid.uuid4(),
        decision_type="status_assessed",
        actor_type="aligo_consultant",
        kb_version="csf2.0-kb-0.1",
        output={"status": "implemented"},
        rationale="No user recorded.",
    )
    db.add(row)

    with pytest.raises(IntegrityError, match="actor_user_matches_type"):
        db.flush()


def test_database_rejects_llm_decision_without_model(db):
    organization = make_organization(db)
    row = DecisionTraceRecord(
        organization_id=organization.id,
        assessment_id=uuid.uuid4(),
        decision_type="answer_interpreted",
        sources=[{"type": "interview_turn", "ref": "interview_turn:1"}],
        actor_type="agent",
        prompt_id="interpret_answer",
        prompt_version="0.2.0",
        kb_version="csf2.0-kb-0.1",
        output={},
        rationale="Missing model name.",
    )
    db.add(row)

    with pytest.raises(IntegrityError, match="llm_has_model"):
        db.flush()


def test_database_rejects_unknown_decision_type(db):
    organization = make_organization(db)
    row = DecisionTraceRecord(
        organization_id=organization.id,
        assessment_id=uuid.uuid4(),
        decision_type="guessed",
        actor_type="aligo_consultant",
        actor_user_id=make_user(db).id,
        kb_version="csf2.0-kb-0.1",
        output={},
        rationale="Unknown type.",
    )
    db.add(row)

    with pytest.raises(IntegrityError, match="decision_type"):
        db.flush()
