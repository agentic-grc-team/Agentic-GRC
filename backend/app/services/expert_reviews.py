from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assessment,
    AssessmentControl,
    ControlResult,
    ControlResultReview,
    DecisionTraceRecord,
    User,
)
from app.security.expert_reviews import require_expert_review_access
from app.schemas.decision_trace import DecisionTrace
from app.schemas.expert_review import ReviewDecision
from app.services.decision_traces import record_trace

def load_reviewable_result(
    db: Session,
    result_id: UUID,
    user: User,
) -> ControlResult:
    result = db.get(ControlResult, result_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review result not found.",
        )

    require_expert_review_access(
        db,
        result.organization_id,
        user,
    )

    # Lock the control before checking versions and existing reviews.
    control = db.scalar(
        select(AssessmentControl)
        .where(
            AssessmentControl.id == result.assessment_control_id,
            AssessmentControl.organization_id == result.organization_id,
            AssessmentControl.assessment_id == result.assessment_id,
        )
        .with_for_update()
    )

    if control is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment control not found.",
        )

    if not control.in_scope:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This control is outside the assessment scope.",
        )

    if result.author_actor != "agent":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only agent-authored results can be reviewed.",
        )

    latest_result_id = db.scalar(
        select(ControlResult.id)
        .where(
            ControlResult.organization_id == result.organization_id,
            ControlResult.assessment_id == result.assessment_id,
            ControlResult.assessment_control_id == control.id,
        )
        .order_by(ControlResult.version_no.desc())
        .limit(1)
    )

    if latest_result_id != result.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This result has been superseded by a newer version.",
        )

    existing_review_id = db.scalar(
        select(ControlResultReview.id).where(
            ControlResultReview.organization_id == result.organization_id,
            ControlResultReview.assessment_id == result.assessment_id,
            ControlResultReview.control_result_id == result.id,
        )
    )

    if existing_review_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This result has already been reviewed.",
        )

    return result

def save_review_decision(
    db: Session,
    result_id: UUID,
    decision: ReviewDecision,
    user: User,
) -> ControlResultReview:
    if decision.outcome == "modified":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Modified result persistence is not implemented yet.",
        )

    result = load_reviewable_result(db, result_id, user)

    assessment = db.get(Assessment, result.assessment_id)
    control = db.get(AssessmentControl, result.assessment_control_id)

    if (
        assessment is None
        or control is None
        or assessment.organization_id != result.organization_id
        or control.organization_id != result.organization_id
        or control.assessment_id != result.assessment_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The result has an invalid assessment context.",
        )

    original_trace = None

    if result.trace_id is not None:
        original_trace = db.get(DecisionTraceRecord, result.trace_id)

    if (
        original_trace is None
        or original_trace.organization_id != result.organization_id
        or original_trace.assessment_id != result.assessment_id
        or original_trace.actor_type != "agent"
        or original_trace.decision_type != "status_assessed"
        or control.control_code not in original_trace.control_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A matching agent status trace is required to review this result.",
        )

    review_id = uuid4()
    rationale = decision.comment

    if not rationale:
        rationale = "The reviewer accepted the proposed result."

    trace = record_trace(
        db,
        DecisionTrace(
            organization_id=result.organization_id,
            assessment_id=result.assessment_id,
            decision_type="human_review",
            control_ids=[control.control_code],
            actor_type="aligo_consultant",
            actor_user_id=user.id,
            kb_version=assessment.kb_version,
            output={
                "control_result_id": str(result.id),
                "control_result_review_id": str(review_id),
                "outcome": decision.outcome,
                "comment": decision.comment,
            },
            rationale=rationale,
            reviews_trace_id=original_trace.id,
            review_outcome=decision.outcome,
        ),
    )

    review = ControlResultReview(
        id=review_id,
        organization_id=result.organization_id,
        assessment_id=result.assessment_id,
        control_result_id=result.id,
        outcome=decision.outcome,
        comment=decision.comment,
        reviewed_by_user_id=user.id,
        review_trace_id=trace.id,
    )

    db.add(review)
    db.flush()

    return review