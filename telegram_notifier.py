import requests
import logging

class TelegramNotifier:
    """
    وحدة إرسال التنبيهات والتقارير اليومية إلى تلغرام
    """
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, text):
        """إرسال رسالة نصية تنسيقية"""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            return res.status_code == 200
        except Exception as e:
            logging.error(f"خطأ أثناء إرسال نص تلغرام: {e}")
            return False

    def send_excel_report(self, file_path, caption=""):
        """إرسال ملف Excel المحدث كـ Document"""
        url = f"{self.base_url}/sendDocument"
        try:
            with open(file_path, 'rb') as f:
                files = {'document': f}
                data = {'chat_id': self.chat_id, 'caption': caption}
                res = requests.post(url, data=data, files=files, timeout=25)
            return res.status_code == 200
        except Exception as e:
            logging.error(f"خطأ أثناء إرسال ملف Excel عبر تلغرام: {e}")
            return False