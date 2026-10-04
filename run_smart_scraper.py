"""
run_smart_scraper.py
Priority-based scraper for sources from sources_master.json
Usage: python run_smart_scraper.py [priority] [limit]
"""

import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from crawlers.smart_crawler import SmartCrawler
from sources import SourcesLoader
from storage.db import TenderStore
from storage.delivery import STATUS_FAILED, STATUS_LOCKED, STATUS_SENT, deliver
from storage.lock import LOCK_TIMEOUT_EXIT_CODE
from storage.paths import resolve_db_path
from telegram_notifier import TelegramNotifier
from tender_filter import TenderFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")


def main():
    priority = sys.argv[1] if len(sys.argv) > 1 else "1"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    print("=" * 70)
    print(f"   SMART SCRAPER : Priority {priority} (limit {limit})")
    print("=" * 70)

    loader = SourcesLoader()
    sources = loader.crawlable(priority=priority)

    print(f"\nCrawlable sources: {len(sources)} (limit {limit})")

    with_tp = [s for s in sources if s.get("tp")]
    without_tp = [s for s in sources if not s.get("tp")]
    selected = (with_tp + without_tp)[:limit]

    print(f"Selected {len(selected)} sources\n")

    all_tenders = []
    for i, src in enumerate(selected, 1):
        url = src.get("tp") or src.get("site")
        if not url:
            continue
        name = src.get("ar", "Unknown")
        try:
            crawler = SmartCrawler(name, url, priority=priority)
            results = crawler.run()
            all_tenders.extend(results)
            if results:
                print(f"  [{i}/{len(selected)}] {name}: {len(results)}")
        except Exception as e:
            print(f"  [{i}/{len(selected)}] {name}: ERROR {e}")

    unique = list({t["title"]: t for t in all_tenders if t.get("title")}.values())
    print(f"\nTotal unique: {len(unique)}")

    print("\nFiltering...")
    filter_obj = TenderFilter()
    filtered = filter_obj.filter_tenders(unique)
    print(f"Filtered: {len(filtered)}")

    def send(pending: list[dict]) -> tuple[bool, str]:
        """إرسال ملخّص الصفقات عبر تلغرام.

        Returns:
            (نجاح، سبب_الخطأ).
        """
        target = TELEGRAM_CHANNEL_ID or TELEGRAM_CHAT_ID
        notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, target)

        msg = f"🔔 Smart Scraper - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += f"📊 New tenders: {len(pending)}\n\n"
        for idx, t in enumerate(pending[:15], 1):
            msg += f"[{idx}] {t['title'][:80]}\n"
            msg += f"    🏛️ {t.get('organisation', '-')}\n"
            msg += f"    🔗 {t.get('link', '#')}\n\n"

        if notifier.send_message(msg):
            return True, ""
        return False, "telegram send_message failed"

    # نفس مسار التسليم الموحّد المستعمل في main.py، تحت قفل واحد.
    # TenderStore() بلا وسائط يفتح DEFAULT_DB_PATH، وهو نفس ما يعيده
    # resolve_db_path() بلا وسائط.
    outcome = deliver(
        resolve_db_path(),
        TenderStore,
        filtered,
        send if TELEGRAM_BOT_TOKEN else None,
        label="run_smart_scraper.py",
    )

    print(f"New: {outcome.inserted}, Total in DB: {outcome.total}")

    if outcome.status == STATUS_LOCKED:
        print("Database is locked by another process — cycle skipped")
        raise SystemExit(LOCK_TIMEOUT_EXIT_CODE)
    if outcome.status == STATUS_SENT:
        print(f"Sent {len(outcome.pending)} to Telegram")
    elif outcome.status == STATUS_FAILED:
        print(f"FAILED to send {len(outcome.pending)} — recorded as failed attempts")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
