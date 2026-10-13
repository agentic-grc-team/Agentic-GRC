from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased

from app.db.models import OrganizationMembership
from app.schemas.expert_review import ReviewItem

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

from copy import deepcopy

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
    resulting_result_id = None
    modified = decision.modified_result

    output = {
        "control_result_id": str(result.id),
        "control_result_review_id": str(review_id),
        "outcome": decision.outcome,
        "comment": decision.comment,
    }

    if decision.outcome == "modified":
        if modified is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A modified result is required.",
            )

        resulting_result_id = uuid4()
        output["resulting_result_id"] = str(resulting_result_id)
        output["modified_result"] = modified.model_dump(mode="json")

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
            output=output,
            rationale=rationale,
            reviews_trace_id=original_trace.id,
            review_outcome=decision.outcome,
        ),
    )

    if decision.outcome == "modified":
        justification = None
        not_assessed_reason = None

        if modified.control_status == "not_applicable":
            justification = modified.justification

        if modified.control_status == "not_assessed":
            not_assessed_reason = modified.not_assessed_reason

        new_result = ControlResult(
            id=resulting_result_id,
            organization_id=result.organization_id,
            assessment_id=result.assessment_id,
            assessment_control_id=result.assessment_control_id,
            version_no=result.version_no + 1,
            based_on_result_id=result.id,
            author_actor="aligo_consultant",
            author_user_id=user.id,
            control_status=modified.control_status,
            explanation=modified.explanation,
            justification=justification,
            not_assessed_reason=not_assessed_reason,
            maturity_current=result.maturity_current,
            maturity_target=result.maturity_target,
            confidence=None,
            requires_human_review=False,
            evidence_pending=result.evidence_pending,
            evidence_summary=result.evidence_summary,
            evidence_refs=deepcopy(result.evidence_refs),
            trace_id=trace.id,
        )

        db.add(new_result)
        db.flush()

    review = ControlResultReview(
        id=review_id,
        organization_id=result.organization_id,
        assessment_id=result.assessment_id,
        control_result_id=result.id,
        outcome=decision.outcome,
        resulting_result_id=resulting_result_id,
        comment=decision.comment,
        reviewed_by_user_id=user.id,
        review_trace_id=trace.id,
    )

    db.add(review)
    db.flush()

    return review

def list_pending_reviews(
    db: Session,
    user: User,
) -> list[ReviewItem]:
    newer_result = aliased(ControlResult)

    has_newer_version = (
        select(newer_result.id)
        .where(
            newer_result.assessment_control_id
            == ControlResult.assessment_control_id,
            newer_result.version_no > ControlResult.version_no,
        )
        .correlate(ControlResult)
        .exists()
    )

    has_review = (
        select(ControlResultReview.id)
        .where(
            ControlResultReview.control_result_id == ControlResult.id,
        )
        .correlate(ControlResult)
        .exists()
    )

    statement = (
        select(ControlResult, AssessmentControl)
        .join(
            AssessmentControl,
            (AssessmentControl.id == ControlResult.assessment_control_id)
            & (
                AssessmentControl.organization_id
                == ControlResult.organization_id
            )
            & (
                AssessmentControl.assessment_id
                == ControlResult.assessment_id
            ),
        )
        .where(
            AssessmentControl.in_scope.is_(True),
            ControlResult.author_actor == "agent",
            ~has_newer_version,
            ~has_review,
        )
        .order_by(ControlResult.created_at, ControlResult.id)
    )

    if not user.is_platform_admin:
        has_access = (
            select(OrganizationMembership.id)
            .where(
                OrganizationMembership.organization_id
                == ControlResult.organization_id,
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.status == "active",
                OrganizationMembership.role.in_(
                    ("administrator", "consultant")
                ),
            )
            .correlate(ControlResult)
            .exists()
        )

        statement = statement.where(has_access)

    rows = db.execute(statement).all()
    items = []

    for result, control in rows:
        items.append(
            ReviewItem(
                result_id=str(result.id),
                assessment_id=str(result.assessment_id),
                control_code=control.control_code,
                control_title=control.control_title,
                control_status=result.control_status,
                maturity_current=result.maturity_current,
                confidence=result.confidence,
                explanation=result.explanation,
                evidence_summary=result.evidence_summary or "",
                requires_human_review=result.requires_human_review,
                justification=result.justification,
                not_assessed_reason=result.not_assessed_reason,
            )
        )

    return items