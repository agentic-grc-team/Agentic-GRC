"""Persist authenticated, resumable interview sessions and participant turns."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Assessment,
    AssessmentControl,
    AssessmentModule,
    AssessmentParticipant,
    AssessmentSession,
    ControlResult,
    InterviewBlock,
    InterviewTurn,
    KBVersion,
    Organization,
    OrganizationMembership,
    Question,
    SessionParticipant,
    User,
)
from app.schemas.interviews import (
    InterviewControlRead,
    InterviewDraftResultRead,
    InterviewRead,
    InterviewSessionCreate,
    InterviewSessionRead,
    InterviewSourceReference,
    InterviewTurnCreate,
    InterviewTurnRead,
    InterviewTurnReceipt,
)


_NOT_FOUND = "Interview assessment not found."
_SESSION_NOT_FOUND = "Interview session not found."


def create_or_resume_interview(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    user: User,
    data: InterviewSessionCreate,
) -> InterviewRead:
    """Create a participant's active session or resume their matching active session."""
    organization, assessment, membership = _require_assessment_access(
        db, organization_id, assessment_id, user
    )
    # Serializes participant/session creation for one assessment without adding
    # an idempotency column that is absent from the adopted database model.
    locked_assessment = db.scalar(
        select(Assessment)
        .where(
            Assessment.organization_id == organization_id,
            Assessment.id == assessment_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    assessment = locked_assessment
    if locked_assessment.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment is not accepting interview sessions.",
        )

    if data.block_id is not None:
        block_exists = db.scalar(
            select(InterviewBlock.id)
            .join(KBVersion, KBVersion.id == InterviewBlock.kb_version_id)
            .where(
                InterviewBlock.id == data.block_id,
                KBVersion.label == assessment.kb_version,
            )
        )
        if block_exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    participant = _get_or_create_participant(
        db, organization_id, assessment_id, user, membership
    )
    session_statement = (
        select(AssessmentSession)
        .join(
            SessionParticipant,
            (SessionParticipant.session_id == AssessmentSession.id)
            & (SessionParticipant.organization_id == AssessmentSession.organization_id),
        )
        .where(
            AssessmentSession.organization_id == organization_id,
            AssessmentSession.assessment_id == assessment_id,
            AssessmentSession.session_type == data.session_type,
            AssessmentSession.block_id == data.block_id,
            AssessmentSession.ended_at.is_(None),
            SessionParticipant.participant_id == participant.id,
            SessionParticipant.organization_id == organization_id,
        )
        .order_by(AssessmentSession.started_at.desc().nulls_last())
        .limit(1)
        .with_for_update(of=AssessmentSession)
    )
    session = db.scalar(session_statement)
    resumed = session is not None

    if session is None:
        now = datetime.now(timezone.utc)
        is_facilitator = user.is_platform_admin or (
            membership is not None and membership.role in ("administrator", "consultant")
        )
        session = AssessmentSession(
            organization_id=organization_id,
            assessment_id=assessment_id,
            session_type=data.session_type,
            block_id=data.block_id,
            facilitator_user_id=user.id if is_facilitator else None,
            started_at=now,
        )
        db.add(session)
        db.flush()
        db.add(
            SessionParticipant(
                organization_id=organization_id,
                session_id=session.id,
                participant_id=participant.id,
            )
        )
    elif session.started_at is None:
        session.started_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(session)
    return _build_interview_read(
        db, organization, assessment, participant, session, resumed=resumed
    )


def read_interview(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    user: User,
    session_id: UUID | None = None,
) -> InterviewRead:
    """Read only sessions joined by this participant; no session returns an empty interview."""
    organization, assessment, _membership = _require_assessment_access(
        db, organization_id, assessment_id, user
    )
    participant = _find_participant(db, organization_id, assessment_id, user.id)
    session = None

    if session_id is not None:
        if participant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SESSION_NOT_FOUND)
        session = db.scalar(
            select(AssessmentSession)
            .join(
                SessionParticipant,
                (SessionParticipant.session_id == AssessmentSession.id)
                & (SessionParticipant.organization_id == AssessmentSession.organization_id),
            )
            .where(
                AssessmentSession.id == session_id,
                AssessmentSession.organization_id == organization_id,
                AssessmentSession.assessment_id == assessment_id,
                SessionParticipant.participant_id == participant.id,
                SessionParticipant.organization_id == organization_id,
            )
        )
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SESSION_NOT_FOUND)
    elif participant is not None:
        session = db.scalar(
            select(AssessmentSession)
            .join(
                SessionParticipant,
                (SessionParticipant.session_id == AssessmentSession.id)
                & (SessionParticipant.organization_id == AssessmentSession.organization_id),
            )
            .where(
                AssessmentSession.organization_id == organization_id,
                AssessmentSession.assessment_id == assessment_id,
                AssessmentSession.ended_at.is_(None),
                SessionParticipant.participant_id == participant.id,
                SessionParticipant.organization_id == organization_id,
            )
            .order_by(AssessmentSession.started_at.desc().nulls_last())
            .limit(1)
        )

    return _build_interview_read(db, organization, assessment, participant, session)


