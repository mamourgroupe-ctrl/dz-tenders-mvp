"""
notifications/base.py
طبقة تجريد موحّدة للإشعارات.
تسمح بإضافة قنوات جديدة (WhatsApp, Email) دون تعديل باقي الكود.
"""

import logging
import os
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

BOT_TOKEN_PATTERN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}")
SECRET_KEY_HINTS = ("TOKEN", "SECRET", "KEY", "PASSWORD", "PASSPHRASE")


def redact_secrets(text: str) -> str:
    """إخفاء التوكنات وقيم المتغيّرات السرّية من نص قد يُسجَّل أو يُعاد.

    Args:
        text: الرسالة الأصلية.

    Returns:
        النص بعد استبدال أي قيمة سرّية بعلامة ``<redacted>``.
    """
    redacted = BOT_TOKEN_PATTERN.sub("<redacted>", str(text))
    for key, value in os.environ.items():
        if any(hint in key.upper() for hint in SECRET_KEY_HINTS) and len(value) >= 8:
            redacted = redacted.replace(value, "<redacted>")
    return redacted


class NotificationChannel(ABC):
    """واجهة موحّدة لكل قناة إشعارات."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def send_text(self, message: str) -> bool: ...

    @abstractmethod
    def send_file(self, filepath: str, caption: str = "") -> bool: ...


class NotificationManager:
    """مدير يوزّع الرسائل على جميع القنوات المسجّلة."""

    def __init__(self):
        self.channels: list[NotificationChannel] = []

    def register(self, channel: NotificationChannel):
        self.channels.append(channel)
        logger.info(f"📡 تم تسجيل قناة: {channel.name}")

    def broadcast(self, message: str, filepath: str = None) -> list[dict]:
        """إرسال رسالة (وملف اختياري) عبر جميع القنوات."""
        results = []
        for ch in self.channels:
            try:
                text_ok = ch.send_text(message)
                file_ok = None
                if filepath:
                    file_ok = ch.send_file(filepath, caption=message[:150])
                results.append(
                    {
                        "channel": ch.name,
                        "text_ok": text_ok,
                        "file_ok": file_ok,
                    }
                )
            except Exception as e:
                error_type = type(e).__name__
                logger.error(
                    f"❌ فشل الإرسال عبر {ch.name}: {error_type}: {redact_secrets(str(e))}"
                )
                results.append(
                    {
                        "channel": ch.name,
                        "error": f"{error_type}: {redact_secrets(str(e))}",
                    }
                )
        return results
