import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from app.core.config import Settings
from app.api.v1.endpoints import auth as auth_endpoint
from app.security.auth import _load_user_from_token
from app.schemas.organizations import InvitationAccept
from app.security.invitations import create_invitation_token, hash_invitation_token
from app.security.supabase import (
    SupabaseIdentity,
    SupabaseInvalidToken,
    SupabaseUnavailable,
    SupabaseUserAlreadyExists,
    create_invited_identity,
    get_verified_identity,
)


def settings() -> Settings:
    return Settings(
        supabase_url="https://project.example.supabase.co",
        supabase_publishable_key="sb_publishable_test-key",
        supabase_secret_key="sb_secret_test-key",
    )


class SupabaseConfigurationTests(unittest.TestCase):
    def test_production_requires_supabase_keys_and_https_urls(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(app_environment="production", app_base_url="https://app.example.com")

        configured = Settings(
            app_environment="production",
            app_base_url="https://app.example.com",
            supabase_url="https://project.example.supabase.co/",
            supabase_publishable_key="sb_publishable_public-key",
            supabase_secret_key="sb_secret_server-key",
            smtp_host="smtp.example.com",
            smtp_sender_email="noreply@example.com",
            smtp_starttls=True,
        )
        self.assertEqual(configured.supabase_url, "https://project.example.supabase.co")

    def test_rejects_non_https_supabase_url_outside_local_development(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(supabase_url="http://supabase.example.com")
        with self.assertRaises(ValidationError):
            Settings(supabase_url="http://localhost.attacker.example")


class InvitationTokenTests(unittest.TestCase):
    def test_invitation_tokens_are_random_and_stored_as_hashes(self) -> None:
        token, token_hash = create_invitation_token()

        self.assertGreaterEqual(len(token), 32)
        self.assertEqual(hash_invitation_token(token), token_hash)
        self.assertNotEqual(token, token_hash)


class SupabaseAuthServiceTests(unittest.TestCase):
    def test_validates_access_tokens_with_supabase_and_normalizes_identity(self) -> None:
        response = Mock(
            status_code=200,
            is_success=True,
            json=Mock(
                return_value={
                    "id": str(uuid4()),
                    "email": "Admin@Example.com",
                    "email_confirmed_at": "2026-10-01T12:00:00Z",
                }
            ),
        )
        with patch("app.security.supabase.httpx.get", return_value=response) as request:
            identity = get_verified_identity("supabase-access-token", settings())

        self.assertEqual(identity.email, "admin@example.com")
        self.assertTrue(identity.email_verified)
        self.assertEqual(request.call_args.args[0], "https://project.example.supabase.co/auth/v1/user")
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"],
            "Bearer supabase-access-token",
        )
        self.assertEqual(request.call_args.kwargs["headers"]["apikey"], "sb_publishable_test-key")

    def test_rejects_access_tokens_not_accepted_by_supabase(self) -> None:
        response = Mock(status_code=401, is_success=False)
        with patch("app.security.supabase.httpx.get", return_value=response):
            with self.assertRaises(SupabaseInvalidToken):
                get_verified_identity("invalid-token", settings())

    def test_reports_auth_service_unavailability_without_exposing_response_body(self) -> None:
        with patch(
            "app.security.supabase.httpx.get",
            side_effect=httpx.ConnectError("private network detail"),
        ):
            with self.assertRaises(SupabaseUnavailable):
                get_verified_identity("access-token", settings())

    def test_creates_confirmed_invited_identity_using_server_key(self) -> None:
        user_id = uuid4()
        response = Mock(
            status_code=200,
            is_success=True,
            json=Mock(
                return_value={
                    "id": str(user_id),
                    "email": "invitee@example.com",
                    "email_confirmed_at": "2026-10-01T12:00:00Z",
                }
            ),
        )
        with patch("app.security.supabase.httpx.post", return_value=response) as request:
            identity = create_invited_identity(
                "invitee@example.com", "secure-password-123", settings()
            )

        self.assertEqual(identity, SupabaseIdentity(user_id, "invitee@example.com", True))
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"], "Bearer sb_secret_test-key"
        )
        self.assertEqual(
            request.call_args.kwargs["json"],
            {
                "email": "invitee@example.com",
                "password": "secure-password-123",
                "email_confirm": True,
            },
        )

    def test_translates_existing_supabase_account_to_a_conflict(self) -> None:
        response = Mock(
            status_code=422,
            is_success=False,
            json=Mock(return_value={"code": "email_exists", "msg": "User already registered"}),
        )
        with patch("app.security.supabase.httpx.post", return_value=response):
            with self.assertRaises(SupabaseUserAlreadyExists):
                create_invited_identity("existing@example.com", "secure-password-123", settings())


class CurrentUserAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Mock()
        self.settings = settings()
        self.identity = SupabaseIdentity(uuid4(), "admin@example.com", True)
        self.credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="supabase-access-token"
        )

    def test_resolves_supabase_identity_to_active_platform_profile(self) -> None:
        user = SimpleNamespace(
            id=self.identity.id,
            email=self.identity.email,
            is_platform_admin=True,
            deactivated_at=None,
        )
        self.db.get.return_value = user
        with patch("app.security.auth.get_verified_identity", return_value=self.identity):
            current_user = _load_user_from_token(
                self.credentials.credentials, self.db, self.settings
            )

        self.assertIs(current_user, user)

    def test_rejects_unverified_email(self) -> None:
        identity = SupabaseIdentity(self.identity.id, self.identity.email, False)
        with patch("app.security.auth.get_verified_identity", return_value=identity):
            with self.assertRaises(HTTPException) as response:
                _load_user_from_token(self.credentials.credentials, self.db, self.settings)
        self.assertEqual(response.exception.status_code, 401)

    def test_provisions_a_profile_from_a_verified_supabase_identity(self) -> None:
        self.db.get.return_value = None
        self.db.scalar.return_value = None
        with patch("app.security.auth.get_verified_identity", return_value=self.identity):
            user = _load_user_from_token(self.credentials.credentials, self.db, self.settings)

        self.assertEqual(user.id, self.identity.id)
        self.assertEqual(user.email, self.identity.email)
        self.db.add.assert_called_once_with(user)
        self.db.commit.assert_called_once()


class InvitationAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Mock()
        self.settings = settings()
        self.token = "one-time-invitation-token-value-that-is-long-enough"
        self.invitation = SimpleNamespace(
            id=uuid4(),
            organization_id=uuid4(),
            email="invitee@example.com",
            role="representative",
            status="pending",
            token_hash=hash_invitation_token(self.token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted_by_user_id=None,
            accepted_at=None,
        )
        self.payload = InvitationAccept(token=self.token, password="a-secure-password-123")

    def test_acceptance_creates_auth_linked_profile_and_membership(self) -> None:
        identity = SupabaseIdentity(uuid4(), "invitee@example.com", True)
        self.db.scalar.side_effect = [self.invitation, None, None]
        with patch.object(auth_endpoint, "create_invited_identity", return_value=identity):
            result = auth_endpoint.accept_invitation_and_create_profile(
                self.payload, self.db, self.settings
            )

        self.assertEqual(result.email, "invitee@example.com")
        self.assertEqual(result.role, "representative")
        self.assertEqual(self.invitation.status, "accepted")
        self.assertIsNone(self.invitation.token_hash)
        self.db.commit.assert_called_once()
        created_profile, membership = self.db.add.call_args_list
        self.assertEqual(created_profile.args[0].id, identity.id)
        self.assertEqual(membership.args[0].user_id, identity.id)
        self.assertEqual(membership.args[0].organization_id, self.invitation.organization_id)

    def test_expired_invitation_is_marked_and_cannot_create_an_account(self) -> None:
        self.invitation.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.db.scalar.return_value = self.invitation
        with patch.object(auth_endpoint, "create_invited_identity") as create_user:
            with self.assertRaises(HTTPException) as response:
                auth_endpoint.accept_invitation_and_create_profile(
                    self.payload, self.db, self.settings
                )

        self.assertEqual(response.exception.status_code, 410)
        self.assertEqual(self.invitation.status, "expired")
        self.assertIsNone(self.invitation.token_hash)
        create_user.assert_not_called()

    def test_existing_profile_cannot_be_overwritten_by_invitation_activation(self) -> None:
        existing_profile = SimpleNamespace(id=uuid4())
        self.db.scalar.side_effect = [self.invitation, existing_profile]
        with patch.object(auth_endpoint, "create_invited_identity") as create_user:
            with self.assertRaises(HTTPException) as response:
                auth_endpoint.accept_invitation_and_create_profile(
                    self.payload, self.db, self.settings
                )

        self.assertEqual(response.exception.status_code, 409)
        create_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
