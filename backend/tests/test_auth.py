import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from app.schemas.auth import LoginRequest

from app.api.v1.endpoints import auth as auth_endpoint
from app.core.config import Settings
from app.security.invitations import create_invitation_token, hash_invitation_token
from app.security.passwords import hash_password, verify_password


class PasswordSecurityTests(unittest.TestCase):
    def test_authentication_settings_reject_weak_jwt_secrets(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(jwt_secret="too-short")

    def test_hash_verifies_password_without_storing_plaintext(self) -> None:
        password = "correct horse battery staple 9"
        password_hash = hash_password(password)

        self.assertTrue(password_hash.startswith("scrypt$"))
        self.assertNotIn(password, password_hash)
        self.assertTrue(verify_password(password, password_hash))
        self.assertFalse(verify_password("incorrect password", password_hash))

    def test_password_length_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            hash_password("short")
        with self.assertRaises(ValueError):
            hash_password("x" * 129)

    def test_invitation_tokens_are_random_and_stored_as_hashes(self) -> None:
        token, token_hash = create_invitation_token()

        self.assertGreaterEqual(len(token), 32)
        self.assertEqual(hash_invitation_token(token), token_hash)
        self.assertNotEqual(token, token_hash)


class LoginApiTests(unittest.TestCase):
    def setUp(self) -> None:
        auth_endpoint._attempts.clear()
        self.user = SimpleNamespace(
            id=uuid4(),
            email="admin@example.com",
            password_hash=hash_password("correct horse battery staple 9"),
            email_verified_at=object(),
            deactivated_at=None,
            is_platform_admin=True,
        )
        self.db = Mock()
        self.db.scalar.return_value = self.user
        self.db.get.return_value = self.user

        self.settings = Settings(jwt_secret="unit-test-secret-with-at-least-32-bytes")
        self.request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/login",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )

    def tearDown(self) -> None:
        auth_endpoint._attempts.clear()

    def test_login_returns_bearer_token_for_verified_active_user(self) -> None:
        response = auth_endpoint.login(
            LoginRequest(email="ADMIN@example.com", password="correct horse battery staple 9"),
            self.request,
            self.db,
            self.settings,
        )

        self.assertEqual(response.token_type, "bearer")
        self.assertEqual(response.user.email, "admin@example.com")
        self.assertTrue(response.access_token)

    def test_login_rejects_invalid_password_and_rate_limits_repeated_failures(self) -> None:
        for _ in range(5):
            with self.assertRaises(HTTPException) as response:
                auth_endpoint.login(
                    LoginRequest(email=self.user.email, password="incorrect password"),
                    self.request,
                    self.db,
                    self.settings,
                )
            self.assertEqual(response.exception.status_code, 401)

        with self.assertRaises(HTTPException) as limited:
            auth_endpoint.login(
                LoginRequest(email=self.user.email, password="correct horse battery staple 9"),
                self.request,
                self.db,
                self.settings,
            )
        self.assertEqual(limited.exception.status_code, 429)

    def test_login_rejects_unverified_or_deactivated_users(self) -> None:
        self.user.email_verified_at = None
        with self.assertRaises(HTTPException) as response:
            auth_endpoint.login(
                LoginRequest(email=self.user.email, password="correct horse battery staple 9"),
                self.request,
                self.db,
                self.settings,
            )
        self.assertEqual(response.exception.status_code, 401)

        self.user.email_verified_at = object()
        self.user.deactivated_at = object()
        with self.assertRaises(HTTPException) as response:
            auth_endpoint.login(
                LoginRequest(email=self.user.email, password="correct horse battery staple 9"),
                self.request,
                self.db,
                self.settings,
            )
        self.assertEqual(response.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
