"""
main.py
نقطة الدمج الكاملة لمشروع DZ-TENDERS-MVP.
"""

import logging
import os

from dotenv import load_dotenv

from config import AppConfig

# ⬇️ استيرادات مشروعك الفعلي
from crawlers import (
    ADECrawler,
    AlgeriaTendersCrawler,
    GoogleNewsCrawler,
    ONACrawler,
    SafqaticCrawler,
)
from logging_config import setup_logging
from notifications.base import NotificationManager
from notifications.excel_report import build_excel_report
from notifications.telegram_channel import TelegramChannel
from storage.db import TenderStore
from storage.delivery import STATUS_LOCKED, deliver
from storage.lock import LOCK_TIMEOUT_EXIT_CODE
from storage.paths import resolve_db_path
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


#: (crawler_instance, enabled) tuples.
#: Disabled sources are skipped with a log entry. Rationale:
#: - SafqaticCrawler: active live source (poste & telecom, 2026)
#: - ADECrawler: returns 500 Server Error (server-side, temporary)
#: - ONACrawler: only reference (sample) data available
#: - AlgeriaTendersCrawler: only reference (sample) data available
#:
#: To re-enable a source: flip False to True (no other change needed).
CRAWLER_SOURCES = [
    (SafqaticCrawler, True),
    (GoogleNewsCrawler, True),
    (ADECrawler, False),
    (ONACrawler, False),
    (AlgeriaTendersCrawler, False),
]


def scrape_all_sources() -> list[dict]:
    """جمع المناقصات من المصادر المفعّلة.

    كل مصدر قد يحتاج إغلاقاً صريحاً (Playwright)؛ تُستدعى close() في finally.
    المصادر المعطّلة تُتخطّى مع تسجيل السبب.
    """
    all_tenders = []
    for crawler_cls, enabled in CRAWLER_SOURCES:
        name = crawler_cls.__name__
        if not enabled:
            logger.info("⏭️  [%s] معطّل (enabled=False)", name)
            continue

        crawler = crawler_cls()
        try:
            logger.info("⏳ [%s] بدء...", name)
            results = crawler.run()
            logger.info("  • %s: %d مناقصة", name, len(results))
            all_tenders.extend(results)
        except Exception as e:
            logger.error("  [!] خطأ في %s: %s", name, e)
        finally:
            closer = getattr(crawler, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception as e:
                    logger.debug("close() failed for %s: %s", name, e)

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
    """نقطة الدخول: زحف، ترشيح، ثم تسليم وحيد تحت قفل قاعدة البيانات."""
    config = AppConfig.from_env()
    setup_logging(config.log_level)
    dry_run = config.dry_run
    logger.info("=" * 60)
    logger.info("🚀 بدء تشغيل DZ-TENDERS-MVP")
    logger.info("=" * 60)

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

    # المسار مطلق دائماً: نسبيٌ يُحلّ على مجلد العمل ينتج قاعدتين مختلفتين
    # بين main.py و run_smart_scraper.py، فيفقد القفل معناه.
    db_path = resolve_db_path(config.db_path)
    report_path: str | None = None

    def build_report(pending: list[dict]) -> None:
        """توليد تقرير Excel من الصفقات الجديدة (داخل القفل)."""
        nonlocal report_path
        report_path = build_excel_report(pending)
        logger.info("📄 تقرير Excel: %s", report_path)

    def send(new_tenders: list[dict]) -> tuple[bool, str]:
        """إرسال التقرير عبر القنوات المسجّلة.

        Returns:
            (نجاح، سبب_الخطأ) — النجاح يعني نجاح قناة نصية واحدة على الأقل.
        """
        summary = build_summary_message(new_tenders)
        logger.info("📤 جاري الإرسال إلى تلغرام...")
        results = notifier.broadcast(summary, filepath=report_path)
        logger.info(f"نتائج الإرسال: {results}")

        if any(entry.get("text_ok") is True for entry in results):
            return True, ""

        error_msg = "; ".join(
            str(entry.get("error", "unknown")) for entry in results if entry.get("error")
        )
        return False, error_msg

    outcome = deliver(
        db_path,
        lambda: TenderStore(db_path=db_path),
        filtered,
        send if notifier is not None else None,
        dry_run=dry_run,
        on_pending=build_report,
        label="main.py",
    )

    if outcome.status == STATUS_LOCKED:
        logger.warning("توقّفت الدورة: قاعدة البيانات مشغولة في عملية أخرى (بلا كتابة)")
        raise SystemExit(LOCK_TIMEOUT_EXIT_CODE)

    logger.info(f"📊 إجمالي المناقصات المسجلة: {outcome.total}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