def save_interview_turn(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    user: User,
    data: InterviewTurnCreate,
    idempotency_key: str | None,
) -> InterviewTurnReceipt:
    """Persist one participant answer exactly once for a session/request key."""
    _organization, assessment, _membership = _require_assessment_access(
        db, organization_id, assessment_id, user
    )
    session = db.scalar(
        select(AssessmentSession)
        .where(
            AssessmentSession.id == data.session_id,
            AssessmentSession.organization_id == organization_id,
            AssessmentSession.assessment_id == assessment_id,
        )
        .with_for_update()
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SESSION_NOT_FOUND)

    participant = db.scalar(
        select(AssessmentParticipant)
        .join(
            SessionParticipant,
            (SessionParticipant.participant_id == AssessmentParticipant.id)
            & (SessionParticipant.organization_id == AssessmentParticipant.organization_id),
        )
        .where(
            AssessmentParticipant.organization_id == organization_id,
            AssessmentParticipant.assessment_id == assessment_id,
            AssessmentParticipant.user_id == user.id,
            SessionParticipant.session_id == session.id,
            SessionParticipant.organization_id == organization_id,
        )
        .order_by(AssessmentParticipant.created_at)
        .limit(1)
    )
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SESSION_NOT_FOUND)

    request_key = _resolve_idempotency_key(data.client_request_id, idempotency_key)
    turn_id = uuid5(
        NAMESPACE_URL,
        f"agentic-grc:interview-turn:{session.id}:{request_key}",
    )
    existing = db.scalar(
        select(InterviewTurn).where(
            InterviewTurn.id == turn_id,
            InterviewTurn.organization_id == organization_id,
            InterviewTurn.session_id == session.id,
        )
    )
    if existing is not None:
        if not _same_turn_request(existing, participant.id, data):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key was already used for a different interview answer.",
            )
        db.commit()
        return InterviewTurnReceipt(turn=_turn_read(existing), idempotent_replay=True)

    if assessment.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment is not accepting interview answers.",
        )
    if session.ended_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This interview session has ended.",
        )

    latest_agent_turn = db.scalar(
        select(InterviewTurn)
        .where(
            InterviewTurn.organization_id == organization_id,
            InterviewTurn.session_id == session.id,
            InterviewTurn.speaker == "agent",
        )
        .order_by(InterviewTurn.sequence_no.desc())
        .limit(1)
    )
    if latest_agent_turn is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview has no pending agent question. Open or resume the interview first.",
        )
    if data.replies_to_turn_id != latest_agent_turn.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="replies_to_turn_id must identify the latest agent turn in this interview.",
        )
    if data.question_id != latest_agent_turn.question_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="question_id must match the question on the latest agent turn.",
        )
    answered_prompt = db.scalar(
        select(InterviewTurn.id)
        .where(
            InterviewTurn.organization_id == organization_id,
            InterviewTurn.session_id == session.id,
            InterviewTurn.speaker == "participant",
            InterviewTurn.replies_to_turn_id == latest_agent_turn.id,
        )
        .limit(1)
    )
    if answered_prompt is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This agent turn already has a saved answer. Retry that answer with its idempotency key.",
        )

    if data.question_id is not None:
        question_statement = (
            select(Question.id)
            .join(AssessmentModule, AssessmentModule.id == Question.module_id)
            .join(KBVersion, KBVersion.id == AssessmentModule.kb_version_id)
            .where(
                Question.id == data.question_id,
                KBVersion.label == assessment.kb_version,
            )
        )
        if session.block_id is not None:
            question_statement = question_statement.where(
                AssessmentModule.block_id == session.block_id
            )
        if db.scalar(question_statement) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SESSION_NOT_FOUND)

    if data.replies_to_turn_id is not None:
        parent_turn = db.scalar(
            select(InterviewTurn.id).where(
                InterviewTurn.id == data.replies_to_turn_id,
                InterviewTurn.organization_id == organization_id,
                InterviewTurn.session_id == session.id,
                InterviewTurn.speaker == "agent",
            )
        )
        if parent_turn is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SESSION_NOT_FOUND)

    sequence_no = db.scalar(
        select(func.coalesce(func.max(InterviewTurn.sequence_no), 0) + 1).where(
            InterviewTurn.organization_id == organization_id,
            InterviewTurn.session_id == session.id,
        )
    )
    turn = InterviewTurn(
        id=turn_id,
        organization_id=organization_id,
        session_id=session.id,
        sequence_no=sequence_no,
        speaker="participant",
        participant_id=participant.id,
        turn_type="answer",
        question_id=data.question_id,
        replies_to_turn_id=data.replies_to_turn_id,
        content=data.content,
        language_code=data.language_code,
    )
    db.add(turn)
    db.flush()
    db.commit()
    db.refresh(turn)
    return InterviewTurnReceipt(turn=_turn_read(turn), idempotent_replay=False)


