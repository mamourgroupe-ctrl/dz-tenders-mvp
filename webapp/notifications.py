"""Pluggable email delivery for verification, reset and renewal messages.

No SMTP credentials exist in the repository. The default backend is
``console``: messages are logged and kept in memory (useful in development,
tests and demos). Production requires an explicit configuration:

* ``APP_EMAIL_BACKEND=smtp``
* ``APP_SMTP_HOST``, ``APP_SMTP_PORT`` (587), ``APP_SMTP_FROM``
* ``APP_SMTP_USER`` / ``APP_SMTP_PASSWORD`` when the relay authenticates

The SMTP backend is a thin ``smtplib`` wrapper, deliberately vendor-neutral:
no provider-specific API is assumed.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage as MimeMessage
from typing import Protocol

from webapp.config import Settings
from webapp.timeutils import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    """A plain-text transactional email."""

    to: str
    subject: str
    body: str
    kind: str = "transactional"
    created_at: datetime = field(default_factory=utcnow)


class EmailProvider(Protocol):
    """Minimal interface shared by the console and SMTP backends."""

    def send(self, message: EmailMessage) -> None:
        """Deliver one message or raise ``RuntimeError``."""


class ConsoleEmailProvider:
    """Log messages instead of sending them (development and tests)."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
        logger.info(
            "[console-email] to=%s subject=%s kind=%s",
            message.to,
            message.subject,
            message.kind,
        )
        logger.debug("[console-email] body:\n%s", message.body)


class SmtpEmailProvider:
    """Deliver through an SMTP relay using STARTTLS."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str = "",
        password: str = "",
        starttls: bool = True,
    ) -> None:
        if not host or not sender:
            raise ValueError("SMTP backend requires APP_SMTP_HOST and APP_SMTP_FROM")
        self.host = host
        self.port = port
        self.sender = sender
        self.username = username
        self.password = password
        self.starttls = starttls

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self.sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)
        with smtplib.SMTP(self.host, self.port, timeout=20) as client:
            if self.starttls:
                client.starttls()
            if self.username:
                client.login(self.username, self.password)
            client.send_message(mime)


def build_email_provider(settings: Settings) -> EmailProvider:
    """Build the configured email backend.

    Raises:
        ValueError: ``APP_EMAIL_BACKEND=smtp`` without the required settings.
    """
    backend = (settings.email_backend or "console").strip().lower()
    if backend == "smtp":
        return SmtpEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.smtp_from,
            username=settings.smtp_user,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
        )
    if backend != "console":
        raise ValueError(f"Unsupported email backend: {backend!r}")
    return ConsoleEmailProvider()


def _base_url(settings: Settings) -> str:
    """Public origin used in links; falls back to localhost in development."""
    return settings.public_base_url or "http://localhost:8000"


def verification_email(
    settings: Settings, *, to: str, token: str, company_name: str = ""
) -> EmailMessage:
    """Build the email-verification message."""
    link = f"{_base_url(settings)}/verifier-email?token={token}"
    body = (
        f"مرحباً {company_name or ''}\n\n"
        "لتأكيد بريدكم الإلكتروني على منصة مناقصات الجزائر، افتحوا الرابط التالي:\n"
        f"{link}\n\n"
        "إن لم تكونوا قد أنشأتم حساباً، تجاهلوا هذه الرسالة.\n"
    )
    return EmailMessage(
        to=to, subject="تأكيد البريد الإلكتروني", body=body, kind="verify_email"
    )


def renewal_email(
    settings: Settings,
    *,
    to: str,
    company_name: str,
    plan_name: str,
    days_left: int,
    ends_at: str,
) -> EmailMessage:
    """Build the renewal reminder."""
    return EmailMessage(
        to=to,
        subject="تنبيه: اقتراب انتهاء الاشتراك",
        body=(
            f"مرحباً {company_name}\n\n"
            f"ينتهي اشتراككم في صيغة «{plan_name}» بتاريخ {ends_at} "
            f"(خلال {days_left} يوماً).\n"
            "لتجديد الاشتراك دون انقطاع، افتحوا لوحة التحكم:\n"
            f"{_base_url(settings)}/tableau-de-bord\n"
        ),
        kind="renewal_reminder",
    )


__all__ = [
    "ConsoleEmailProvider",
    "EmailMessage",
    "EmailProvider",
    "SmtpEmailProvider",
    "build_email_provider",
    "renewal_email",
    "verification_email",
]
