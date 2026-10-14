"""Expert review persistence and concurrency integration tests."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Assessment,
    AssessmentControl,
    ControlResult,
    ControlResultReview,
    DecisionTraceRecord,
    Organization,
    OrganizationMembership,
    User,
)
from app.db.session import get_engine
from app.schemas.expert_review import ReviewDecision
from app.services.expert_reviews import (
    list_pending_reviews,
    save_review_decision,
)

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


def make_assessment_context(db, role="consultant"):
    """Create the assessment context without an agent result or trace."""
    organization = make_organization(db)
    user = make_user(db)

    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
            status="active",
        )
    )
    db.commit()

    assessment = make_assessment(db, organization)
    control = make_control(
        db,
        organization,
        assessment,
        control_code="PR.AA-03",
        control_title="Users, services, and hardware are authenticated",
    )

    return organization, user, assessment, control


def make_review_context(db, role="consultant"):
    organization, user, assessment, control = (
        make_assessment_context(db, role=role)
    )

    trace = make_trace(
        db,
        organization,
        assessment,
        output={"status": "partially_implemented"},
    )

    result = make_result(
        db,
        organization,
        control,
        trace_id=trace.id,
        maturity_current=2,
        maturity_target=4,
        evidence_pending=True,
    )

    return organization, user, assessment, control, result, trace

@pytest.mark.parametrize("outcome", ["accepted", "rejected"])
def test_expert_review_saves_decision_and_trace(db, outcome):
    organization, user, assessment, control, result, original_trace = (
        make_review_context(db)
    )

    review = save_review_decision(
        db,
        result.id,
        ReviewDecision(
            outcome=outcome,
            comment="Evidence checked.",
        ),
        user,
    )
    review_id = review.id
    db.commit()
    db.expire_all()

    stored_review = db.get(ControlResultReview, review_id)
    review_trace = db.get(
        DecisionTraceRecord,
        stored_review.review_trace_id,
    )

    assert stored_review.control_result_id == result.id
    assert stored_review.outcome == outcome
    assert stored_review.reviewed_by_user_id == user.id
    assert stored_review.resulting_result_id is None

    assert review_trace.decision_type == "human_review"
    assert review_trace.actor_user_id == user.id
    assert review_trace.reviews_trace_id == original_trace.id
    assert review_trace.review_outcome == outcome
    assert review_trace.organization_id == organization.id
    assert review_trace.assessment_id == assessment.id

    assert list_pending_reviews(db, user) == []


def test_expert_review_modify_creates_new_version(db):
    organization, user, assessment, control, result, original_trace = (
        make_review_context(db)
    )

    review = save_review_decision(
        db,
        result.id,
        ReviewDecision(
            outcome="modified",
            comment="Corrected after configuration review.",
            modified_result={
                "control_status": "not_implemented",
                "explanation": "MFA is not enforced.",
            },
        ),
        user,
    )
    review_id = review.id
    db.commit()
    db.expire_all()

    stored_review = db.get(ControlResultReview, review_id)
    new_result = db.get(
        ControlResult,
        stored_review.resulting_result_id,
    )
    old_result = db.get(ControlResult, result.id)

    assert new_result.version_no == 2
    assert new_result.based_on_result_id == old_result.id
    assert new_result.assessment_control_id == control.id
    assert new_result.assessment_id == assessment.id
    assert new_result.organization_id == organization.id
    assert new_result.author_actor == "aligo_consultant"
    assert new_result.author_user_id == user.id
    assert new_result.control_status == "not_implemented"
    assert new_result.explanation == "MFA is not enforced."
    assert new_result.confidence is None
    assert new_result.maturity_current == 2
    assert new_result.maturity_target == 4
    assert new_result.evidence_pending is True
    assert new_result.evidence_refs == old_result.evidence_refs
    assert new_result.trace_id == stored_review.review_trace_id

    assert old_result.version_no == 1
    assert old_result.control_status == "partially_implemented"
    assert list_pending_reviews(db, user) == []


def test_expert_review_queue_excludes_other_organizations(db):
    org_a, user_a, _, _, result_a, _ = make_review_context(db)
    org_b, user_b, _, _, result_b, _ = make_review_context(db)

    pending = list_pending_reviews(db, user_a)

    assert [item.result_id for item in pending] == [str(result_a.id)]

    with pytest.raises(HTTPException) as error:
        save_review_decision(
            db,
            result_b.id,
            ReviewDecision(outcome="accepted"),
            user_a,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Review result not found."


def test_expert_review_representative_cannot_review(db):
    _, user, _, _, result, _ = make_review_context(
        db,
        role="representative",
    )

    assert list_pending_reviews(db, user) == []

    with pytest.raises(HTTPException) as error:
        save_review_decision(
            db,
            result.id,
            ReviewDecision(outcome="accepted"),
            user,
        )

    assert error.value.status_code == 403


def test_expert_review_queue_only_returns_latest_version(db):
    organization, user, _, control, old_result, trace = (
        make_review_context(db)
    )

    latest_result = make_result(
        db,
        organization,
        control,
        version_no=2,
        based_on_result_id=old_result.id,
        trace_id=trace.id,
    )

    pending = list_pending_reviews(db, user)

    assert [item.result_id for item in pending] == [
        str(latest_result.id)
    ]

    with pytest.raises(HTTPException) as error:
        save_review_decision(
            db,
            old_result.id,
            ReviewDecision(outcome="accepted"),
            user,
        )

    assert error.value.status_code == 409


def test_expert_review_rejects_second_decision(db):
    _, user, _, _, result, _ = make_review_context(db)

    save_review_decision(
        db,
        result.id,
        ReviewDecision(outcome="accepted"),
        user,
    )
    db.commit()

    with pytest.raises(HTTPException) as error:
        save_review_decision(
            db,
            result.id,
            ReviewDecision(
                outcome="rejected",
                comment="Second decision.",
            ),
            user,
        )

    assert error.value.status_code == 409


def test_expert_review_rollback_removes_all_new_records(db):
    _, user, assessment, control, result, _ = make_review_context(db)
    result_id = result.id
    assessment_id = assessment.id
    control_id = control.id

    with pytest.raises(RuntimeError, match="Simulated failure"):
        with db.begin_nested():
            save_review_decision(
                db,
                result_id,
                ReviewDecision(
                    outcome="modified",
                    comment="Correction.",
                    modified_result={
                        "control_status": "not_implemented",
                        "explanation": "MFA is absent.",
                    },
                ),
                user,
            )

            # Simulate failure after all records have been flushed.
            raise RuntimeError("Simulated failure")

    db.expire_all()

    reviews = list(
        db.scalars(
            select(ControlResultReview).where(
                ControlResultReview.control_result_id == result_id,
            )
        )
    )

    results = list(
        db.scalars(
            select(ControlResult).where(
                ControlResult.assessment_control_id == control_id,
            )
        )
    )

    human_traces = list(
        db.scalars(
            select(DecisionTraceRecord).where(
                DecisionTraceRecord.assessment_id == assessment_id,
                DecisionTraceRecord.decision_type == "human_review",
            )
        )
    )

    assert reviews == []
    assert [item.id for item in results] == [result_id]
    assert human_traces == []
    assert [item.result_id for item in list_pending_reviews(db, user)] == [
        str(result_id)
    ]


def test_expert_review_concurrent_modify_requests():
    settings = get_settings()

    # This test commits setup data, so run it only on our local Docker DB.
    if (
        settings.db_host != "127.0.0.1"
        or settings.db_port != 55432
        or settings.db_name != "agentic_grc_test"
    ):
        pytest.skip("Requires the dedicated local Docker test database.")

    engine = get_engine()

    with Session(engine) as setup:
        organization, user, assessment, control, result, trace = (
            make_review_context(setup)
        )

        user_id = user.id
        result_id = result.id
        control_id = control.id
        assessment_id = assessment.id

        setup.commit()

    barrier = Barrier(2)

    def submit_decision(comment):
        with Session(engine) as session:
            session.execute(
                text("SET LOCAL lock_timeout = '10s'")
            )
            session.execute(
                text("SET LOCAL statement_timeout = '15s'")
            )

            reviewer = session.get(User, user_id)

            decision = ReviewDecision(
                outcome="modified",
                comment=comment,
                modified_result={
                    "control_status": "not_implemented",
                    "explanation": "Concurrent review test correction.",
                },
            )

            # Both workers reach this point before either submits.
            barrier.wait(timeout=10)

            try:
                save_review_decision(
                    session,
                    result_id,
                    decision,
                    reviewer,
                )
                session.commit()
                return 200

            except HTTPException as error:
                session.rollback()
                return error.status_code

            except Exception:
                session.rollback()
                raise

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            submit_decision,
            "First consultant decision.",
        )
        second = executor.submit(
            submit_decision,
            "Second consultant decision.",
        )

        outcomes = [
            first.result(timeout=30),
            second.result(timeout=30),
        ]

    assert sorted(outcomes) == [200, 409]

    with Session(engine) as verification:
        reviews = list(
            verification.scalars(
                select(ControlResultReview).where(
                    ControlResultReview.control_result_id == result_id,
                )
            )
        )

        versions = list(
            verification.scalars(
                select(ControlResult)
                .where(
                    ControlResult.assessment_control_id == control_id,
                )
                .order_by(ControlResult.version_no)
            )
        )

        human_traces = list(
            verification.scalars(
                select(DecisionTraceRecord).where(
                    DecisionTraceRecord.assessment_id == assessment_id,
                    DecisionTraceRecord.decision_type == "human_review",
                )
            )
        )

        assert len(reviews) == 1
        assert [version.version_no for version in versions] == [1, 2]
        assert len(human_traces) == 1

        assert reviews[0].resulting_result_id == versions[1].id
        assert reviews[0].review_trace_id == human_traces[0].id
        assert versions[1].trace_id == human_traces[0].id
