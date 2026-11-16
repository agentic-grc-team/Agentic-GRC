"""Keep an assessment's status in step with its results (draft → in_progress → awaiting_review → completed).

The status is derived from the latest result version of every control in scope, the same rule the
report uses for "final":

* in_progress: at least one control has no result yet (the interview still has work to do);
* awaiting_review: every control has a result, but at least one is not final yet;
* completed: every control has a final result (an accepted agent result or a consultant version).

Interviews stay open while the assessment is in progress or awaiting review, so a second
participant can still answer. A completed assessment no longer accepts interview answers.
A draft assessment is never moved by this module.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.db.models import Assessment, AssessmentControl, ControlResult, ControlResultReview

INTERVIEW_OPEN_STATUSES = frozenset({"in_progress", "awaiting_review"})


def accepts_interviews(assessment_status: str) -> bool:
    """True while participants may still open interviews and answer."""
    return assessment_status in INTERVIEW_OPEN_STATUSES


def derive_status(controls_in_scope: int, with_result: int, final: int) -> str:
    """The status for these counts of in-scope controls."""
    if controls_in_scope == 0 or with_result < controls_in_scope:
        return "in_progress"
    if final < controls_in_scope:
        return "awaiting_review"
    return "completed"


def refresh_assessment_status(db: Session, organization_id: UUID, assessment_id: UUID) -> Assessment | None:
    """Recompute and set the assessment's status in the current transaction (flush only).

    Call it after anything that adds a result version or a review. It locks the assessment row so
    two concurrent writers end with the status of the later one.
    """
    assessment = db.scalar(
        select(Assessment)
        .where(Assessment.organization_id == organization_id, Assessment.id == assessment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if assessment is None or assessment.status == "draft":
        return assessment

    newest = aliased(ControlResult)
    latest_version = (
        select(func.max(newest.version_no))
        .where(newest.assessment_control_id == ControlResult.assessment_control_id)
        .correlate(ControlResult)
        .scalar_subquery()
    )
    rows = db.execute(
        select(AssessmentControl.id, ControlResult.author_actor, ControlResultReview.outcome)
        .outerjoin(
            ControlResult,
            (ControlResult.assessment_control_id == AssessmentControl.id)
            & (ControlResult.organization_id == AssessmentControl.organization_id)
            & (ControlResult.version_no == latest_version),
        )
        .outerjoin(ControlResultReview, ControlResultReview.control_result_id == ControlResult.id)
        .where(
            AssessmentControl.organization_id == organization_id,
            AssessmentControl.assessment_id == assessment_id,
            AssessmentControl.in_scope.is_(True),
        )
    ).all()

    with_result = sum(1 for _, author, _ in rows if author is not None)
    final = sum(
        1
        for _, author, outcome in rows
        if author == "aligo_consultant" or (author == "agent" and outcome == "accepted")
    )
    new_status = derive_status(len(rows), with_result, final)

    if new_status != assessment.status:
        assessment.status = new_status
    if new_status == "completed":
        if assessment.completed_at is None:
            assessment.completed_at = datetime.now(timezone.utc)
    elif assessment.completed_at is not None:
        assessment.completed_at = None
    db.flush()
    return assessment
