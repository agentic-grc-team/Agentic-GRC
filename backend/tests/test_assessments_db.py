"""Integration tests for assessments, controls, results and reviews on a real PostgreSQL database (AGRC-61).

They run in CI against a temporary database. Locally they are skipped unless
backend/.env points to a database with the migrations applied.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    Assessment,
    AssessmentControl,
    ControlResult,
    ControlResultReview,
    DecisionTraceRecord,
    Organization,
    User,
)
from app.db.session import get_engine
from app.schemas.assessments import AssessmentCreate
from app.services.assessments import get_assessment, list_assessments, start_assessment


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


def make_assessment(db: Session, organization: Organization, **changes) -> Assessment:
    fields = {
        "organization_id": organization.id,
        "title": f"Test assessment {uuid.uuid4()}",
        "framework_code": "NIST-CSF",
        "framework_version": "2.0",
        "kb_version": "demo-0.2",
        "status": "in_progress",
        "started_at": datetime.now(timezone.utc),
    }
    fields.update(changes)
    assessment = Assessment(**fields)
    db.add(assessment)
    db.commit()
    return assessment


def make_control(db: Session, organization: Organization, assessment: Assessment, **changes) -> AssessmentControl:
    fields = {
        "organization_id": organization.id,
        "assessment_id": assessment.id,
        "control_code": "PR.AA-03",
        "control_title": "Identities and credentials are managed",
        "in_scope": True,
        "scope_rationale": None,
    }
    fields.update(changes)
    control = AssessmentControl(**fields)
    db.add(control)
    db.commit()
    return control


def make_result(db: Session, organization: Organization, control: AssessmentControl, **changes) -> ControlResult:
    fields = {
        "organization_id": organization.id,
        "assessment_id": control.assessment_id,
        "assessment_control_id": control.id,
        "version_no": 1,
        "based_on_result_id": None,
        "author_actor": "agent",
        "author_user_id": None,
        "control_status": "partially_implemented",
        "explanation": "MFA is partially implemented across systems.",
        "confidence": 0.8,
        "requires_human_review": False,
        "evidence_pending": False,
        "evidence_summary": "Some systems enforce MFA, others do not.",
        "evidence_refs": [{"source_type": "document_span", "reference": "doc:1", "excerpt": "MFA used", "nature": "implementation"}],
    }
    fields.update(changes)
    result = ControlResult(**fields)
    db.add(result)
    db.commit()
    return result


def make_trace(db: Session, organization: Organization, assessment: Assessment, **changes) -> DecisionTraceRecord:
    fields = {
        "organization_id": organization.id,
        "assessment_id": assessment.id,
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
    trace = DecisionTraceRecord(**fields)
    db.add(trace)
    db.commit()
    return trace


# --- assessments --------------------------------------------------------------

def test_start_assessment_stores_all_fields(db):
    organization = make_organization(db)
    user = make_user(db)
    data = AssessmentCreate(title="Test Assessment", kb_version="demo-0.2")

    assessment = start_assessment(db, organization.id, user.id, data)

    assert assessment.id is not None
    assert assessment.organization_id == organization.id
    assert assessment.created_by_user_id == user.id
    assert assessment.title == "Test Assessment"
    assert assessment.status == "in_progress"
    assert assessment.started_at is not None
    assert assessment.framework_code == "NIST-CSF"
    assert assessment.framework_version == "2.0"
    assert assessment.kb_version == "demo-0.2"


def test_list_assessments_returns_only_organization_newest_first(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    # Explicit times: the whole test runs in one transaction, where now() (the created_at default)
    # returns the same value for every row, so the order would fall back to the random ids.
    created = datetime.now(timezone.utc)
    first_a = make_assessment(db, org_a, title="First A", created_at=created)
    second_a = make_assessment(db, org_a, title="Second A", created_at=created + timedelta(seconds=1))
    make_assessment(db, org_b, title="B Assessment")

    listed = list_assessments(db, org_a.id)

    assert [a.id for a in listed] == [second_a.id, first_a.id]


def test_get_assessment_with_other_org_id_returns_none(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    assessment_a = make_assessment(db, org_a)

    assert get_assessment(db, org_b.id, assessment_a.id) is None
    assert get_assessment(db, org_a.id, assessment_a.id) is not None


def test_unknown_assessment_status_rejected(db):
    org = make_organization(db)
    assessment = Assessment(
        organization_id=org.id,
        title="Bad Status",
        kb_version="demo-0.2",
        status="invalid_status",
    )
    db.add(assessment)
    with pytest.raises(IntegrityError, match="ck_assessments_status"):
        db.commit()


def test_completed_assessment_without_completed_at_rejected(db):
    org = make_organization(db)
    assessment = Assessment(
        organization_id=org.id,
        title="Completed without date",
        kb_version="demo-0.2",
        status="completed",
        completed_at=None,
    )
    db.add(assessment)
    with pytest.raises(IntegrityError, match="ck_assessments_completed_at"):
        db.commit()


def test_completed_at_before_started_at_rejected(db):
    org = make_organization(db)
    now = datetime.now(timezone.utc)
    assessment = Assessment(
        organization_id=org.id,
        title="Bad dates",
        kb_version="demo-0.2",
        status="completed",
        started_at=now,
        completed_at=now.replace(year=now.year - 1),
    )
    db.add(assessment)
    with pytest.raises(IntegrityError, match="ck_assessments_dates_order"):
        db.commit()


# --- trace FK -----------------------------------------------------------------

def test_trace_for_assessment_of_same_organization_accepted(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    trace = make_trace(db, org, assessment)
    assert trace.id is not None


def test_trace_for_nonexistent_assessment_rejected(db):
    org = make_organization(db)
    non_existent_assessment_id = uuid.uuid4()
    trace = DecisionTraceRecord(
        organization_id=org.id,
        assessment_id=non_existent_assessment_id,
        decision_type="status_assessed",
        control_ids=["PR.AA-03"],
        sources=[{"type": "interview_turn", "ref": "t:1"}],
        actor_type="agent",
        prompt_id="rule:test",
        prompt_version="1.0",
        kb_version="demo-0.2",
        output={"status": "not_implemented"},
        rationale="Test",
    )
    db.add(trace)
    with pytest.raises(IntegrityError, match="assessment_same_org"):
        db.commit()


def test_trace_with_mismatched_organization_assessment_rejected(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    assessment_b = make_assessment(db, org_b)
    trace = DecisionTraceRecord(
        organization_id=org_a.id,
        assessment_id=assessment_b.id,
        decision_type="status_assessed",
        control_ids=["PR.AA-03"],
        sources=[{"type": "interview_turn", "ref": "t:1"}],
        actor_type="agent",
        prompt_id="rule:test",
        prompt_version="1.0",
        kb_version="demo-0.2",
        output={"status": "not_implemented"},
        rationale="Test",
    )
    db.add(trace)
    with pytest.raises(IntegrityError, match="assessment_same_org"):
        db.commit()


# --- assessment controls ------------------------------------------------------

def test_assessment_control_stored_and_duplicate_code_rejected(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment, control_code="PR.AA-03")
    assert control.id is not None

    dup_control = AssessmentControl(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_code="PR.AA-03",
        control_title="Duplicate control",
        in_scope=True,
    )
    db.add(dup_control)
    with pytest.raises(IntegrityError, match="uq_assessment_controls_assessment_code"):
        db.commit()


def test_invalid_control_code_format_rejected(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = AssessmentControl(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_code="PRAA03",
        control_title="Invalid code format",
        in_scope=True,
    )
    db.add(control)
    with pytest.raises(IntegrityError, match="control_code_format"):
        db.commit()


def test_out_of_scope_without_rationale_rejected(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = AssessmentControl(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_code="PR.AA-01",
        control_title="No rationale",
        in_scope=False,
        scope_rationale=None,
    )
    db.add(control)
    with pytest.raises(IntegrityError, match="ck_assessment_controls_scope_rationale"):
        db.commit()


def test_control_with_mismatched_organization_assessment_rejected(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    assessment_a = make_assessment(db, org_a)
    control = AssessmentControl(
        organization_id=org_b.id,
        assessment_id=assessment_a.id,
        control_code="PR.AA-02",
        control_title="Mismatched org",
        in_scope=True,
    )
    db.add(control)
    with pytest.raises(IntegrityError, match="assessment_same_org"):
        db.commit()


# --- control results ----------------------------------------------------------

def test_agent_result_stored_with_evidence_refs_roundtrip(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    ref = [{"source_type": "document_span", "reference": "doc:42", "excerpt": "MFA logs", "nature": "implementation"}]
    result = make_result(db, org, control, evidence_refs=ref)
    assert result.id is not None
    assert result.evidence_refs == ref


def test_duplicate_result_version_for_same_control_rejected(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    make_result(db, org, control, version_no=1)

    dup_result = ControlResult(
        organization_id=org.id,
        assessment_id=control.assessment_id,
        assessment_control_id=control.id,
        version_no=1,
        author_actor="agent",
        control_status="implemented",
        explanation="Second version 1",
    )
    db.add(dup_result)
    with pytest.raises(IntegrityError, match="uq_control_results_control_version"):
        db.commit()


def test_not_applicable_without_justification_rejected(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    result = ControlResult(
        organization_id=org.id,
        assessment_id=control.assessment_id,
        assessment_control_id=control.id,
        version_no=1,
        author_actor="agent",
        control_status="not_applicable",
        explanation="N/A",
        justification=None,
    )
    db.add(result)
    with pytest.raises(IntegrityError, match="not_applicable_justified"):
        db.commit()


def test_not_assessed_without_reason_rejected(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    result = ControlResult(
        organization_id=org.id,
        assessment_id=control.assessment_id,
        assessment_control_id=control.id,
        version_no=1,
        author_actor="agent",
        control_status="not_assessed",
        explanation="Not assessed yet",
        not_assessed_reason=None,
    )
    db.add(result)
    with pytest.raises(IntegrityError, match="not_assessed_reason"):
        db.commit()


def test_consultant_result_without_user_rejected(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    result = ControlResult(
        organization_id=org.id,
        assessment_id=control.assessment_id,
        assessment_control_id=control.id,
        version_no=1,
        author_actor="aligo_consultant",
        author_user_id=None,
        control_status="implemented",
        explanation="No user id",
    )
    db.add(result)
    with pytest.raises(IntegrityError, match="author_user_matches_actor"):
        db.commit()


def test_maturity_current_out_of_range_rejected(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    result = ControlResult(
        organization_id=org.id,
        assessment_id=control.assessment_id,
        assessment_control_id=control.id,
        version_no=1,
        author_actor="agent",
        control_status="implemented",
        explanation="Maturity 6",
        maturity_current=6,
    )
    db.add(result)
    with pytest.raises(IntegrityError, match="ck_control_results_maturity_current_range"):
        db.commit()


def test_control_result_update_and_delete_rejected_by_trigger(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    result = make_result(db, org, control)

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE control_results SET explanation='x' WHERE id = :id"), {"id": result.id})

    db.rollback()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM control_results WHERE id = :id"), {"id": result.id})


def test_result_with_mismatched_organization_control_rejected(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    assessment_a = make_assessment(db, org_a)
    assessment_b = make_assessment(db, org_b)
    control_a = make_control(db, org_a, assessment_a)

    result = ControlResult(
        organization_id=org_b.id,
        assessment_id=assessment_b.id,
        assessment_control_id=control_a.id,
        version_no=1,
        author_actor="agent",
        control_status="implemented",
        explanation="Mismatched control org",
    )
    db.add(result)
    with pytest.raises(IntegrityError, match="control_same_assessment"):
        db.commit()


# --- reviews ------------------------------------------------------------------

def test_accepted_review_stored_with_empty_comment(db):
    org = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    result = make_result(db, org, control)

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=result.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
    )
    db.add(review)
    db.commit()
    assert review.id is not None
    assert review.outcome == "accepted"


def test_modified_review_stored_with_resulting_result(db):
    org = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    agent_result = make_result(db, org, control, version_no=1)

    consultant_result = make_result(
        db,
        org,
        control,
        version_no=2,
        based_on_result_id=agent_result.id,
        author_actor="aligo_consultant",
        author_user_id=user.id,
        control_status="implemented",
        explanation="Consultant modified result",
    )

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=agent_result.id,
        outcome="modified",
        resulting_result_id=consultant_result.id,
        comment="Adjusted status to implemented",
        reviewed_by_user_id=user.id,
    )
    db.add(review)
    db.commit()
    assert review.id is not None
    assert review.resulting_result_id == consultant_result.id


def test_modified_review_without_resulting_result_rejected(db):
    org = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    agent_result = make_result(db, org, control)

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=agent_result.id,
        outcome="modified",
        resulting_result_id=None,
        comment="No resulting result",
        reviewed_by_user_id=user.id,
    )
    db.add(review)
    with pytest.raises(IntegrityError, match="modified_has_result"):
        db.commit()


def test_rejected_review_with_blank_comment_rejected(db):
    org = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    agent_result = make_result(db, org, control)

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=agent_result.id,
        outcome="rejected",
        comment="   ",
        reviewed_by_user_id=user.id,
    )
    db.add(review)
    with pytest.raises(IntegrityError, match="comment_required"):
        db.commit()


def test_duplicate_review_for_same_result_rejected(db):
    org = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    agent_result = make_result(db, org, control)

    first_review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=agent_result.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
    )
    db.add(first_review)
    db.commit()

    second_review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=agent_result.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
    )
    db.add(second_review)
    with pytest.raises(IntegrityError, match="uq_control_result_reviews_result"):
        db.commit()


def test_review_update_rejected_by_trigger(db):
    org = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    agent_result = make_result(db, org, control)

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=agent_result.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
    )
    db.add(review)
    db.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(
            text("UPDATE control_result_reviews SET comment='changed' WHERE id = :id"),
            {"id": review.id},
        )


def test_review_with_mismatched_organization_result_rejected(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    assessment_a = make_assessment(db, org_a)
    assessment_b = make_assessment(db, org_b)
    user = make_user(db)
    control_a = make_control(db, org_a, assessment_a)
    agent_result_a = make_result(db, org_a, control_a)

    review = ControlResultReview(
        organization_id=org_b.id,
        assessment_id=assessment_b.id,
        control_result_id=agent_result_a.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
    )
    db.add(review)
    with pytest.raises(IntegrityError, match="result_same_assessment"):
        db.commit()


# --- composite trace and assessment FKs (AGRC-61 fix) ------------------------

def test_result_with_trace_of_same_assessment_accepted(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    trace = make_trace(db, org, assessment)

    result = make_result(db, org, control, trace_id=trace.id)
    assert result.id is not None
    assert result.trace_id == trace.id


def test_result_with_trace_of_another_organization_rejected(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    assessment_a = make_assessment(db, org_a)
    assessment_b = make_assessment(db, org_b)
    control_a = make_control(db, org_a, assessment_a)
    trace_b = make_trace(db, org_b, assessment_b)

    result = ControlResult(
        organization_id=org_a.id,
        assessment_id=assessment_a.id,
        assessment_control_id=control_a.id,
        version_no=1,
        author_actor="agent",
        control_status="implemented",
        explanation="Result with other org trace",
        trace_id=trace_b.id,
    )
    db.add(result)
    with pytest.raises(IntegrityError, match="trace_same_assessment"):
        db.commit()


def test_result_with_trace_of_another_assessment_same_org_rejected(db):
    org = make_organization(db)
    assessment_1 = make_assessment(db, org)
    assessment_2 = make_assessment(db, org)
    control_1 = make_control(db, org, assessment_1)
    trace_2 = make_trace(db, org, assessment_2)

    result = ControlResult(
        organization_id=org.id,
        assessment_id=assessment_1.id,
        assessment_control_id=control_1.id,
        version_no=1,
        author_actor="agent",
        control_status="implemented",
        explanation="Result with other assessment trace",
        trace_id=trace_2.id,
    )
    db.add(result)
    with pytest.raises(IntegrityError, match="trace_same_assessment"):
        db.commit()


def test_result_with_mismatched_assessment_id_to_control_rejected(db):
    org = make_organization(db)
    assessment_1 = make_assessment(db, org)
    assessment_2 = make_assessment(db, org)
    control_1 = make_control(db, org, assessment_1)

    result = ControlResult(
        organization_id=org.id,
        assessment_id=assessment_2.id,
        assessment_control_id=control_1.id,
        version_no=1,
        author_actor="agent",
        control_status="implemented",
        explanation="Result with mismatched assessment_id to control",
    )
    db.add(result)
    with pytest.raises(IntegrityError, match="control_same_assessment"):
        db.commit()


def test_result_with_based_on_result_of_another_assessment_rejected(db):
    org = make_organization(db)
    assessment_1 = make_assessment(db, org)
    assessment_2 = make_assessment(db, org)
    control_1 = make_control(db, org, assessment_1)
    control_2 = make_control(db, org, assessment_2)
    result_1 = make_result(db, org, control_1, version_no=1)

    result_2 = ControlResult(
        organization_id=org.id,
        assessment_id=assessment_2.id,
        assessment_control_id=control_2.id,
        version_no=2,
        based_on_result_id=result_1.id,
        author_actor="agent",
        control_status="implemented",
        explanation="Result based on another assessment result",
    )
    db.add(result_2)
    with pytest.raises(IntegrityError, match="based_on_same_assessment"):
        db.commit()


def test_review_with_trace_of_same_assessment_accepted(db):
    org = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    result = make_result(db, org, control)
    trace = make_trace(db, org, assessment)

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=result.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
        review_trace_id=trace.id,
    )
    db.add(review)
    db.commit()
    assert review.id is not None
    assert review.review_trace_id == trace.id


def test_review_with_trace_of_another_organization_rejected(db):
    org_a = make_organization(db)
    org_b = make_organization(db)
    user = make_user(db)
    assessment_a = make_assessment(db, org_a)
    assessment_b = make_assessment(db, org_b)
    control_a = make_control(db, org_a, assessment_a)
    result_a = make_result(db, org_a, control_a)
    trace_b = make_trace(db, org_b, assessment_b)

    review = ControlResultReview(
        organization_id=org_a.id,
        assessment_id=assessment_a.id,
        control_result_id=result_a.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
        review_trace_id=trace_b.id,
    )
    db.add(review)
    with pytest.raises(IntegrityError, match="trace_same_assessment"):
        db.commit()


def test_review_with_trace_of_another_assessment_same_org_rejected(db):
    org = make_organization(db)
    user = make_user(db)
    assessment_1 = make_assessment(db, org)
    assessment_2 = make_assessment(db, org)
    control_1 = make_control(db, org, assessment_1)
    result_1 = make_result(db, org, control_1)
    trace_2 = make_trace(db, org, assessment_2)

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment_1.id,
        control_result_id=result_1.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
        review_trace_id=trace_2.id,
    )
    db.add(review)
    with pytest.raises(IntegrityError, match="trace_same_assessment"):
        db.commit()


def test_review_with_mismatched_assessment_id_to_result_rejected(db):
    org = make_organization(db)
    user = make_user(db)
    assessment_1 = make_assessment(db, org)
    assessment_2 = make_assessment(db, org)
    control_1 = make_control(db, org, assessment_1)
    result_1 = make_result(db, org, control_1)

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment_2.id,
        control_result_id=result_1.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
    )
    db.add(review)
    with pytest.raises(IntegrityError, match="result_same_assessment"):
        db.commit()


def test_modified_review_with_resulting_result_of_another_assessment_rejected(db):
    org = make_organization(db)
    user = make_user(db)
    assessment_1 = make_assessment(db, org)
    assessment_2 = make_assessment(db, org)
    control_1 = make_control(db, org, assessment_1)
    control_2 = make_control(db, org, assessment_2)
    agent_result_1 = make_result(db, org, control_1, version_no=1)
    consultant_result_2 = make_result(
        db,
        org,
        control_2,
        version_no=2,
        author_actor="aligo_consultant",
        author_user_id=user.id,
        control_status="implemented",
        explanation="Result in assessment 2",
    )

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment_1.id,
        control_result_id=agent_result_1.id,
        outcome="modified",
        resulting_result_id=consultant_result_2.id,
        comment="Resulting result in another assessment",
        reviewed_by_user_id=user.id,
    )
    db.add(review)
    with pytest.raises(IntegrityError, match="resulting_same_assessment"):
        db.commit()


def test_result_with_null_trace_id_accepted(db):
    org = make_organization(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)

    result = ControlResult(
        organization_id=org.id,
        assessment_id=assessment.id,
        assessment_control_id=control.id,
        version_no=1,
        author_actor="agent",
        control_status="implemented",
        explanation="Result without trace reference",
        trace_id=None,
    )
    db.add(result)
    db.commit()
    assert result.id is not None
    assert result.trace_id is None


def test_review_with_null_review_trace_id_accepted(db):
    org = make_organization(db)
    user = make_user(db)
    assessment = make_assessment(db, org)
    control = make_control(db, org, assessment)
    result = make_result(db, org, control)

    review = ControlResultReview(
        organization_id=org.id,
        assessment_id=assessment.id,
        control_result_id=result.id,
        outcome="accepted",
        comment="",
        reviewed_by_user_id=user.id,
        review_trace_id=None,
    )
    db.add(review)
    db.commit()
    assert review.id is not None
    assert review.review_trace_id is None

