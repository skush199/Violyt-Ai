from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import logging
import smtplib
import ssl
from urllib.parse import quote

from app.core.config import get_settings


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmailDeliveryResult:
    attempted: bool
    delivered: bool
    recipient_email: str
    reason: str | None = None


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(self.settings.smtp_host and self.settings.smtp_username and self.settings.smtp_password)

    def build_activation_link(self, token: str) -> str:
        base_url = self.settings.frontend_base_url.rstrip("/")
        return f"{base_url}/auth/activate?token={quote(token, safe='')}"

    def send_activation_email(
        self,
        recipient_email: str,
        recipient_name: str | None,
        token: str,
    ) -> EmailDeliveryResult:
        activation_link = self.build_activation_link(token)
        subject = "Activate your Violyt account"
        greeting_name = recipient_name or recipient_email
        text_body = (
            f"Hello {greeting_name},\n\n"
            "Your Violyt account is ready. Use the link below to activate your account and create a password:\n\n"
            f"{activation_link}\n\n"
            "This link will expire automatically. If you did not expect this invitation, you can ignore this email."
        )
        html_body = (
            f"<p>Hello {greeting_name},</p>"
            "<p>Your Violyt account is ready. Use the button below to activate your account and create a password.</p>"
            f'<p><a href="{activation_link}" style="display:inline-block;padding:12px 20px;'
            'background:#3C2F8F;color:#ffffff;text-decoration:none;border-radius:8px;">Activate Account</a></p>'
            f"<p>If the button does not work, open this link:</p><p>{activation_link}</p>"
            "<p>This link will expire automatically. If you did not expect this invitation, you can ignore this email.</p>"
        )
        return self._send_email(recipient_email, subject, text_body, html_body)

    def send_password_reset_email(
        self,
        recipient_email: str,
        recipient_name: str | None,
        token: str,
    ) -> EmailDeliveryResult:
        reset_link = self.build_activation_link(token)
        subject = "Reset your Violyt password"
        greeting_name = recipient_name or recipient_email
        text_body = (
            f"Hello {greeting_name},\n\n"
            "We received a request to reset your Violyt password. Use the link below to continue:\n\n"
            f"{reset_link}\n\n"
            "If you did not request a password reset, you can ignore this email."
        )
        html_body = (
            f"<p>Hello {greeting_name},</p>"
            "<p>We received a request to reset your Violyt password. Use the button below to continue.</p>"
            f'<p><a href="{reset_link}" style="display:inline-block;padding:12px 20px;'
            'background:#3C2F8F;color:#ffffff;text-decoration:none;border-radius:8px;">Reset Password</a></p>'
            f"<p>If the button does not work, open this link:</p><p>{reset_link}</p>"
            "<p>If you did not request a password reset, you can ignore this email.</p>"
        )
        return self._send_email(recipient_email, subject, text_body, html_body)

    def _send_email(
        self,
        recipient_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailDeliveryResult:
        if not self.is_configured():
            logger.warning("SMTP is not configured. Skipping email delivery for %s.", recipient_email)
            return EmailDeliveryResult(
                attempted=False,
                delivered=False,
                recipient_email=recipient_email,
                reason="SMTP is not configured.",
            )

        message = EmailMessage()
        from_email = self.settings.smtp_from_email or self.settings.smtp_username or "noreply@violyt.local"
        from_name = self.settings.smtp_from_name
        message["Subject"] = subject
        message["From"] = f"{from_name} <{from_email}>"
        message["To"] = recipient_email
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
                smtp.ehlo()
                if self.settings.smtp_use_tls:
                    smtp.starttls(context=context)
                    smtp.ehlo()
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning("Email delivery failed for %s: %s", recipient_email, exc)
            return EmailDeliveryResult(
                attempted=True,
                delivered=False,
                recipient_email=recipient_email,
                reason="SMTP authentication failed. Check the sender email password or app password.",
            )
        except smtplib.SMTPRecipientsRefused as exc:
            logger.warning("Email delivery failed for %s: %s", recipient_email, exc)
            return EmailDeliveryResult(
                attempted=True,
                delivered=False,
                recipient_email=recipient_email,
                reason="The recipient email address was rejected by the mail server.",
            )
        except (smtplib.SMTPConnectError, TimeoutError, OSError) as exc:
            logger.warning("Email delivery failed for %s: %s", recipient_email, exc)
            return EmailDeliveryResult(
                attempted=True,
                delivered=False,
                recipient_email=recipient_email,
                reason="Could not connect to the SMTP server.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email delivery failed for %s: %s", recipient_email, exc)
            return EmailDeliveryResult(
                attempted=True,
                delivered=False,
                recipient_email=recipient_email,
                reason=str(exc) or "Email delivery failed.",
            )

        return EmailDeliveryResult(
            attempted=True,
            delivered=True,
            recipient_email=recipient_email,
            reason=None,
        )
