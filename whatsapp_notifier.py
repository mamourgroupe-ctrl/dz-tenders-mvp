"""
whatsapp_notifier.py
وحدة إرسال التنبيهات عبر WhatsApp Business Cloud API.
"""

import os
import logging
from dotenv import load_dotenv
from python_whatsapp_bot import Whatsapp

load_dotenv()

logger = logging.getLogger(__name__)


class WhatsAppNotifier:
    """
    إرسال رسائل WhatsApp Business Cloud API الرسمية.
    """

    def __init__(self):
        self.number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.token = os.getenv("WHATSAPP_ACCESS_TOKEN")

        if not self.number_id or not self.token:
            raise ValueError(
                "❌ يجب ضبط WHATSAPP_PHONE_NUMBER_ID و WHATSAPP_ACCESS_TOKEN في ملف .env"
            )

        # تهيئة العميل وفقًا للتوثيق الرسمي
        self.bot = Whatsapp(
            number_id=self.number_id,
            token=self.token,
            mark_as_read=True
        )

    def send_text(self, to_number: str, text: str):
        """إرسال رسالة نصية (داخل نافذة 24 ساعة)"""
        try:
            result = self.bot.send_message(to_number, text)
            logger.info(f"✅ تم إرسال رسالة نصية إلى {to_number}")
            return result
        except Exception as e:
            logger.error(f"❌ فشل الإرسال إلى {to_number}: {e}")
            return None

    def send_template(
        self,
        to_number: str,
        template_name: str,
        language_code: str = "ar",
        components: list = None
    ):
        """إرسال قالب معتمد"""
        try:
            result = self.bot.send_template_message(
                to_number,
                template_name,
                components=components,
                language_code=language_code
            )
            logger.info(f"✅ تم إرسال قالب '{template_name}' إلى {to_number}")
            return result
        except Exception as e:
            logger.error(f"❌ فشل إرسال القالب إلى {to_number}: {e}")
            return None

    def broadcast_template(
        self,
        recipients: list,
        template_name: str,
        language_code: str = "ar",
        components: list = None
    ):
        """إرسال قالب إلى قائمة من الأرقام"""
        results = []
        for number in recipients:
            try:
                self.send_template(number, template_name, language_code, components)
                results.append({"number": number, "success": True})
            except Exception as e:
                logger.error(f"فشل الإرسال إلى {number}: {e}")
                results.append({"number": number, "success": False})
        return results


# ==================== اختبار سريع ====================
if __name__ == "__main__":
    notifier = WhatsAppNotifier()
    print("✅ WhatsAppNotifier initialized successfully")