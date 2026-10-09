import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.services.email import EmailDeliveryError, send_invitation_email


class InvitationEmailTests(unittest.TestCase):
    def test_sends_single_use_fragment_link_over_starttls(self) -> None:
        smtp = MagicMock()
        smtp_context = smtp.__enter__.return_value
        settings = Settings(
            app_base_url="https://grc.example.com/",
            smtp_host="smtp.example.com",
            smtp_username="mailer",
            smtp_password="smtp-password",
            smtp_sender_email="noreply@example.com",
            smtp_starttls=True,
        )

        with patch("app.services.email.smtplib.SMTP", return_value=smtp):
            send_invitation_email(
                settings,
                recipient="person@example.com",
                organization_name="Northstar Health",
                role="representative",
                token="high-entropy-token",
                expires_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
            )

        smtp_context.starttls.assert_called_once_with()
        smtp_context.login.assert_called_once_with("mailer", "smtp-password")
        message = smtp_context.send_message.call_args.args[0]
        body = message.get_content()
        self.assertIn("representative", body)
        self.assertIn("https://grc.example.com/invite/accept#token=high-entropy-token", body)
        self.assertNotIn("?token=", body)

    def test_requires_smtp_configuration(self) -> None:
        with self.assertRaises(EmailDeliveryError):
            send_invitation_email(
                Settings(),
                recipient="person@example.com",
                organization_name="Northstar Health",
                role="consultant",
                token="high-entropy-token",
                expires_at=datetime.now(timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