def _require_assessment_access(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    user: User,
) -> tuple[Organization, Assessment, OrganizationMembership | None]:
    organization = db.scalar(select(Organization).where(Organization.id == organization_id))
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    membership = None
    if not user.is_platform_admin:
        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.status == "active",
            )
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    assessment = db.scalar(
        select(Assessment).where(
            Assessment.organization_id == organization_id,
            Assessment.id == assessment_id,
        )
    )
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    has_in_scope_controls = db.scalar(
        select(AssessmentControl.id)
        .where(
            AssessmentControl.organization_id == organization_id,
            AssessmentControl.assessment_id == assessment_id,
            AssessmentControl.in_scope.is_(True),
        )
        .limit(1)
    )
    if has_in_scope_controls is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment has no in-scope controls configured for an interview.",
        )
    return organization, assessment, membership


def _get_or_create_participant(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    user: User,
    membership: OrganizationMembership | None,
) -> AssessmentParticipant:
    participant = _find_participant(db, organization_id, assessment_id, user.id)
    if participant is not None:
        return participant

    role = membership.role if membership is not None else "platform_admin"
    participant_type = (
        "assessed_org_representative" if role == "representative" else "aligo_consultant"
    )
    role_titles = {
        "administrator": "Organization administrator",
        "consultant": "ALIGO consultant",
        "representative": "Organization representative",
        "platform_admin": "ALIGO platform administrator",
    }
    participant = AssessmentParticipant(
        organization_id=organization_id,
        assessment_id=assessment_id,
        user_id=user.id,
        participant_type=participant_type,
        role_title=role_titles[role],
    )
    db.add(participant)
    db.flush()
    return participant


def _find_participant(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    user_id: UUID,
) -> AssessmentParticipant | None:
    return db.scalar(
        select(AssessmentParticipant)
        .where(
            AssessmentParticipant.organization_id == organization_id,
            AssessmentParticipant.assessment_id == assessment_id,
            AssessmentParticipant.user_id == user_id,
        )
        .order_by(AssessmentParticipant.created_at, AssessmentParticipant.id)
        .limit(1)
    )


