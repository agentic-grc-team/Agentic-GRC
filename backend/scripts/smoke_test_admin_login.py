"""Run a credential-safe Supabase Auth and platform-admin smoke test."""

from __future__ import annotations

import json
import os
import sys
from getpass import getpass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT_SECONDS = 10


def request_json(
    url: str,
    *,
    method: str,
    payload: dict | None = None,
    token: str | None = None,
    api_key: str | None = None,
) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if api_key is not None:
        headers["apikey"] = api_key

    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object from the service.")
    return result


def main() -> int:
    settings = get_settings()
    if not settings.supabase_url or settings.supabase_publishable_key is None:
        print("Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in backend/.env first.")
        return 2

    base_url = os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
    email = input("Administrator email: ").strip().lower()
    password = getpass("Administrator password: ")
    if not email or not password:
        print("An email address and password are required.")
        return 2

    try:
        auth_result = request_json(
            f"{settings.supabase_url}/auth/v1/token?grant_type=password",
            method="POST",
            payload={"email": email, "password": password},
            api_key=settings.supabase_publishable_key.get_secret_value(),
        )
    except HTTPError as exc:
        print(f"Supabase sign-in failed (HTTP {exc.code}).")
        return 1
    except URLError:
        print("Could not reach Supabase Auth. Check SUPABASE_URL and network access.")
        return 1
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        print("Supabase Auth returned an invalid sign-in response.")
        return 1

    access_token = auth_result.get("access_token")
    auth_user = auth_result.get("user")
    if (
        not isinstance(access_token, str)
        or not access_token
        or not isinstance(auth_user, dict)
        or str(auth_user.get("email", "")).lower() != email
    ):
        print("Supabase did not authenticate the requested account.")
        return 1

    try:
        current_user = request_json(
            f"{base_url}/api/v1/auth/me",
            method="GET",
            token=access_token,
        )
    except HTTPError as exc:
        print(f"The backend rejected the Supabase token (HTTP {exc.code}).")
        return 1
    except URLError:
        print(f"Could not reach the API at {base_url}. Start FastAPI and try again.")
        return 1
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        print("The API returned an invalid /auth/me response.")
        return 1

    if (
        current_user.get("email", "").lower() != email
        or current_user.get("is_platform_admin") is not True
    ):
        print("The authenticated account does not have platform administrator access.")
        return 1

    print("PASS: Supabase email/password authentication succeeded.")
    print("PASS: /api/v1/auth/me verified the Supabase token and platform admin profile.")
    print("The password and bearer token were not displayed or saved by this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
