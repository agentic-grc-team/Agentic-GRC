import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.main import app
from app.security.auth import AuthenticatedIdentity, get_authenticated_identity
from app.db.session import get_engine


class OrganizationStoryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()

    def setUp(self) -> None:
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.identity = AuthenticatedIdentity(
            issuer="https://test-idp.example/tenant",
            subject=f"test-{uuid4()}",
            email=f"admin-{uuid4()}@example.com",
        )

        def override_db():
            with Session(bind=self.connection, join_transaction_mode="create_savepoint") as session:
                yield session

        def override_identity():
            return self.identity

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_authenticated_identity] = override_identity
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.transaction.rollback()
        self.connection.close()

    def test_create_organization_is_scoped_and_creator_is_admin(self) -> None:
        response = self.client.post(
            "/api/v1/organizations",
            json={"name": f"Client {uuid4()}", "sector": "Technology", "size": "Small"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        organization = response.json()
        self.assertEqual(organization["role"], "administrator")

        listed = self.client.get("/api/v1/organizations")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([item["id"] for item in listed.json()], [organization["id"]])

    def test_duplicate_requires_confirmation_of_a_matching_organization(self) -> None:
        name = f"Duplicate {uuid4()}"
        payload = {"name": name, "sector": "Technology", "size": "Small"}
        original = self.client.post("/api/v1/organizations", json=payload)
        self.assertEqual(original.status_code, 201, original.text)

        duplicate = self.client.post("/api/v1/organizations", json=payload)
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        match_id = duplicate.json()["detail"]["matches"][0]["id"]
        payload["confirm_duplicate_of"] = match_id
        confirmed = self.client.post("/api/v1/organizations", json=payload)
        self.assertEqual(confirmed.status_code, 201, confirmed.text)
        memberships = self.client.get("/api/v1/organizations")
        self.assertEqual(memberships.status_code, 200, memberships.text)
        self.assertEqual(len(memberships.json()), 2)

    def test_invitation_is_persisted_and_matching_verified_user_can_accept(self) -> None:
        created = self.client.post(
            "/api/v1/organizations",
            json={"name": f"Inviter {uuid4()}", "sector": "Services", "size": "Medium"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        organization_id = created.json()["id"]
        invitee_email = f"invitee-{uuid4()}@example.com"

        invitation = self.client.post(
            f"/api/v1/organizations/{organization_id}/invitations",
            json={"email": invitee_email},
        )
        self.assertEqual(invitation.status_code, 201, invitation.text)
        self.assertEqual(invitation.json()["delivery_status"], "not_sent")
        invitation_id = invitation.json()["id"]

        wrong_identity = AuthenticatedIdentity(
            issuer="https://test-idp.example/tenant",
            subject=f"wrong-user-{uuid4()}",
            email=f"wrong-{uuid4()}@example.com",
        )
        self.identity = wrong_identity
        forbidden_acceptance = self.client.post(
            f"/api/v1/organizations/invitations/{invitation_id}/accept"
        )
        self.assertEqual(forbidden_acceptance.status_code, 404)

        self.identity = AuthenticatedIdentity(
            issuer="https://test-idp.example/tenant",
            subject=f"invitee-{uuid4()}",
            email=invitee_email,
        )
        inbox = self.client.get("/api/v1/organizations/me/invitations")
        self.assertEqual(inbox.status_code, 200, inbox.text)
        self.assertEqual(inbox.json()[0]["id"], invitation_id)

        accepted = self.client.post(f"/api/v1/organizations/invitations/{invitation_id}/accept")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        memberships = self.client.get("/api/v1/organizations")
        self.assertEqual(memberships.status_code, 200, memberships.text)
        self.assertEqual(memberships.json()[0]["id"], organization_id)
        self.assertEqual(memberships.json()[0]["role"], "consultant")

        forbidden = self.client.post(
            f"/api/v1/organizations/{organization_id}/invitations",
            json={"email": f"another-{uuid4()}@example.com"},
        )
        self.assertEqual(forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()
