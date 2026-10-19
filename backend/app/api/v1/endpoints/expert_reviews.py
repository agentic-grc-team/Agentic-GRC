import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.db.models import User
from app.schemas.expert_review import (
    ReviewDecision,
    ReviewDecisionResponse,
    ReviewEvidence,
    ReviewItem,
)
from app.security.auth import get_current_user
from app.services.expert_reviews import (
    list_pending_reviews,
    save_review_decision,
)

from app.services.review_evidence import get_review_evidence

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/expert-reviews",
    tags=["expert reviews"],
)


@router.get("/pending", response_model=list[ReviewItem])
def get_pending_reviews(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    return list_pending_reviews(db, user)

@router.get(
    "/{result_id}/evidence",
    response_model=ReviewEvidence,
)
def read_review_evidence(
    result_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    return get_review_evidence(db, result_id, user)

@router.post(
    "/{result_id}/decision",
    response_model=ReviewDecisionResponse,
)

def submit_review_decision(
    result_id: UUID,
    decision: ReviewDecision,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    try:
        review = save_review_decision(
            db,
            result_id,
            decision,
            user,
        )

        response = ReviewDecisionResponse(
            result_id=str(review.control_result_id),
            outcome=review.outcome,
            comment=review.comment,
            message="Review decision saved successfully.",
        )

        db.commit()

        return response

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The review conflicts with current data. "
                "Refresh the queue and try again."
            ),
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Expert review persistence failed.")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The review could not be saved.",
        ) from exc