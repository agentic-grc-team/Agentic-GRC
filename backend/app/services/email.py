from datetime import datetime
from email.message import EmailMessage
import smtplib
from urllib.parse import urlencode

from app.core.config import Settings


class EmailDeliveryError(RuntimeError):
    """Raised when the configured SMTP server cannot deliver an email."""


def send_invitation_email(
    settings: Settings,
    recipient: str,
    organization_name: str,
    role: str,
    token: str,
    expires_at: datetime,
) -> None:
    required_values = (settings.smtp_host, settings.smtp_sender_email)
    if not all(required_values):
        raise EmailDeliveryError("Invitation email is not configured. Set SMTP_HOST and SMTP_SENDER_EMAIL.")

    query = urlencode({"token": token})
    activation_url = f"{settings.app_base_url.rstrip('/')}/invite/accept#{query}"
    expiry_label = expires_at.strftime("%Y-%m-%d %H:%M UTC")
    message = EmailMessage()
    message["Subject"] = f"Invitation to join {organization_name} on Agentic GRC"
    message["From"] = settings.smtp_sender_email
    message["To"] = recipient
    message.set_content(
        f"You have been invited to join {organization_name} as a {role}.\n\n"
        f"Create your account and accept the invitation using this link:\n{activation_url}\n\n"
        f"This link expires on {expiry_label} and can only be used once."
    )

    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(
                    settings.smtp_username,
                    settings.smtp_password.get_secret_value()
                    if settings.smtp_password is not None
                    else "",
                )
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("The invitation email could not be delivered.") from exc
