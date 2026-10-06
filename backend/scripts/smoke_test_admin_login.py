"""Run a credential-safe smoke test for the local platform administrator."""

from __future__ import annotations

import json
import os
import sys
from getpass import getpass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT_SECONDS = 10


def request_json(
    url: str,
    *,
    method: str,
    payload: dict | None = None,
    token: str | None = None,
) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object from the API.")
    return result


def main() -> int:
    base_url = os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
    email = input("Administrator email: ").strip().lower()
    if not email:
        print("An email address is required.")
        return 2

    password = getpass("Administrator password: ")
    if not password:
        print("A password is required.")
        return 2

    try:
        login_result = request_json(
            f"{base_url}/api/v1/auth/login",
            method="POST",
            payload={"email": email, "password": password},
        )
    except HTTPError as exc:
        if exc.code == 503:
            print("Login is not configured. Set JWT_SECRET in backend/.env and restart the API.")
        else:
            print(f"Administrator login failed (HTTP {exc.code}).")
        return 1
    except URLError:
        print(f"Could not reach the API at {base_url}. Start the backend and try again.")
        return 1
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        print("The API returned an invalid login response.")
        return 1

    access_token = login_result.get("access_token")
    login_user = login_result.get("user")
    if (
        login_result.get("token_type") != "bearer"
        or not isinstance(access_token, str)
        or not access_token
        or not isinstance(login_user, dict)
        or login_user.get("email", "").lower() != email
        or login_user.get("is_platform_admin") is not True
    ):
        print("Login response did not identify the requested account as a platform administrator.")
        return 1

    try:
        current_user = request_json(
            f"{base_url}/api/v1/auth/me",
            method="GET",
            token=access_token,
        )
    except HTTPError as exc:
        print(f"The issued bearer token was rejected by /auth/me (HTTP {exc.code}).")
        return 1
    except URLError:
        print("Could not verify the bearer token with /auth/me.")
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

    print("PASS: administrator login succeeded and returned a bearer token.")
    print("PASS: /api/v1/auth/me confirmed platform administrator access.")
    print("The password and bearer token were not displayed or saved by this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
