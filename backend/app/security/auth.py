from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.core.config import Settings, get_settings
from app.db.models import User


bearer_scheme = HTTPBearer(auto_error=False)
_ALLOWED_ALGORITHMS = ["HS256"]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid email and password session is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _jwt_secret(settings: Settings) -> str:
    if settings.jwt_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email authentication is not configured. Set JWT_SECRET.",
        )
    return settings.jwt_secret.get_secret_value()


def create_access_token(user: User, settings: Settings) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_access_token_minutes)
    claims = {
        "sub": str(user.id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": expires_at,
        "token_type": "access",
    }
    token = jwt.encode(claims, _jwt_secret(settings), algorithm="HS256")
    return token, expires_at


def _load_user_from_token(
    credentials: HTTPAuthorizationCredentials,
    db: Session,
    settings: Settings,
) -> User:
    try:
        claims = jwt.decode(
            credentials.credentials,
            _jwt_secret(settings),
            algorithms=_ALLOWED_ALGORITHMS,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["iss", "aud", "exp", "iat", "sub", "token_type"]},
        )
        if claims.get("token_type") != "access":
            raise _unauthorized()
        user_id = UUID(claims["sub"])
    except HTTPException:
        raise
    except (PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise _unauthorized() from exc

    user = db.get(User, user_id)
    if user is None or user.deactivated_at is not None or user.email_verified_at is None:
        raise _unauthorized()
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return _load_user_from_token(credentials, db, settings)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> User | None:
    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return _load_user_from_token(credentials, db, settings)
