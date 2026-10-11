from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class SupabaseIdentity:
    id: UUID
    email: str
    email_verified: bool


class SupabaseInvalidToken(Exception):
    """The Supabase Auth service rejected an access token."""


class SupabaseUserAlreadyExists(Exception):
    """An invitation attempted to create an identity that already exists."""


class SupabaseUnavailable(Exception):
    """Supabase Auth could not complete a request."""


def _base_url(settings: Settings) -> str:
    if not settings.supabase_url:
        raise SupabaseUnavailable("Supabase Auth is not configured.")
    return settings.supabase_url.rstrip("/")


def _publishable_key(settings: Settings) -> str:
    if settings.supabase_publishable_key is None:
        raise SupabaseUnavailable("Supabase Auth is not configured.")
    return settings.supabase_publishable_key.get_secret_value()


def _secret_key(settings: Settings) -> str:
    if settings.supabase_secret_key is None:
        raise SupabaseUnavailable("Supabase Admin Auth is not configured.")
    return settings.supabase_secret_key.get_secret_value()


def _parse_identity(payload: object) -> SupabaseIdentity:
    if not isinstance(payload, dict):
        raise SupabaseUnavailable("Supabase Auth returned an invalid response.")
    try:
        user_id = UUID(str(payload["id"]))
        email = str(payload["email"]).strip().lower()
    except (KeyError, TypeError, ValueError) as exc:
        raise SupabaseUnavailable("Supabase Auth returned an incomplete user profile.") from exc
    if not email:
        raise SupabaseUnavailable("Supabase Auth returned a user without an email address.")
    return SupabaseIdentity(
        id=user_id,
        email=email,
        email_verified=bool(payload.get("email_confirmed_at") or payload.get("confirmed_at")),
    )


def get_verified_identity(access_token: str, settings: Settings) -> SupabaseIdentity:
    """Validate a bearer token against Supabase Auth instead of trusting its claims locally."""
    try:
        response = httpx.get(
            f"{_base_url(settings)}/auth/v1/user",
            headers={
                "apikey": _publishable_key(settings),
                "Authorization": f"Bearer {access_token}",
            },
            timeout=5.0,
        )
    except httpx.RequestError as exc:
        raise SupabaseUnavailable("Supabase Auth is temporarily unavailable.") from exc

    if response.status_code in (401, 403):
        raise SupabaseInvalidToken
    if response.status_code >= 500:
        raise SupabaseUnavailable("Supabase Auth is temporarily unavailable.")
    if not response.is_success:
        raise SupabaseUnavailable("Supabase Auth rejected the user lookup.")
    try:
        return _parse_identity(response.json())
    except ValueError as exc:
        raise SupabaseUnavailable("Supabase Auth returned invalid JSON.") from exc


def create_invited_identity(email: str, password: str, settings: Settings) -> SupabaseIdentity:
    """Create a confirmed Auth identity after validating the application's invite token."""
    secret_key = _secret_key(settings)
    try:
        response = httpx.post(
            f"{_base_url(settings)}/auth/v1/admin/users",
            headers={
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password, "email_confirm": True},
            timeout=8.0,
        )
    except httpx.RequestError as exc:
        raise SupabaseUnavailable("Supabase Admin Auth is temporarily unavailable.") from exc

    if response.status_code in (400, 409, 422):
        try:
            detail = response.json()
        except ValueError:
            detail = {}
        error_text = " ".join(
            str(detail.get(key, "")) for key in ("code", "msg", "message", "error")
        ).lower() if isinstance(detail, dict) else ""
        if "already" in error_text or "exists" in error_text or "registered" in error_text:
            raise SupabaseUserAlreadyExists from None
    if not response.is_success:
        raise SupabaseUnavailable("Supabase could not create the invited account.")
    return _parse_identity(response.json())


def delete_auth_identity(user_id: UUID, settings: Settings) -> bool:
    """Compensate for a failed database commit after creating a new Auth identity."""
    secret_key = _secret_key(settings)
    try:
        response = httpx.delete(
            f"{_base_url(settings)}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
            },
            timeout=8.0,
        )
    except httpx.RequestError:
        return False
    return response.is_success or response.status_code == 404
