import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.security.auth import get_authenticated_identity


class JwtAuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key()
        cls.private_pem = cls.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def setUp(self) -> None:
        self.settings = Settings(
            auth_issuer="https://issuer.example/tenant",
            auth_audience="agentic-grc-api",
            auth_jwks_url="https://issuer.example/tenant/keys",
        )

    def token(self, **overrides: object) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "iss": self.settings.auth_issuer,
            "aud": self.settings.auth_audience,
            "sub": "subject-123",
            "email": "person@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        claims.update(overrides)
        return jwt.encode(claims, self.private_pem, algorithm="RS256", headers={"kid": "test-key"})

    def authenticate(self, token: str, settings: Settings | None = None):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        fake_client = SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=self.public_key)
        )
        with patch("app.security.auth._jwks_client", return_value=fake_client):
            return get_authenticated_identity(credentials, settings or self.settings)

    def test_accepts_valid_signature_and_verified_email(self) -> None:
        identity = self.authenticate(self.token())
        self.assertEqual(identity.issuer, self.settings.auth_issuer)
        self.assertEqual(identity.subject, "subject-123")
        self.assertEqual(identity.email, "person@example.com")

    def test_rejects_unverified_email(self) -> None:
        with self.assertRaises(HTTPException) as error:
            self.authenticate(self.token(email_verified=False))
        self.assertEqual(error.exception.status_code, 401)

    def test_rejects_wrong_audience(self) -> None:
        with self.assertRaises(HTTPException) as error:
            self.authenticate(self.token(aud="another-api"))
        self.assertEqual(error.exception.status_code, 401)

    def test_fails_closed_when_oidc_is_not_configured(self) -> None:
        unconfigured = Settings(auth_issuer=None, auth_audience=None, auth_jwks_url=None)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
        with self.assertRaises(HTTPException) as error:
            get_authenticated_identity(credentials, unconfigured)
        self.assertEqual(error.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