def _build_interview_read(
    db: Session,
    organization: Organization,
    assessment: Assessment,
    participant: AssessmentParticipant | None,
    session: AssessmentSession | None,
    *,
    resumed: bool = False,
) -> InterviewRead:
    controls = db.scalars(
        select(AssessmentControl)
        .where(
            AssessmentControl.organization_id == organization.id,
            AssessmentControl.assessment_id == assessment.id,
            AssessmentControl.in_scope.is_(True),
        )
        .order_by(AssessmentControl.control_code)
    ).all()
    draft_result_rows = db.execute(
        select(ControlResult, AssessmentControl)
        .join(
            AssessmentControl,
            (AssessmentControl.id == ControlResult.assessment_control_id)
            & (AssessmentControl.organization_id == ControlResult.organization_id)
            & (AssessmentControl.assessment_id == ControlResult.assessment_id),
        )
        .where(
            ControlResult.organization_id == organization.id,
            ControlResult.assessment_id == assessment.id,
            ControlResult.author_actor == "agent",
            AssessmentControl.in_scope.is_(True),
        )
        .order_by(
            AssessmentControl.control_code,
            ControlResult.version_no.desc(),
            ControlResult.created_at.desc(),
        )
    ).all()
    latest_drafts = {}
    for result, control in draft_result_rows:
        latest_drafts.setdefault(control.control_code, (result, control))
    turns = []
    if session is not None:
        turns = list(
            db.scalars(
                select(InterviewTurn)
                .where(
                    InterviewTurn.organization_id == organization.id,
                    InterviewTurn.session_id == session.id,
                )
                .order_by(InterviewTurn.sequence_no)
            )
        )

    return InterviewRead(
        organization_id=organization.id,
        organization_name=organization.name,
        assessment_id=assessment.id,
        assessment_title=assessment.title,
        assessment_status=assessment.status,
        kb_version=assessment.kb_version,
        participant_id=participant.id if participant is not None else None,
        session=_session_read(session) if session is not None else None,
        turns=[_turn_read(turn) for turn in turns],
        in_scope_controls=[
            InterviewControlRead(
                id=control.id,
                code=control.control_code,
                title=control.control_title,
            )
            for control in controls
        ],
        draft_results=[
            InterviewDraftResultRead(
                id=result.id,
                assessment_control_id=control.id,
                control_code=control.control_code,
                control_title=control.control_title,
                status=result.control_status,
                explanation=result.explanation,
                justification=result.justification,
                not_assessed_reason=result.not_assessed_reason,
                confidence=float(result.confidence) if result.confidence is not None else None,
                requires_human_review=result.requires_human_review,
                evidence_pending=result.evidence_pending,
                evidence_summary=result.evidence_summary,
                evidence_refs=result.evidence_refs,
                trace_id=result.trace_id,
                created_at=result.created_at,
            )
            for result, control in latest_drafts.values()
        ],
        resumed=resumed,
    )


def _session_read(session: AssessmentSession) -> InterviewSessionRead:
    return InterviewSessionRead(
        id=session.id,
        session_type=session.session_type,
        block_id=session.block_id,
        facilitator_user_id=session.facilitator_user_id,
        scheduled_at=session.scheduled_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
        resume_summary=session.resume_summary,
    )


def _turn_read(turn: InterviewTurn) -> InterviewTurnRead:
    return InterviewTurnRead(
        id=turn.id,
        sequence_no=turn.sequence_no,
        speaker=turn.speaker,
        participant_id=turn.participant_id,
        turn_type=turn.turn_type,
        question_id=turn.question_id,
        replies_to_turn_id=turn.replies_to_turn_id,
        content=turn.content,
        language_code=turn.language_code,
        created_at=turn.created_at,
        source_references=[
            InterviewSourceReference(
                type="interview_turn",
                ref=f"interview_turn:{turn.id}",
            )
        ],
    )


def _resolve_idempotency_key(client_request_id: UUID | None, header_key: str | None) -> str:
    normalized_header = header_key.strip() if header_key is not None else None
    if normalized_header == "":
        normalized_header = None
    if normalized_header is not None and len(normalized_header) > 128:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key must be at most 128 characters.",
        )

    body_key = str(client_request_id) if client_request_id is not None else None
    if body_key is not None and normalized_header is not None and body_key != normalized_header:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="client_request_id and Idempotency-Key must match when both are provided.",
        )
    request_key = body_key or normalized_header
    if request_key is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide client_request_id or the Idempotency-Key header.",
        )
    return request_key


def _same_turn_request(
    existing: InterviewTurn,
    participant_id: UUID,
    data: InterviewTurnCreate,
) -> bool:
    return (
        existing.speaker == "participant"
        and existing.participant_id == participant_id
        and existing.turn_type == "answer"
        and existing.question_id == data.question_id
        and existing.replies_to_turn_id == data.replies_to_turn_id
        and existing.content == data.content
        and existing.language_code == data.language_code
    )
