"""اختبارات طبقة الإشعارات: تمييز أخطاء تلغرام وإخفاء الأسرار."""

import logging

from notifications.base import NotificationChannel, NotificationManager, redact_secrets
from telegram_notifier import TelegramNotifier

SECRET = "123456789:AAFakeTokenValueThatLooksReal0123456789"


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def test_notifier_logs_unauthorized_status(monkeypatch, caplog):
    """استجابة 401 تُسجَّل كخطأ مصادقة برسالة مفهومة بلا كشف التوكن."""
    captured: dict = {}

    def fake_post(*args, **kwargs):
        captured["url"] = args[0] if args else kwargs.get("url")
        return FakeResponse(401, '{"ok":false,"error_code":401,"description":"Unauthorized"}')

    monkeypatch.setattr("telegram_notifier.requests.post", fake_post)

    with caplog.at_level(logging.ERROR):
        result = TelegramNotifier(SECRET, "42").send_message("مرحبا")

    assert result is False
    assert "401" in caplog.text
    assert "Unauthorized" in caplog.text or "غير صالح" in caplog.text
    assert SECRET in captured["url"]
    assert SECRET not in caplog.text


def test_notifier_logs_other_status_with_body(monkeypatch, caplog):
    """الأخطاء الأخرى تُسجَّل برمز الحالة ونص الاستجابة."""
    monkeypatch.setattr(
        "telegram_notifier.requests.post",
        lambda *a, **k: FakeResponse(400, "Bad Request: chat not found"),
    )

    with caplog.at_level(logging.ERROR):
        result = TelegramNotifier(SECRET, "42").send_message("مرحبا")

    assert result is False
    assert "400" in caplog.text
    assert "chat not found" in caplog.text


def test_broadcast_error_entry_has_no_secret_payload(monkeypatch, caplog):
    """نتيجة broadcast لا تحمّل القيمة السرّية، ونوع الخطأ مُميَّز."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET)

    class Broken(NotificationChannel):
        def send_text(self, message):
            raise ValueError(f"فشل الاتصال والتوكن هو {SECRET}")

        def send_file(self, filepath, caption=""):
            return False

    manager = NotificationManager()
    manager.register(Broken())

    with caplog.at_level(logging.ERROR):
        results = manager.broadcast("مرحبا")

    assert results[0]["channel"] == "Broken"
    assert results[0]["error"].startswith("ValueError")
    assert SECRET not in results[0]["error"]
    assert SECRET not in caplog.text
    assert "<redacted>" in results[0]["error"]


def test_redact_secrets_masks_token_pattern():
    """نمط توكن البوت يُخفى حتى لو لم يكن في البيئة."""
    assert SECRET not in redact_secrets(f"token={SECRET}")
    assert "<redacted>" in redact_secrets(f"token={SECRET}")
