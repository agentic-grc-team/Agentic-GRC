import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.endpoints import auth as auth_endpoint
from app.api.v1.endpoints import organizations as organization_endpoints
from app.core.config import Settings
from app.db.models import IndustrySector, OrganizationSize, User
from app.db.session import get_engine
from app.schemas.organizations import InvitationAccept, InvitationCreate, OrganizationCreate
from app.security.invitations import hash_invitation_token
from app.security.supabase import SupabaseIdentity


class OrganizationInvitationFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()
        try:
            with cls.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        except (OSError, SQLAlchemyError) as exc:
            raise unittest.SkipTest("PostgreSQL is unavailable for integration tests.") from exc

    def setUp(self) -> None:
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        admin_id = uuid4()
        admin_email = f"admin-{uuid4()}@example.com"
        self._insert_auth_user(admin_id, admin_email)
        self.admin = User(
            id=admin_id,
            email=admin_email,
            is_platform_admin=True,
        )
        self.session.add(self.admin)
        if self.session.get(IndustrySector, "other") is None:
            self.session.add(IndustrySector(code="other", label="Other / not specified"))
        if self.session.get(OrganizationSize, "unknown") is None:
            self.session.add(OrganizationSize(code="unknown", label="Not specified"))
        self.session.flush()
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _insert_auth_user(self, user_id, email: str) -> None:
        now = datetime.now(timezone.utc)
        self.connection.execute(
            text(
                "INSERT INTO auth.users "
                "(id, aud, role, email, encrypted_password, email_confirmed_at, "
                "raw_app_meta_data, raw_user_meta_data, created_at, updated_at) "
                "VALUES (:id, 'authenticated', 'authenticated', :email, '', :confirmed_at, "
                "'{}'::jsonb, '{}'::jsonb, :created_at, :updated_at)"
            ),
            {
                "id": user_id,
                "email": email,
                "confirmed_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )

    def _create_organization(self, name: str):
        return organization_endpoints.create_organization(
            OrganizationCreate(name=name, sector_code="other", size_code="unknown"),
            self.session,
            self.admin,
        )

    def test_duplicate_organization_name_requires_explicit_confirmation(self) -> None:
        name = f"Client {uuid4()}"
        original = self._create_organization(name)

        with self.assertRaises(HTTPException) as duplicate:
            self._create_organization(name)
        self.assertEqual(duplicate.exception.status_code, 409)
        duplicate_id = duplicate.exception.detail["matches"][0]["id"]

        confirmed = organization_endpoints.create_organization(
            OrganizationCreate(
                name=name,
                sector_code="other",
                size_code="unknown",
                confirm_duplicate_of=duplicate_id,
            ),
            self.session,
            self.admin,
        )
        self.assertEqual(confirmed.role, "administrator")

    def test_invitation_email_creates_verified_user_and_membership(self) -> None:
        organization = self._create_organization(f"Client {uuid4()}")
        invitee_email = f"representative-{uuid4()}@example.com"
        invitee_id = uuid4()
        raw_token = f"test-token-{uuid4()}-long-enough-for-activation"
        token_hash = hash_invitation_token(raw_token)
        with (
            patch.object(organization_endpoints, "create_invitation_token", return_value=(raw_token, token_hash)),
            patch.object(organization_endpoints, "send_invitation_email") as send_email,
            patch.object(
                auth_endpoint,
                "create_invited_identity",
                return_value=SupabaseIdentity(invitee_id, invitee_email, True),
            ),
        ):
            self._insert_auth_user(invitee_id, invitee_email)
            invitation = organization_endpoints.create_invitation(
                organization.id,
                InvitationCreate(email=invitee_email, role="representative"),
                self.session,
                self.admin,
                Settings(),
            )

        self.assertEqual(invitation.delivery_status, "sent")
        send_email.assert_called_once()
        accept = auth_endpoint.accept_invitation_and_create_profile(
            InvitationAccept(token=raw_token, password="a-secure-test-password-12"),
            self.session,
        )
        self.assertEqual(accept.role, "representative")

        user = self.session.scalar(select(User).where(User.email == invitation.email))
        self.assertIsNotNone(user)
        self.assertEqual(user.id, invitee_id)

        with self.assertRaises(HTTPException) as replay:
            auth_endpoint.accept_invitation_and_create_profile(
                InvitationAccept(token=raw_token, password="another-secure-password-12"),
                self.session,
            )
        self.assertIn(replay.exception.status_code, (404, 410))


if __name__ == "__main__":
    unittest.main()
