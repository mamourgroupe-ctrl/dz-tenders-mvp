"""
test_run.py
فحص المناقصات عبر كل المصادر.

الاستخدام:
    python test_run.py                 # فحص كامل مع إرسال تلغرام
    python test_run.py --dry-run       # فحص بلا إرسال (يُستخدم في CI)
"""

import argparse
import json
import logging
import os
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

from crawlers import ADECrawler, AlgeriaTendersCrawler, MarchesPublicsCrawler, ONACrawler
from storage.db import TenderStore
from storage.delivery import (
    STATUS_EMPTY,
    STATUS_FAILED,
    STATUS_LOCKED,
    STATUS_SENT,
    deliver,
)
from storage.lock import LOCK_TIMEOUT_EXIT_CODE
from storage.paths import resolve_db_path
from telegram_notifier import TelegramNotifier
from tender_filter import TenderFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

MISSING_CREDENTIALS_HINT = "يجب ضبط TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID في .env"


def _credentials() -> tuple[str | None, str | None, str | None]:
    """قراءة بيانات تلغرام من البيئة.

    تُقرأ داخل ``main`` لا عند الاستيراد: تحميل ``.env`` يحدث في كتلة
    ``__main__`` فقط، فقراءة متغيّرات البيئة كثوابت عند الاستيراد كانت
    تُعيد ``None`` دائماً وتُلوّث أي اختبار يستورد هذه الوحدة.

    Returns:
        (التوكن، معرّف المحادثة، معرّف القناة) وقد تكون أيّها None.
    """
    return (
        os.getenv("TELEGRAM_BOT_TOKEN"),
        os.getenv("TELEGRAM_CHAT_ID"),
        os.getenv("TELEGRAM_CHANNEL_ID"),
    )


def _build_parser() -> argparse.ArgumentParser:
    """بناء محلّل وسائط الأوامر."""
    parser = argparse.ArgumentParser(
        prog="python test_run.py",
        description="فحص المناقصات عبر كل المصادر",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="جمع المناقصات وحفظ التقارير بلا إرسال عبر تلغرام",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="مسار قاعدة البيانات (افتراضياً من DB_PATH أو storage/tenders.db)",
    )
    return parser


def save_to_json(data, filename="tenders_results.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=str)


def save_to_excel(data, filename="tenders_results.xlsx"):
    if not data:
        return
    df = pd.DataFrame(data)
    df_export = df.drop(columns=["matched_families", "matched_products"], errors="ignore")
    columns_mapping = {
        "title": "عنوان المناقصة",
        "organisation": "الهيئة / الجهة",
        "wilaya": "الولاية",
        "product": "نوع المنتج",
        "deadline": "آخر جل",
        "status": "الحالة",
        "link": "الرابط",
        "relevance_score": "درجة الهمية",
        "wilaya_priority": "ولوية الولاية",
    }
    df_export = df_export.rename(columns=columns_mapping)
    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="المناقصات")


def format_telegram_message(new_tenders, stats):
    today = datetime.now().strftime("%Y-%m-%d")
    msg = f"تقرير المناقصات - {today}\n"
    msg += "=" * 28 + "\n\n"
    msg += "احصائيات سريعة:\n"
    msg += f"   - مناقصات جديدة اليوم: {len(new_tenders)}\n"
    msg += f"   - الاجمالي: {stats['total']}\n"
    msg += f"   - غير مرسلة: {stats['new_unnotified']}\n"
    msg += "=" * 28 + "\n\n"

    for idx, item in enumerate(new_tenders[:10], 1):
        families = " | ".join([f["name_ar"] for f in item.get("matched_families", [])])
        wilaya = item.get("wilaya", "غير محددة")
        icon = (
            "[T]"
            if item.get("wilaya_priority") == "target"
            else ("[P]" if item.get("wilaya_priority") == "priority" else "[-]")
        )

        msg += f"[{idx}] {item['title']}\n"
        msg += f"     الجهة: {item.get('organisation', 'غير محددة')}\n"
        msg += f"     {icon} الولاية: {wilaya}\n"
        if families:
            msg += f"     العائلة: {families}\n"
        msg += f"     الرابط: {item.get('link', '#')}\n\n"

    if len(new_tenders) > 10:
        msg += f"\n... و {len(new_tenders) - 10} اخرى في Excel.\n"

    msg += "\nملف Excel مرفق."
    return msg


