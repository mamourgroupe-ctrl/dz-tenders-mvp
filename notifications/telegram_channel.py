"""
notifications/telegram_channel.py
غلاف حول TelegramNotifier الحالي يطبّق واجهة NotificationChannel.
"""

from notifications.base import NotificationChannel
from telegram_notifier import TelegramNotifier


class TelegramChannel(NotificationChannel):
    def __init__(self, bot_token: str, chat_id: str):
        self.notifier = TelegramNotifier(bot_token, chat_id)

    def send_text(self, message: str) -> bool:
        return self.notifier.send_message(message)

    def send_file(self, filepath: str, caption: str = "") -> bool:
        return self.notifier.send_excel_report(filepath, caption=caption)