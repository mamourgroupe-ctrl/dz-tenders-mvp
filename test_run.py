import json
import pandas as pd
from crawlers import ADECrawler, AlgeriaTendersCrawler, ONACrawler
from telegram_notifier import TelegramNotifier

# 🔑 أدخل معلومات البوت الخاصة بك هنا
TELEGRAM_BOT_TOKEN = "8835703293:AAG0qpNumTw-kh5VitaY8el9wRYv1qCT7R8"
TELEGRAM_CHAT_ID = "5036844498"

def save_to_json(data, filename="tenders_results.json"):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def save_to_excel(data, filename="tenders_results.xlsx"):
    if not data:
        return
    df = pd.DataFrame(data)
    columns_mapping = {
        "title": "عنوان المناقصة",
        "organisation": "الهيئة / الجهة",
        "wilaya": "الولاية",
        "product": "نوع المنتج",
        "deadline": "آخر أجل للتسليم",
        "status": "الحالة",
        "link": "رابط المناقصة"
    }
    df = df.rename(columns=columns_mapping)
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="كل المناقصات")

def format_telegram_message(tenders):
    """تنسيق تقرير أنيق للرسالة النصية"""
    msg = f"🔔 <b>تقرير المناقصات الجديد (DZ-TENDERS)</b>\n"
    msg += f"📊 <b>إجمالي الصفقات المستخرجة:</b> {len(tenders)}\n"
    msg += "ــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــ\n\n"
    
    for idx, item in enumerate(tenders, 1):
        msg += f"<b>[{idx}] {item['title']}</b>\n"
        msg += f"🏢 <b>الجهة:</b> {item['organisation']}\n"
        msg += f"📍 <b>الولاية:</b> {item['wilaya']} | 📦 <b>المنتج:</b> {item['product']}\n"
        msg += f"🔗 <a href='{item['link']}'>رابط الصفقة المباشر</a>\n\n"
        
    msg += "📎 <i>تم إرفاق ملف Excel التفصيلي بالأسفل.</i>"
    return msg

def main():
    print("=" * 70)
    print("   🚀 DZ-TENDERS-MVP : فحص المناقصات وإرسال التنبيهات عبر Telegram")
    print("=" * 70)

    crawlers = [ADECrawler(), ONACrawler(), AlgeriaTendersCrawler()]
    all_tenders = []

    for crawler in crawlers:
        try:
            all_tenders.extend(crawler.run())
        except Exception as e:
            print(f"[!] خطأ في {crawler.__class__.__name__}: {e}")

    unique_tenders = list({t['title']: t for t in all_tenders}.values())

    # حفظ الملفات محلياً
    save_to_json(unique_tenders)
    excel_file = "tenders_results.xlsx"
    save_to_excel(unique_tenders, filename=excel_file)

    # إرسال التنبيه والملف إلى تلغرام
    if TELEGRAM_BOT_TOKEN != "ضع_هنا_TOKEN_الخاص_ببوتينك":
        print("\n[📲] جاري إرسال الإشعار والتقرير إلى تلغرام...")
        notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        
        # 1. إرسال النص
        text_report = format_telegram_message(unique_tenders)
        notifier.send_message(text_report)
        
        # 2. إرسال ملف Excel
        notifier.send_excel_report(excel_file, caption="📊 تقرير المناقصات المجمعة - DZ TENDERS")
        print("[✓] تم إرسال التقرير إلى هاتفك بنجاح!")
    else:
        print("\n[!] تذكير: يرجى وضع BOT_TOKEN و CHAT_ID لتفعيل إشعارات تلغرام.")

if __name__ == "__main__":
    main()