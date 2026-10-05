from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import Settings, get_settings


bearer_scheme = HTTPBearer(auto_error=False)
_email_adapter = TypeAdapter(EmailStr)
_ALLOWED_ALGORITHMS = ["RS256", "ES256"]


@dataclass(frozen=True)
class AuthenticatedIdentity:
    issuer: str
    subject: str
    email: str


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, timeout=5)


def get_authenticated_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedIdentity:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    issuer = settings.auth_issuer
    audience = settings.auth_audience
    jwks_url = settings.auth_jwks_url
    if not issuer or not audience or not jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured. Set AUTH_ISSUER, AUTH_AUDIENCE, and AUTH_JWKS_URL.",
        )
    if not issuer.startswith("https://") or not jwks_url.startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The OIDC issuer and JWKS URL must use HTTPS.",
        )

    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in _ALLOWED_ALGORITHMS:
            raise jwt.InvalidAlgorithmError("Unsupported signing algorithm")
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=_ALLOWED_ALGORITHMS,
            audience=audience,
            issuer=issuer,
            options={"require": ["iss", "aud", "exp", "sub", "email", "email_verified"]},
        )
    except PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The identity provider's signing keys are temporarily unavailable.",
        ) from exc
    except (jwt.PyJWTError, PyJWKClientError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The bearer token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = claims.get("sub")
    email_claim = claims.get("email")
    if not isinstance(subject, str) or not subject.strip() or claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The token must identify a subject with a verified email address.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        email = str(_email_adapter.validate_python(email_claim)).strip().lower()
    except (ValidationError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The token does not contain a valid verified email address.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthenticatedIdentity(issuer=issuer, subject=subject, email=email)
