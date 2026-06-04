"""
Small SMTP email helper for account verification and report delivery.
"""
import logging
import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional

from app.utils.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)

    @staticmethod
    def _send_message(message: EmailMessage) -> None:
        if not EmailService.is_configured():
            raise RuntimeError("SMTP is not configured")

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)

    @staticmethod
    def send_signup_otp(email: str, otp: str) -> None:
        if not EmailService.is_configured():
            logger.warning("SMTP is not configured; signup OTP for %s is %s", email, otp)
            return

        message = EmailMessage()
        message["From"] = settings.EMAIL_FROM or settings.SMTP_USER
        message["To"] = email
        message["Subject"] = "TenderEval signup verification code"
        message.set_content(
            f"Your TenderEval verification code is {otp}.\n\n"
            f"This code expires in {settings.EMAIL_OTP_EXPIRE_MINUTES} minutes."
        )

        EmailService._send_message(message)

    @staticmethod
    def send_evaluation_report(
        recipients: Iterable[str],
        subject: str,
        body: str,
        pdf_bytes: bytes,
        filename: str,
        cc: Optional[Iterable[str]] = None,
    ) -> None:
        message = EmailMessage()
        message["From"] = settings.EMAIL_FROM or settings.SMTP_USER
        message["To"] = ", ".join(recipients)
        if cc:
            message["Cc"] = ", ".join(cc)
        message["Subject"] = subject
        message.set_content(body)
        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=filename,
        )

        EmailService._send_message(message)
