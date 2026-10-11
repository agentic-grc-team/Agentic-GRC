import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.core.config import Settings, get_settings
from app.db.models import OrganizationInvitation, OrganizationMembership, User
from app.schemas.auth import AuthenticatedUser, CurrentUserResponse
from app.schemas.organizations import InvitationAccept, InvitationAccepted
from app.security.auth import get_current_user
from app.security.invitations import hash_invitation_token
from app.security.supabase import (
    SupabaseUnavailable,
    SupabaseUserAlreadyExists,
    create_invited_identity,
    delete_auth_identity,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


def _public_user(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(id=user.id, email=user.email, is_platform_admin=user.is_platform_admin)


@router.get("/me", response_model=CurrentUserResponse)
def current_user(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        is_platform_admin=user.is_platform_admin,
    )


@router.post("/accept-invitation", response_model=InvitationAccepted)
def accept_invitation_and_create_profile(
    payload: InvitationAccept,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> InvitationAccepted:
    now = datetime.now(timezone.utc)
    created_auth_user_id = None
    try:
        invitation = db.scalar(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.token_hash == hash_invitation_token(payload.token))
            .with_for_update()
        )
        if invitation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
        if invitation.status != "pending" or invitation.expires_at <= now:
            if invitation.status == "pending" and invitation.expires_at <= now:
                invitation.status = "expired"
                invitation.token_hash = None
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This invitation is no longer active.",
            )

        normalized_email = invitation.email.strip().lower()
        existing_profile = db.scalar(
            select(User).where(func.lower(func.btrim(User.email)) == normalized_email)
        )
        if existing_profile is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists for this email. Sign in and accept the invitation from your account.",
            )

        identity = create_invited_identity(normalized_email, payload.password, settings)
        created_auth_user_id = identity.id
        if identity.email != normalized_email or not identity.email_verified:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Supabase did not confirm the invited account as expected.",
            )

        user = User(id=identity.id, email=identity.email)
        db.add(user)
        db.flush()
        existing_membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == invitation.organization_id,
                OrganizationMembership.user_id == user.id,
            )
        )
        if existing_membership is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This user already belongs to the organization.",
            )

        db.add(
            OrganizationMembership(
                organization_id=invitation.organization_id,
                user_id=user.id,
                role=invitation.role,
                status="active",
            )
        )
        invitation.status = "accepted"
        invitation.accepted_by_user_id = user.id
        invitation.accepted_at = now
        invitation.token_hash = None
        db.commit()
        return InvitationAccepted(
            invitation_id=invitation.id,
            organization_id=invitation.organization_id,
            email=user.email,
            role=invitation.role,
            membership_status="active",
        )
    except SupabaseUserAlreadyExists as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for this email. Sign in and accept the invitation from your account.",
        ) from exc
    except SupabaseUnavailable as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth is temporarily unavailable. Please try again.",
        ) from exc
    except HTTPException:
        db.rollback()
        if created_auth_user_id is not None:
            _remove_orphan_auth_user(created_auth_user_id, settings)
        raise
    except IntegrityError as exc:
        db.rollback()
        if created_auth_user_id is not None:
            _remove_orphan_auth_user(created_auth_user_id, settings)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The invitation could not be accepted because the account or membership already exists.",
        ) from exc
    except Exception:
        db.rollback()
        if created_auth_user_id is not None:
            _remove_orphan_auth_user(created_auth_user_id, settings)
        raise


def _remove_orphan_auth_user(user_id, settings: Settings) -> None:
    if not delete_auth_identity(user_id, settings):
        logger.error("Could not clean up an Auth identity after invitation acceptance failed.")
