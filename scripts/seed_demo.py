#!/usr/bin/env python3
"""
Seed demo tenders into SQLite database.
Idempotent - safe to run multiple times.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from storage.database import TenderDatabase  # noqa: E402


def main():
    """Create/initialize database and insert 41 demo tenders."""
    db = TenderDatabase()
    wilayas = [
        "أدرار",
        "الشلف",
        "الأغواط",
        "أم البواقي",
        "باتنة",
        "بجاية",
        "بسكرة",
        "بشار",
        "البليدة",
        "البويرة",
        "تمنراست",
        "تبسة",
        "تلمسان",
        "تيارت",
        "تيزي وزو",
        "الجزائر",
        "الجلفة",
        "جيجل",
        "سطيف",
        "سعيدة",
        "سكيكدة",
        "سيدي بلعباس",
        "عنابة",
        "قالمة",
        "قسنطينة",
        "المدية",
        "مستغانم",
        "المسيلة",
        "معسكر",
        "ورقلة",
        "وهران",
        "البيض",
        "إليزي",
        "برج بوعريريج",
        "بومرداس",
        "الطارف",
        "تندوف",
        "تيسمسيلت",
        "الوادي",
        "خنشلة",
        "سوق أهراس",
        "تيبازة",
        "ميلة",
        "عين الدفلى",
        "النعامة",
        "عين تموشنت",
        "غرداية",
        "غليزان",
        "تيميمون",
        "برج باجي مختار",
        "أولاد جلال",
        "بني عباس",
        "عين صالح",
        "عين قزام",
        "تقرت",
        "جانت",
        "المغير",
        "المنيعة",
    ]

    products = ["أعمال أشغال", "توريد معدات", "أنابيب PVC", "أنابيب PEHD", "خزانات PE"]

    titles = [
        "اقتناء معدات طبية للمستشفى الجهوي",
        "إنجاز طريق ولائي بطول 15 كلم",
        "توريد أنابيب PVC لشبكة المياه",
        "بناء مدرسة ابتدائية",
        "تجهيز مكاتب إدارية",
        "صيانة شبكة الإنارة العمومية",
        "توريد أثاث مدرسي",
        "إنجاز قنطرة على مسيل مائي",
        "اقتناء سيارات إسعاف مجهزة",
        "ترميم مبنى الإدارة المحلية",
        "توريد مواد البناء",
        "إنجاز شبكة صرف صحي",
        "تجهيز مختبر تحليلي",
        "صيانة الطرق البلدية",
        "اقتناء أجهزة حاسوب ومعدات إعلام آلي",
        "إنجاز ملعب رياضي",
        "توريد غذاء مدرسي",
        "بناء قسم الطوارئ بالمستشفى",
        "صيانة محطة ضخ المياه",
        "إنجاز حظيرة للآليات البلدية",
    ]

    portals = [
        "https://www.marches-publics.gov.dz/tender/",
        "https://baosem.com/tender/",
        "https://mounakassatdz.com/tender/",
    ]

    count_added = 0
    for i in range(1, 42):  # 41 tenders
        tender = {
            "title": titles[i % len(titles)],
            "organisation": "وزارة الصناعة والمناجم",
            "wilaya": wilayas[i % len(wilayas)],
            "product": products[i % len(products)],
            "deadline": "2026-12-31",
            "status": "ouvert",
            "link": f"{portals[i % len(portals)]}{12345 + i}",
            "relevance_score": 70 + (i % 30),
        }
        if db.add_tender(tender):
            count_added += 1

    print(f"Database initialized at {db.db_path}")
    print(f"Added {count_added} new tenders (total will be checked by API)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
