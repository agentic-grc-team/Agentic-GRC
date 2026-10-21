"""Authenticated interview session and participant-turn endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.db.models import User
from app.schemas.interviews import (
    InterviewRead,
    InterviewSessionCreate,
    InterviewTurnCreate,
    InterviewTurnReceipt,
)
from app.security.auth import get_current_user
from app.services.interview_agent import advance_interview_agent, start_interview_agent
from app.services.interviews import (
    create_or_resume_interview,
    read_interview,
    save_interview_turn,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["interviews"])


@router.post(
    "/{organization_id}/assessments/{assessment_id}/interview",
    response_model=InterviewRead,
    status_code=status.HTTP_201_CREATED,
)
def open_interview(
    organization_id: UUID,
    assessment_id: UUID,
    data: InterviewSessionCreate,
    response: Response,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> InterviewRead:
    try:
        interview = create_or_resume_interview(
            db, organization_id, assessment_id, user, data
        )
        resumed = interview.resumed
        if interview.session is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The interview session could not be initialized.",
            )
        start_interview_agent(db, interview.session.id)
        interview = read_interview(
            db, organization_id, assessment_id, user, interview.session.id
        )
        interview.resumed = resumed
        if resumed:
            response.status_code = status.HTTP_200_OK
        return interview
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview session conflicts with current data. Retry the request.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Interview session persistence failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The interview session could not be saved.",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.error("Interview agent initialization failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The interview agent could not initialize the session. Retry the request.",
        ) from exc


@router.get(
    "/{organization_id}/assessments/{assessment_id}/interview",
    response_model=InterviewRead,
)
def get_interview(
    organization_id: UUID,
    assessment_id: UUID,
    session_id: UUID | None = None,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> InterviewRead:
    return read_interview(db, organization_id, assessment_id, user, session_id)


@router.post(
    "/{organization_id}/assessments/{assessment_id}/interview/turns",
    response_model=InterviewTurnReceipt,
    status_code=status.HTTP_201_CREATED,
)
def post_interview_turn(
    organization_id: UUID,
    assessment_id: UUID,
    data: InterviewTurnCreate,
    response: Response,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=128,
        description="Alternative idempotency key; required if client_request_id is omitted.",
    ),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> InterviewTurnReceipt:
    try:
        receipt = save_interview_turn(
            db,
            organization_id,
            assessment_id,
            user,
            data,
            idempotency_key,
        )
        agent_turns = advance_interview_agent(
            db,
            organization_id,
            assessment_id,
            data.session_id,
            receipt.turn.id,
        )
        interview = read_interview(
            db, organization_id, assessment_id, user, data.session_id
        )
        receipt.agent_turns = agent_turns
        receipt.draft_results = interview.draft_results
        if receipt.idempotent_replay:
            response.status_code = status.HTTP_200_OK
        return receipt
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview answer conflicts with current data. Retry the request.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Interview turn processing failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The interview answer could not be processed. Retry with the same idempotency key.",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.error("Interview agent processing failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The answer was saved, but the interview agent could not process it. Retry with the same idempotency key.",
        ) from exc
