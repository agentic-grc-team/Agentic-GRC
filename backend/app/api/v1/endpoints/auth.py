import hashlib
import threading
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.core.config import Settings, get_settings
from app.db.models import OrganizationInvitation, OrganizationMembership, User
from app.schemas.auth import AuthenticatedUser, CurrentUserResponse, LoginRequest, LoginResponse
from app.schemas.organizations import InvitationAccept, InvitationAccepted
from app.security.auth import create_access_token, get_current_user
from app.security.invitations import hash_invitation_token
from app.security.passwords import hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["authentication"])
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")
_ATTEMPT_WINDOW_SECONDS = 15 * 60
_ATTEMPT_LIMIT = 5
_attempts: dict[str, deque[float]] = {}
_attempts_lock = threading.Lock()


def _rate_limit_key(request: Request, email: str) -> str:
    remote_host = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"{remote_host}:{email}".encode("utf-8")).hexdigest()


def _is_rate_limited(key: str, now: float) -> bool:
    with _attempts_lock:
        attempts = _attempts.get(key)
        if attempts is None:
            return False
        while attempts and attempts[0] <= now - _ATTEMPT_WINDOW_SECONDS:
            attempts.popleft()
        if not attempts:
            _attempts.pop(key, None)
        return len(attempts) >= _ATTEMPT_LIMIT


def _record_failed_attempt(key: str, now: float) -> None:
    with _attempts_lock:
        attempts = _attempts.get(key)
        if attempts is None:
            if len(_attempts) >= 10_000:
                _attempts.pop(next(iter(_attempts)))
            attempts = _attempts.setdefault(key, deque())
        while attempts and attempts[0] <= now - _ATTEMPT_WINDOW_SECONDS:
            attempts.popleft()
        attempts.append(now)


def _clear_attempts(key: str) -> None:
    with _attempts_lock:
        _attempts.pop(key, None)


def _public_user(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(id=user.id, email=user.email, is_platform_admin=user.is_platform_admin)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    normalized_email = str(payload.email).strip().lower()
    key = _rate_limit_key(request, normalized_email)
    now_monotonic = time.monotonic()
    if _is_rate_limited(key, now_monotonic):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Try again later.",
            headers={"Retry-After": str(_ATTEMPT_WINDOW_SECONDS)},
        )

    user = db.scalar(
        select(User).where(func.lower(func.btrim(User.email)) == normalized_email)
    )
    stored_hash = user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, stored_hash)
    if (
        user is None
        or user.deactivated_at is not None
        or user.email_verified_at is None
        or not password_valid
    ):
        _record_failed_attempt(key, now_monotonic)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _clear_attempts(key)
    access_token, expires_at = create_access_token(user, settings)
    return LoginResponse(
        access_token=access_token,
        expires_at=expires_at,
        user=_public_user(user),
    )


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
) -> InvitationAccepted:
    now = datetime.now(timezone.utc)
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
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invitation is no longer active.")

        normalized_email = invitation.email.strip().lower()
        user = db.scalar(
            select(User)
            .where(func.lower(func.btrim(User.email)) == normalized_email)
            .with_for_update()
        )
        if user is not None and user.password_hash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists for this email. Sign in and accept the invitation from your account.",
            )

        if user is None:
            user = User(email=normalized_email)
            db.add(user)
            db.flush()
        user.password_hash = hash_password(payload.password)
        user.email_verified_at = now

        existing_membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == invitation.organization_id,
                OrganizationMembership.user_id == user.id,
            )
        )
        if existing_membership is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This user already belongs to the organization.")

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
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The invitation could not be accepted because the account or membership already exists.",
        ) from exc
