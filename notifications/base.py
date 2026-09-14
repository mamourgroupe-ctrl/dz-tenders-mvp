"""
notifications/base.py
طبقة تجريد موحّدة للإشعارات.
تسمح بإضافة قنوات جديدة (WhatsApp, Email) دون تعديل باقي الكود.
"""

from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """واجهة موحّدة لكل قناة إشعارات."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def send_text(self, message: str) -> bool:
        ...

    @abstractmethod
    def send_file(self, filepath: str, caption: str = "") -> bool:
        ...


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
                results.append({
                    "channel": ch.name,
                    "text_ok": text_ok,
                    "file_ok": file_ok,
                })
            except Exception as e:
                logger.error(f"❌ فشل الإرسال عبر {ch.name}: {e}")
                results.append({"channel": ch.name, "error": str(e)})
        return results