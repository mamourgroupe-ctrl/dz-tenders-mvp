import os
import json
import logging
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from crawlers import ADECrawler, AlgeriaTendersCrawler, ONACrawler
from telegram_notifier import TelegramNotifier
from tender_filter import TenderFilter
from storage import TenderDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("يجب ضبط TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID في ملف .env")


def save_to_json(data, filename="tenders_results.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=str)


def save_to_excel(data, filename="tenders_results.xlsx"):
    if not data:
        return
    df = pd.DataFrame(data)
    df_export = df.drop(
        columns=["matched_families", "matched_products"], errors="ignore"
    )
    columns_mapping = {
        "title": "عنوان المناقصة",
        "organisation": "الهيئة / الجهة",
        "wilaya": "الولاية",
        "product": "نوع المنتج",
        "deadline": "آخر جل للتسليم",
        "status": "الحالة",
        "link": "رابط المناقصة",
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

    msg += "حصائيات سريعة:\n"
    msg += f"   - مناقصات جديدة اليوم: {len(new_tenders)}\n"
    msg += f"   - جمالي المناقصات المحفوظة: {stats['total']}\n"
    msg += f"   - مناقصات جديدة (لم ترسل): {stats['new_unnotified']}\n"
    msg += "=" * 28 + "\n\n"

    for idx, item in enumerate(new_tenders[:10], 1):
        families = " | ".join(
            [f["name_ar"] for f in item.get("matched_families", [])]
        )
        wilaya = item.get("wilaya", "غير محددة")
        wilaya_priority = item.get("wilaya_priority", "")

        icon = "[T]" if wilaya_priority == "target" else (
            "[P]" if wilaya_priority == "priority" else "[-]"
        )

        msg += f"[{idx}] {item['title']}\n"
        msg += f"     الجهة: {item.get('organisation', 'غير محددة')}\n"
        msg += f"     {icon} الولاية: {wilaya}\n"
        if families:
            msg += f"     العائلة: {families}\n"
        msg += f"     الرابط: {item.get('link', '#')}\n\n"

    if len(new_tenders) > 10:
        msg += f"\n... و {len(new_tenders) - 10} مناقصة خرى في ملف Excel.\n"

    msg += "\nملف Excel مرفق."
    return msg


def main():
    print("=" * 70)
    print("   DZ-TENDERS-MVP : فحص المناقصات ورسال التنبيهات")
    print("=" * 70)

    print("\n[1/5] جاري جمع المناقصات...")
    crawlers = [ADECrawler(), ONACrawler(), AlgeriaTendersCrawler()]
    all_tenders = []

    for crawler in crawlers:
        try:
            results = crawler.run()
            print(f"   - {crawler.__class__.__name__}: {len(results)}")
            all_tenders.extend(results)
        except Exception as e:
            print(f"   [!] {crawler.__class__.__name__}: {e}")

    unique_tenders = list(
        {t.get("title", ""): t for t in all_tenders if t.get("title")}.values()
    )
    print(f"   جمالي: {len(unique_tenders)} مناقصة فريدة")

    print("\n[2/5] جاري الفلترة...")
    filter_obj = TenderFilter()
    filtered = filter_obj.filter_tenders(unique_tenders)
    summary = filter_obj.summary(filtered)
    print(f"   {summary['total_filtered']} مناقصة مستهدفة")

    print("\n[3/5] جاري دارة قاعدة البيانات...")
    db = TenderDatabase()

    new_count = 0
    duplicate_count = 0
    for t in filtered:
        if db.add_tender(t):
            new_count += 1
        else:
            duplicate_count += 1

    print(f"   جديدة: {new_count}")
    print(f"   مكررة: {duplicate_count}")

    print("\n[4/5] تحديد المناقصات الجديدة...")
    new_tenders = db.get_new_tenders(filtered)
    print(f"   {len(new_tenders)} مناقصة جديدة للرسال")

    stats = db.stats()
    print(f"\n   الحصائيات:")
    print(f"      - الجمالي في DB: {stats['total']}")
    print(f"      - اليوم: {stats['today']}")
    print(f"      - غير مرسلة: {stats['new_unnotified']}")
    if stats["by_wilaya"]:
        print(f"      - حسب الولاية (على 5):")
        for w in stats["by_wilaya"][:5]:
            print(f"         - {w['wilaya']}: {w['count']}")

    print("\n[5/5] جاري الحفظ والرسال...")
    save_to_json(filtered)
    excel_file = "tenders_results.xlsx"
    save_to_excel(filtered, filename=excel_file)
    print(f"   تم حفظ {len(filtered)} مناقصة")

    if new_tenders:
        notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        text_report = format_telegram_message(new_tenders, stats)
        notifier.send_message(text_report)
        notifier.send_excel_report(
            excel_file,
            caption=f"{len(new_tenders)} مناقصة جديدة - {datetime.now().strftime('%Y-%m-%d')}",
        )
        for t in new_tenders:
            db.mark_notified(t)
        print(f"   تم رسال {len(new_tenders)} مناقصة جديدة!")
    else:
        print("   لا توجد مناقصات جديدة للرسال.")

    print("\n" + "=" * 70)
    print("   انتهت العملية")
    print("=" * 70)


if __name__ == "__main__":
    main()
