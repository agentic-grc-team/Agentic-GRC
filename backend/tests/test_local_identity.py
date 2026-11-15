"""Unit tests for mirroring Supabase-verified identities into a self-hosted auth.users."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
from uuid import uuid4

from fastapi import HTTPException

from app.api.v1.endpoints import auth as auth_endpoint
from app.core.config import Settings
from app.schemas.organizations import InvitationAccept
from app.security.auth import _load_user_from_token
from app.security.invitations import hash_invitation_token
from app.security.local_identity import (
    LocalIdentityMirrorRefused,
    mirror_verified_identity,
)
from app.security.supabase import SupabaseIdentity


def settings(mirror: bool) -> Settings:
    return Settings(
        supabase_url="https://project.example.supabase.co",
        supabase_publishable_key="sb_publishable_test-key",
        supabase_secret_key="sb_secret_test-key",
        auth_mirror_local_identities=mirror,
    )


class MirrorVerifiedIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Mock()
        self.identity = SupabaseIdentity(uuid4(), "user@example.com", True)

    def test_defaults_to_disabled(self) -> None:
        self.assertFalse(Settings().auth_mirror_local_identities)

    def test_does_nothing_when_disabled(self) -> None:
        mirror_verified_identity(self.identity, self.db, settings(False))
        self.db.execute.assert_not_called()
        self.db.scalar.assert_not_called()

    def test_does_nothing_for_unverified_identity(self) -> None:
        identity = SupabaseIdentity(uuid4(), "user@example.com", False)
        mirror_verified_identity(identity, self.db, settings(True))
        self.db.execute.assert_not_called()
        self.db.scalar.assert_not_called()

    def test_writes_one_row_on_a_self_hosted_database(self) -> None:
        self.db.scalar.return_value = False
        mirror_verified_identity(self.identity, self.db, settings(True))
        self.db.execute.assert_called_once()
        params = self.db.execute.call_args.args[1]
        self.assertEqual(params, {"id": self.identity.id, "email": "user@example.com"})
        self.db.commit.assert_not_called()

    def test_database_error_on_write_is_refused(self) -> None:
        from sqlalchemy.exc import ProgrammingError

        self.db.scalar.return_value = False
        self.db.execute.side_effect = ProgrammingError(
            "INSERT INTO auth.users", {}, Exception("permission denied for table users")
        )
        with self.assertRaises(LocalIdentityMirrorRefused):
            mirror_verified_identity(self.identity, self.db, settings(True))

    def test_refuses_to_write_on_supabase(self) -> None:
        self.db.scalar.return_value = True
        with self.assertRaises(LocalIdentityMirrorRefused):
            mirror_verified_identity(self.identity, self.db, settings(True))
        self.db.execute.assert_not_called()


class CurrentUserMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Mock()
        self.identity = SupabaseIdentity(uuid4(), "new@example.com", True)

    def test_mirrors_before_adding_a_new_profile(self) -> None:
        self.db.get.return_value = None
        self.db.scalar.return_value = None
        order = Mock()
        order.attach_mock(self.db.add, "add")
        with (
            patch("app.security.auth.get_verified_identity", return_value=self.identity),
            patch("app.security.auth.mirror_verified_identity") as mirror,
        ):
            order.attach_mock(mirror, "mirror")
            user = _load_user_from_token("token", self.db, settings(True))

        self.assertEqual(user.id, self.identity.id)
        names = [entry[0] for entry in order.mock_calls]
        self.assertLess(names.index("mirror"), names.index("add"))

    def test_mirrors_before_updating_a_changed_email(self) -> None:
        existing = SimpleNamespace(
            id=self.identity.id, email="old@example.com", deactivated_at=None
        )
        self.db.get.return_value = existing
        with (
            patch("app.security.auth.get_verified_identity", return_value=self.identity),
            patch("app.security.auth.mirror_verified_identity") as mirror,
        ):
            user = _load_user_from_token("token", self.db, settings(True))

        mirror.assert_called_once()
        self.assertEqual(user.email, "new@example.com")

    def test_refused_mirror_returns_503_and_rolls_back(self) -> None:
        self.db.get.return_value = None
        self.db.scalar.return_value = None
        with (
            patch("app.security.auth.get_verified_identity", return_value=self.identity),
            patch(
                "app.security.auth.mirror_verified_identity",
                side_effect=LocalIdentityMirrorRefused("supabase"),
            ),
        ):
            with self.assertRaises(HTTPException) as response:
                _load_user_from_token("token", self.db, settings(True))

        self.assertEqual(response.exception.status_code, 503)
        self.db.rollback.assert_called_once()
        self.db.add.assert_not_called()


class InvitationMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        from datetime import datetime, timedelta, timezone

        self.db = Mock()
        self.token = "one-time-invitation-token-value-that-is-long-enough"
        self.invitation = SimpleNamespace(
            id=uuid4(),
            organization_id=uuid4(),
            email="invitee@example.com",
            role="consultant",
            status="pending",
            token_hash=hash_invitation_token(self.token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted_by_user_id=None,
            accepted_at=None,
        )
        self.payload = InvitationAccept(token=self.token, password="a-secure-password-123")
        self.identity = SupabaseIdentity(uuid4(), "invitee@example.com", True)

    def test_mirrors_before_creating_the_invited_profile(self) -> None:
        self.db.scalar.side_effect = [self.invitation, None, None]
        order = Mock()
        order.attach_mock(self.db.add, "add")
        with (
            patch.object(auth_endpoint, "create_invited_identity", return_value=self.identity),
            patch.object(auth_endpoint, "mirror_verified_identity") as mirror,
        ):
            order.attach_mock(mirror, "mirror")
            auth_endpoint.accept_invitation_and_create_profile(
                self.payload, self.db, settings(True)
            )

        names = [entry[0] for entry in order.mock_calls]
        self.assertEqual(names[0], "mirror")
        self.assertIn("add", names)

    def test_refused_mirror_returns_503_and_removes_the_new_auth_identity(self) -> None:
        self.db.scalar.side_effect = [self.invitation, None]
        with (
            patch.object(auth_endpoint, "create_invited_identity", return_value=self.identity),
            patch.object(
                auth_endpoint,
                "mirror_verified_identity",
                side_effect=LocalIdentityMirrorRefused("supabase"),
            ),
            patch.object(auth_endpoint, "delete_auth_identity", return_value=True) as delete,
        ):
            with self.assertRaises(HTTPException) as response:
                auth_endpoint.accept_invitation_and_create_profile(
                    self.payload, self.db, settings(True)
                )

        self.assertEqual(response.exception.status_code, 503)
        self.db.rollback.assert_called()
        self.assertEqual(delete.call_args, call(self.identity.id, unittest.mock.ANY))


if __name__ == "__main__":
    unittest.main()