def main(argv=None):
    """نقطة دخول الفحص.

    Args:
        argv: الوسائط (افتراضياً ``sys.argv[1:]``).

    Returns:
        رمز خروج العملية (0 نجاح).
    """
    args = _build_parser().parse_args(argv)
    dry_run = args.dry_run
    bot_token, chat_id, channel_id = _credentials()

    if not dry_run and not (bot_token and chat_id):
        raise ValueError(MISSING_CREDENTIALS_HINT)

    print("=" * 70)
    print("   DZ-TENDERS-MVP : فحص المناقصات")
    if dry_run:
        print("   [DRY-RUN] لن يُرسل أي إشعار")
    print("=" * 70)

    print("\n[1/5] جمع المناقصات من المصادر...")
    crawlers = [
        ADECrawler(),
        ONACrawler(),
        AlgeriaTendersCrawler(),
        MarchesPublicsCrawler(),
    ]
    all_tenders = []

    for crawler in crawlers:
        try:
            results = crawler.run()
            print(f"   - {crawler.__class__.__name__}: {len(results)}")
            all_tenders.extend(results)
        except Exception as e:
            print(f"   [!] {crawler.__class__.__name__}: {e}")

    unique_tenders = list({t.get("title", ""): t for t in all_tenders if t.get("title")}.values())
    print(f"   الاجمالي: {len(unique_tenders)} مناقصة فريدة")

    print("\n[2/5] الفلترة...")
    filter_obj = TenderFilter()
    filtered = filter_obj.filter_tenders(unique_tenders)
    summary = filter_obj.summary(filtered)
    print(f"   {summary['total_filtered']} مناقصة مستهدفة")

    print("\n[3/5] قاعدة البيانات...")
    db_path = resolve_db_path(args.db)
    print(f"   {db_path}")

    print("\n[4/5] الحفظ والارسال...")
    save_to_json(filtered)
    excel_file = "tenders_results.xlsx"
    save_to_excel(filtered, filename=excel_file)

    def send(pending: list[dict]) -> tuple[bool, str]:
        """إرسال الصفقات الجديدة عبر تلغرام.

        Returns:
            (نجاح، سبب_الخطأ).
        """
        target = channel_id or chat_id
        print(f"   [TARGET] Sending to: {target}")
        notifier = TelegramNotifier(bot_token, target)
        stats = TenderStore(db_path=db_path).stats()
        notifier.send_message(format_telegram_message(pending, stats))
        notifier.send_excel_report(
            excel_file,
            caption=f"{len(pending)} مناقصة جديدة - {datetime.now().strftime('%Y-%m-%d')}",
        )
        return True, ""

    # نفس مسار التسليم الموحّد المستعمل في main.py: قفل واحد، ترحيل واحد.
    # يمرّ الصفقات المحجوبة تلقائياً لأن الفحص يتم عبر is_new_or_changed.
    outcome = deliver(
        db_path,
        lambda: TenderStore(db_path=db_path),
        filtered,
        send if not dry_run else None,
        dry_run=dry_run,
        label="test_run.py",
    )

    if outcome.status == STATUS_LOCKED:
        print("Database is locked by another process — cycle skipped")
        raise SystemExit(LOCK_TIMEOUT_EXIT_CODE)

    print(f"   الاجمالي في DB: {outcome.total}")

    if dry_run:
        print("   [DRY-RUN] تم حفظ التقارير دون إرسال.")
    elif outcome.status == STATUS_SENT:
        print(f"   تم ارسال {len(outcome.pending)} مناقصة!")
    elif outcome.status == STATUS_EMPTY:
        print("   لا توجد مناقصات جديدة.")
    elif outcome.status == STATUS_FAILED:
        print(f"   فشل الإرسال: {outcome.error}")

    print("\n" + "=" * 70)
    print("   انتهت العملية")
    print("=" * 70)


if __name__ == "__main__":
    load_dotenv()
    main()
