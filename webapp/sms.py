"""Pluggable SMS delivery for phone OTP codes.

The repository ships **no** provider account and no real credentials. Two
backends exist:

* ``console`` (default) — logs the code and keeps it in memory so developers and
  tests can complete the flow without sending anything.
* ``http`` — a generic JSON webhook for an operator API, configured through
  ``APP_SMS_API_URL``, ``APP_SMS_API_KEY`` and ``APP_SMS_SENDER``. The exact
  payload must be adapted to the chosen operator; it is a clearly marked
  placeholder, not an integration with a specific vendor.

Never log the full phone number or the code at INFO level in production.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import requests

from webapp.config import Settings
from webapp.timeutils import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmsMessage:
    """One outbound SMS."""

    phone: str
    text: str
    kind: str = "otp"
    created_at: datetime = field(default_factory=utcnow)


class SmsProvider(Protocol):
    """Minimal interface shared by the console and HTTP backends."""

    def send(self, message: SmsMessage) -> None:
        """Deliver one SMS or raise ``RuntimeError``."""


class ConsoleSmsProvider:
    """Log the code instead of sending it (development and tests)."""

    def __init__(self) -> None:
        self.outbox: list[SmsMessage] = []

    def send(self, message: SmsMessage) -> None:
        self.outbox.append(message)
        logger.info(
            "[console-sms] to=%s kind=%s text=%s",
            message.phone,
            message.kind,
            message.text,
        )


class HttpSmsProvider:
    """POST a JSON payload to an operator webhook.

    The payload shape is a placeholder: adapt ``_payload`` and the endpoint to
    the operator once credentials and API documentation are available.
    """

    def __init__(
        self, *, url: str, api_key: str, sender: str, timeout: float = 15.0
    ) -> None:
        if not url or not api_key:
            raise ValueError("SMS backend requires APP_SMS_API_URL and APP_SMS_API_KEY")
        self.url = url
        self.api_key = api_key
        self.sender = sender
        self.timeout = timeout

    def _payload(self, message: SmsMessage) -> dict[str, str]:
        return {
            "sender": self.sender,
            "to": message.phone,
            "message": message.text,
        }

    def send(self, message: SmsMessage) -> None:
        response = requests.post(
            self.url,
            json=self._payload(message),
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"SMS gateway rejected the message ({response.status_code})"
            )


def build_sms_provider(settings: Settings) -> SmsProvider:
    """Build the configured SMS backend."""
    backend = (settings.sms_backend or "console").strip().lower()
    if backend == "http":
        return HttpSmsProvider(
            url=settings.sms_api_url,
            api_key=settings.sms_api_key,
            sender=settings.sms_sender,
        )
    if backend != "console":
        raise ValueError(f"Unsupported SMS backend: {backend!r}")
    return ConsoleSmsProvider()


def otp_message(code: str, *, ttl_minutes: int) -> str:
    """Build the OTP SMS body (no link, no marketing)."""
    return (
        f"رمز التحقق الخاص بمنصة مناقصات الجزائر: {code}\n"
        f"صالح لمدة {ttl_minutes} دقيقة. لا تشاركوه مع أي شخص."
    )


__all__ = [
    "ConsoleSmsProvider",
    "HttpSmsProvider",
    "SmsMessage",
    "SmsProvider",
    "build_sms_provider",
    "otp_message",
]
