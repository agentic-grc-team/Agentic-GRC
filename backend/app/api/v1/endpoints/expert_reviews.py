from fastapi import APIRouter, HTTPException, status

from app.schemas.expert_review import (
    ReviewDecision,
    ReviewDecisionResponse,
    ReviewItem,
)


router = APIRouter(prefix="/expert-reviews", tags=["expert reviews"])


@router.get("/pending", response_model=list[ReviewItem])
def get_pending_reviews():
    return [
        ReviewItem(
            result_id="result-demo-001",
            assessment_id="assessment-demo-001",
            control_code="PR.AA-03",
            control_title="Users, services, and hardware are authenticated",
            control_status="partially_implemented",
            maturity_current=2,
            confidence=0.78,
            explanation=(
                "Multi-factor authentication is enabled for some "
                "administrator accounts, but not for all privileged accounts."
            ),
            evidence_summary=(
                "The uploaded access policy requires MFA. However, the "
                "Microsoft 365 configuration indicates incomplete coverage."
            ),
            requires_human_review=True,
        )
    ]

@router.post(
    "/{result_id}/decision",
    response_model=ReviewDecisionResponse,
)
def submit_review_decision(
    result_id: str,
    decision: ReviewDecision,
):
    if result_id != "result-demo-001":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review result not found.",
        )

    return ReviewDecisionResponse(
        result_id=result_id,
        outcome=decision.outcome,
        comment=decision.comment,
        message="Review decision received successfully.",
    )