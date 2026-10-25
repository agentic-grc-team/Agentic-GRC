"""Read the reasoning trace behind one result in Expert reviews (HU-25, AGRC-60)."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Assessment,
    AssessmentControl,
    ControlResult,
    DecisionTraceRecord,
    Organization,
    User,
)
from app.schemas.decision_trace import DecisionTraceRead
from app.schemas.review_trace import ResultTraceRead
from app.security.expert_reviews import require_expert_review_access


def get_result_trace(db: Session, result_id: UUID, user: User) -> ResultTraceRead:
    """The decisions behind one result, with the result's own decision identified.

    Access is the same as for the review itself: administrators and consultants of the
    result's organization, or a platform administrator. Other members get 403 and
    everyone else 404, before any trace data is read (HU-25 AC 4).
    """
    result = db.get(ControlResult, result_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review result not found.",
        )

    require_expert_review_access(db, result.organization_id, user)

    control = db.scalar(
        select(AssessmentControl).where(
            AssessmentControl.id == result.assessment_control_id,
            AssessmentControl.organization_id == result.organization_id,
            AssessmentControl.assessment_id == result.assessment_id,
        )
    )
    assessment = db.scalar(
        select(Assessment).where(
            Assessment.id == result.assessment_id,
            Assessment.organization_id == result.organization_id,
        )
    )
    organization = db.get(Organization, result.organization_id)
    if control is None or assessment is None or organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review result not found.",
        )

    # Decisions about this control in this assessment. The result's own decision is
    # included by id as well, so it is never missed even if its control list differs.
    belongs_to_control = DecisionTraceRecord.control_ids.contains([control.control_code])
    if result.trace_id is not None:
        belongs_to_control = or_(belongs_to_control, DecisionTraceRecord.id == result.trace_id)

    steps = db.scalars(
        select(DecisionTraceRecord)
        .where(
            DecisionTraceRecord.organization_id == result.organization_id,
            DecisionTraceRecord.assessment_id == result.assessment_id,
            belongs_to_control,
        )
        .order_by(DecisionTraceRecord.created_at, DecisionTraceRecord.id)
    ).all()

    return ResultTraceRead(
        result_id=result.id,
        organization_id=organization.id,
        organization_name=organization.name,
        assessment_id=assessment.id,
        assessment_title=assessment.title,
        control_code=control.control_code,
        control_title=control.control_title,
        result_version=result.version_no,
        result_author=result.author_actor,
        result_trace_id=result.trace_id,
        steps=[DecisionTraceRead.model_validate(step) for step in steps],
    )
