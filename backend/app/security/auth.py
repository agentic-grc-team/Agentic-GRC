from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.core.config import Settings, get_settings
from app.db.models import User
from app.security.supabase import (
    SupabaseIdentity,
    SupabaseInvalidToken,
    SupabaseUnavailable,
    get_verified_identity,
)


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid Supabase session is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _profile_for_identity(identity: SupabaseIdentity, db: Session) -> User:
    if not identity.email_verified:
        raise _unauthorized()

    user = db.get(User, identity.id)
    if user is None:
        conflicting_user = db.scalar(
            select(User.id).where(func.lower(func.btrim(User.email)) == identity.email)
        )
        if conflicting_user is not None:
            raise _unauthorized()
        user = User(id=identity.id, email=identity.email)
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError as exc:
            db.rollback()
            user = db.get(User, identity.id)
            if user is None:
                raise _unauthorized() from exc
    elif user.deactivated_at is not None:
        raise _unauthorized()
    elif user.email != identity.email:
        user.email = identity.email
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError as exc:
            db.rollback()
            raise _unauthorized() from exc

    if user.deactivated_at is not None:
        raise _unauthorized()
    return user


def _load_user_from_token(
    access_token: str,
    db: Session,
    settings: Settings,
) -> User:
    try:
        identity = get_verified_identity(access_token, settings)
    except SupabaseInvalidToken as exc:
        raise _unauthorized() from exc
    except SupabaseUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth is temporarily unavailable.",
        ) from exc
    return _profile_for_identity(identity, db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return _load_user_from_token(credentials.credentials, db, settings)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> User | None:
    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return _load_user_from_token(credentials.credentials, db, settings)
