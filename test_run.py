import os
import json
import pandas as pd
from dotenv import load_dotenv
from crawlers import ADECrawler, AlgeriaTendersCrawler, ONACrawler
from telegram_notifier import TelegramNotifier
from tender_filter import TenderFilter  # ✅ إضافة الفلتر

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("❌ يجب ضبط TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID في ملف .env")


def save_to_json(data, filename="tenders_results.json"):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def save_to_excel(data, filename="tenders_results.xlsx"):
    if not data:
        return
    df = pd.DataFrame(data)
    # إزالة الأعمدة المعقدة قبل التصدير
    df_export = df.drop(columns=["matched_families", "matched_products"], errors="ignore")
    columns_mapping = {
        "title": "عنوان المناقصة",
        "organisation": "الهيئة / الجهة",
        "wilaya": "الولاية",
        "product": "نوع المنتج",
        "deadline": "آخر أجل للتسليم",
        "status": "الحالة",
        "link": "رابط المناقصة",
        "relevance_score": "درجة الأهمية",
    }
    df_export = df_export.rename(columns=columns_mapping)
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name="المناقصات المستهدفة")


def format_telegram_message(tenders):
    """تنسيق تقرير أنيق للرسالة النصية"""
    msg = f"🔔 <b>تقرير المناقصات المستهدفة (DZ-TENDERS)</b>\n"
    msg += f"📊 <b>إجمالي الصفقات المطابقة:</b> {len(tenders)}\n"
    msg += "━" * 30 + "\n\n"

    for idx, item in enumerate(tenders[:15], 1):  # أول 15 مناقصة فقط
        families = " | ".join([f["name_ar"] for f in item.get("matched_families", [])])
        msg += f"<b>[{idx}] {item['title']}</b>\n"
        msg += f"🏛️ <b>الجهة:</b> {item['organisation']}\n"
        msg += f"📍 <b>الولاية:</b> {item['wilaya']}\n"
        msg += f"🎯 <b>العائلة:</b> {families}\n"
        msg += f"🔗 <a href='{item['link']}'>رابط الصفقة</a>\n\n"

    if len(tenders) > 15:
        msg += f"\n<i>... و {len(tenders) - 15} مناقصة أخرى في ملف Excel.</i>\n"

    msg += "\n📎 <i>تم إرفاق ملف Excel التفصيلي.</i>"
    return msg


def main():
    print("=" * 70)
    print("   🚀 DZ-TENDERS-MVP : فحص المناقصات وإرسال التنبيهات")
    print("=" * 70)

    # 1. جمع المناقصات
    crawlers = [ADECrawler(), ONACrawler(), AlgeriaTendersCrawler()]
    all_tenders = []

    for crawler in crawlers:
        try:
            all_tenders.extend(crawler.run())
        except Exception as e:
            print(f"[!] خطأ في {crawler.__class__.__name__}: {e}")

    unique_tenders = list({t['title']: t for t in all_tenders}.values())
    print(f"\n[📥] تم جمع {len(unique_tenders)} مناقصة فريدة")

    # 2. فلترة المناقصات
    print("\n[🔍] جاري فلترة المناقصات حسب الأهداف التسويقية...")
    filter_obj = TenderFilter()
    filtered_tenders = filter_obj.filter_tenders(unique_tenders)

    summary = filter_obj.summary(filtered_tenders)
    print(f"[✅] تم تصنيف {summary['total_filtered']} مناقصة مستهدفة")
    print("\n📊 التوزيع حسب العائلة:")
    for fid, info in summary["by_family"].items():
        print(f"   • {info['name']}: {info['count']} مناقصة ({info['priority']})")

    # 3. حفظ الملفات
    save_to_json(filtered_tenders)
    excel_file = "tenders_results.xlsx"
    save_to_excel(filtered_tenders, filename=excel_file)

    # 4. إرسال إلى تلغرام
    if filtered_tenders:
        print("\n[📤] جاري إرسال التقرير إلى تلغرام...")
        notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        text_report = format_telegram_message(filtered_tenders)
        notifier.send_message(text_report)
        notifier.send_excel_report(
            excel_file,
            caption=f"📊 تقرير DZ-TENDERS ({len(filtered_tenders)} مناقصة مستهدفة)"
        )
        print("[✅] تم الإرسال بنجاح!")
    else:
        print("\n[ℹ️] لا توجد مناقصات مطابقة للمعايير الحالية.")


if __name__ == "__main__":
    main()