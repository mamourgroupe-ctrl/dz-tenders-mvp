"""
run_smart_scraper.py
Priority-based scraper for sources from sources_master.json
Usage: python run_smart_scraper.py [priority] [limit]
"""

import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

from sources import SourcesLoader
from crawlers.smart_crawler import SmartCrawler
from tender_filter import TenderFilter
from telegram_notifier import TelegramNotifier
from storage import TenderDatabase

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

    db = TenderDatabase()
    new_count = 0
    for t in filtered:
        if db.add_tender(t):
            new_count += 1

    new_tenders = db.get_new_tenders(filtered)
    stats = db.stats()
    print(f"New: {new_count}, Total in DB: {stats['total']}")

    if new_tenders and TELEGRAM_BOT_TOKEN:
        target = TELEGRAM_CHANNEL_ID or TELEGRAM_CHAT_ID
        notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, target)

        msg = f"🔔 Smart Scraper - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += f"📊 New tenders: {len(new_tenders)}\n\n"
        for idx, t in enumerate(new_tenders[:15], 1):
            msg += f"[{idx}] {t['title'][:80]}\n"
            msg += f"    🏛️ {t.get('organisation', '-')}\n"
            msg += f"    🔗 {t.get('link', '#')}\n\n"

        notifier.send_message(msg)

        for t in new_tenders:
            db.mark_notified(t)

        print(f"Sent {len(new_tenders)} to Telegram")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
