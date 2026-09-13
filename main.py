"""
main.py
نقطة الدمج الكاملة لمشروع DZ-TENDERS-MVP.
"""

import os
import logging
from dotenv import load_dotenv

from storage.db import TenderStore
from notifications.base import NotificationManager
from notifications.telegram_channel import TelegramChannel
from notifications.excel_report import build_excel_report

# ⬇️ استيرادات مشروعك الفعلي
from crawlers import ADECrawler, ONACrawler, AlgeriaTendersCrawler
from tender_filter import TenderFilter

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dz_tenders.main")


def scrape_all_sources() -> list[dict]:
    """جمع المناقصات من كل المصادر."""
    crawlers = [ADECrawler(), ONACrawler(), AlgeriaTendersCrawler()]
    all_tenders = []
    for crawler in crawlers:
        try:
            results = crawler.run()
            logger.info(f"  • {crawler.__class__.__name__}: {len(results)} مناقصة")
            all_tenders.extend(results)
        except Exception as e:
            logger.error(f"  [!] خطأ في {crawler.__class__.__name__}: {e}")

    # إزالة التكرار
    unique = list({t.get("title", ""): t for t in all_tenders if t.get("title")}.values())
    return unique


def apply_filter(tenders: list[dict]) -> list[dict]:
    """تطبيق فلترة العائلات التسويقية."""
    filter_obj = TenderFilter()
    return filter_obj.filter_tenders(tenders)


def build_notifier() -> NotificationManager:
    notifier = NotificationManager()
    notifier.register(TelegramChannel(
        os.environ["TELEGRAM_BOT_TOKEN"],
        os.environ["TELEGRAM_CHAT_ID"],
    ))
    return notifier


def build_summary_message(new_tenders: list[dict]) -> str:
    by_family: dict[str, int] = {}
    for t in new_tenders:
        for fam in t.get("matched_families", []):
            name = fam.get("name_ar", "غير مصنّف")
            by_family[name] = by_family.get(name, 0) + 1

    lines = [f"🔔 <b>تقرير DZ-TENDERS</b>\n📋 {len(new_tenders)} مناقصة جديدة:\n"]
    for family, count in sorted(by_family.items(), key=lambda x: -x[1]):
        lines.append(f"• {family}: {count}")

    # إضافة عناوين أول 5 مناقصات
    lines.append("\n━━━━━━━━━━━━━━━━━━")
    for i, t in enumerate(new_tenders[:5], 1):
        lines.append(f"{i}. {t.get('title', 'بدون عنوان')[:80]}")
    return "\n".join(lines)


def run():
    logger.info("=" * 60)
    logger.info("🚀 بدء تشغيل DZ-TENDERS-MVP")
    logger.info("=" * 60)

    store = TenderStore(db_path=os.environ.get("DB_PATH", "tenders.db"))
    notifier = build_notifier()

    logger.info("📥 بدء الزحف...")
    all_tenders = scrape_all_sources()
    logger.info(f"تم جلب {len(all_tenders)} مناقصة فريدة")

    logger.info("🔍 تطبيق فلترة العائلات التسويقية...")
    filtered = apply_filter(all_tenders)
    logger.info(f"تبقّى {len(filtered)} مناقصة بعد الفلترة")

    logger.info("🧠 التحقق من المناقصات الجديدة...")
    new_or_changed = [t for t in filtered if store.is_new_or_changed(t)]
    logger.info(f"منها {len(new_or_changed)} مناقصة جديدة/محدّثة")

    if not new_or_changed:
        logger.info("✅ لا يوجد جديد — لن يُرسل أي إشعار.")
        store.close()
        return

    excel_path = build_excel_report(new_or_changed)
    summary = build_summary_message(new_or_changed)

    logger.info("📤 جاري الإرسال إلى تلغرام...")
    results = notifier.broadcast(summary, filepath=excel_path)
    logger.info(f"نتائج الإرسال: {results}")

    for tender in new_or_changed:
        store.mark_sent(tender)

    logger.info(f"📊 إجمالي المناقصات المسجلة: {store.count()}")
    store.close()
    logger.info("=" * 60)


if __name__ == "__main__":
    run()