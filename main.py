"""
main.py
نقطة الدمج الكاملة لمشروع DZ-TENDERS-MVP.
"""

import logging
import os

from dotenv import load_dotenv

from config import AppConfig

# ⬇️ استيرادات مشروعك الفعلي
from crawlers import ADECrawler, AlgeriaTendersCrawler, ONACrawler
from logging_config import setup_logging
from notifications.base import NotificationManager
from notifications.excel_report import build_excel_report
from notifications.telegram_channel import TelegramChannel
from storage.db import TenderStore
from tender_filter import TenderFilter

load_dotenv()

TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def env_flag(name: str, default: bool = False) -> bool:
    """Read boolean environment flags."""
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    return raw_value.strip().lower() in TRUE_VALUES


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


def drop_reference_data(tenders: list[dict], include_samples: bool = False) -> list[dict]:
    """حذف البيانات المرجعية (المُلفّقة) إلا عند طلب تضمينها صراحةً.

    Args:
        tenders: المناقصات المجمّعة من كل الزواحف.
        include_samples: عند True تُعاد البيانات المرجعية كما هي.

    Returns:
        قائمة المناقصات الحية فقط عند include_samples=False.
    """
    if include_samples:
        logger.warning("INCLUDE_SAMPLES=true: سيتم إبلاغ المستخدم ببيانات مرجعية غير حقيقية")
        return list(tenders)

    kept = [t for t in tenders if not t.get("is_sample")]
    dropped = len(tenders) - len(kept)
    if dropped:
        logger.warning(
            "تم استبعاد %d مناقصة مرجعية (بيانات تجريبية غير حقيقية) — "
            "اضبط INCLUDE_SAMPLES=true لتضمينها",
            dropped,
        )
    return kept


def apply_filter(tenders: list[dict]) -> list[dict]:
    """تطبيق فلترة العائلات التسويقية."""
    filter_obj = TenderFilter()
    return filter_obj.filter_tenders(tenders)


def build_notifier(config: AppConfig) -> NotificationManager | None:
    """بناء مُرسِل تلغرام من الإعدادات، أو None إذا كانت ناقصة.

    Args:
        config: إعدادات التطبيق المحمّلة من متغيرات البيئة.

    Returns:
        NotificationManager جاهز، أو None عند غياب التوكن أو معرّف المحادثة.
    """
    if not config.is_telegram_configured:
        logger.warning(
            "إعدادات Telegram غير مكتملة — تم تعطيل الإرسال "
            "(مطلوب TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID)"
        )
        return None

    notifier = NotificationManager()
    notifier.register(
        TelegramChannel(
            config.telegram_bot_token,
            config.telegram_chat_id,
        )
    )
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
    config = AppConfig.from_env()
    setup_logging(config.log_level)
    dry_run = config.dry_run
    logger.info("=" * 60)
    logger.info("🚀 بدء تشغيل DZ-TENDERS-MVP")
    logger.info("=" * 60)

    store = TenderStore(db_path=config.db_path)

    notifier = None
    if not dry_run:
        notifier = build_notifier(config)

    logger.info("📥 بدء الزحف...")
    all_tenders = scrape_all_sources()
    logger.info(f"تم جلب {len(all_tenders)} مناقصة فريدة")

    live_tenders = drop_reference_data(all_tenders, include_samples=config.include_samples)
    logger.info(f"تبقّى {len(live_tenders)} مناقصة بعد استبعاد البيانات المرجعية")

    logger.info("🔍 تطبيق فلترة العائلات التسويقية...")
    filtered = apply_filter(live_tenders)
    logger.info(f"تبقّى {len(filtered)} مناقصة بعد الفلترة")

    logger.info("🧠 التحقق من المناقصات الجديدة...")
    new_or_changed = [t for t in filtered if store.is_new_or_changed(t)]
    logger.info(f"منها {len(new_or_changed)} مناقصة جديدة/محدّثة")

    if not new_or_changed:
        logger.info("✅ لا يوجد جديد — لن يُرسل أي إشعار.")
        store.close()
        return

    inserted = store.save_many(new_or_changed)
    logger.info(f"💾 حُفظت {inserted} صفقة جديدة في القاعدة")

    excel_path = build_excel_report(new_or_changed)
    summary = build_summary_message(new_or_changed)

    if dry_run:
        logger.warning("DRY_RUN=true: skipping Telegram send")
        logger.info("DRY_RUN report path: %s", excel_path)
    elif notifier is None:
        logger.warning("تخطّي الإرسال: الإعدادات غير مكتملة")
    else:
        logger.info("📤 جاري الإرسال إلى تلغرام...")
        results = notifier.broadcast(summary, filepath=excel_path)
        logger.info(f"نتائج الإرسال: {results}")

        if any(entry.get("text_ok") is True for entry in results):
            for tender in new_or_changed:
                store.mark_sent(tender)
        else:
            error_msg = "; ".join(
                str(entry.get("error", "unknown")) for entry in results if entry.get("error")
            )
            for tender in new_or_changed:
                store.register_failed_attempt(tender, error_msg)
            logger.warning("فشل الإرسال عبر كل القنوات — سُجّلت محاولة فاشلة لكل صفقة: %s", error_msg)

    logger.info(f"📊 إجمالي المناقصات المسجلة: {store.count()}")
    store.close()
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
