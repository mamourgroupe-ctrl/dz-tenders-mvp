import os
import json
import logging
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from crawlers import (
    ADECrawler, AlgeriaTendersCrawler, ONACrawler, MarchesPublicsCrawler
)
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
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("يجب ضبط TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID في .env")


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
        families = " | ".join(
            [f["name_ar"] for f in item.get("matched_families", [])]
        )
        wilaya = item.get("wilaya", "غير محددة")
        icon = "[T]" if item.get("wilaya_priority") == "target" else (
            "[P]" if item.get("wilaya_priority") == "priority" else "[-]"
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


def main():
    print("=" * 70)
    print("   DZ-TENDERS-MVP : فحص المناقصات")
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

    unique_tenders = list(
        {t.get("title", ""): t for t in all_tenders if t.get("title")}.values()
    )
    print(f"   الاجمالي: {len(unique_tenders)} مناقصة فريدة")

    print("\n[2/5] الفلترة...")
    filter_obj = TenderFilter()
    filtered = filter_obj.filter_tenders(unique_tenders)
    summary = filter_obj.summary(filtered)
    print(f"   {summary['total_filtered']} مناقصة مستهدفة")

    print("\n[3/5] قاعدة البيانات...")
    db = TenderDatabase()
    new_count = 0
    dup_count = 0
    for t in filtered:
        if db.add_tender(t):
            new_count += 1
        else:
            dup_count += 1
    print(f"   جديدة: {new_count} | مكررة: {dup_count}")

    print("\n[4/5] المناقصات الجديدة...")
    new_tenders = db.get_new_tenders(filtered)
    print(f"   {len(new_tenders)} مناقصة جديدة")
    stats = db.stats()
    print(f"   الاجمالي في DB: {stats['total']}")

    print("\n[5/5] الحفظ والارسال...")
    save_to_json(filtered)
    excel_file = "tenders_results.xlsx"
    save_to_excel(filtered, filename=excel_file)

    if new_tenders:
        target = TELEGRAM_CHANNEL_ID or TELEGRAM_CHAT_ID
        print(f"   [TARGET] Sending to: {target}")
        notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, target)
        text_report = format_telegram_message(new_tenders, stats)
        notifier.send_message(text_report)
        notifier.send_excel_report(
            excel_file,
            caption=f"{len(new_tenders)} مناقصة جديدة - {datetime.now().strftime('%Y-%m-%d')}",
        )
        for t in new_tenders:
            db.mark_notified(t)
        print(f"   تم ارسال {len(new_tenders)} مناقصة!")
    else:
        print("   لا توجد مناقصات جديدة.")

    print("\n" + "=" * 70)
    print("   انتهت العملية")
    print("=" * 70)


if __name__ == "__main__":
    main()
