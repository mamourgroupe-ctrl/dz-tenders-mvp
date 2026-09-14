"""
notifications/excel_report.py
توليد تقرير Excel من قائمة المناقصات.
"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)

COLUMNS_MAPPING = {
    "title": "عنوان المناقصة",
    "organisation": "الهيئة / الجهة",
    "wilaya": "الولاية",
    "product": "نوع المنتج",
    "deadline": "آخر أجل للتسليم",
    "status": "الحالة",
    "link": "رابط المناقصة",
    "relevance_score": "درجة الأهمية",
}


def build_excel_report(tenders: list[dict], filename: str = "tenders_results.xlsx") -> str:
    """ينشئ ملف Excel ويعيد مساره."""
    if not tenders:
        logger.warning("لا توجد مناقصات لتصديرها")
        return None

    df = pd.DataFrame(tenders)
    # إزالة الأعمدة المعقدة (قوائم/dicts) قبل التصدير
    df = df.drop(
        columns=["matched_families", "matched_products"],
        errors="ignore",
    )
    df = df.rename(columns=COLUMNS_MAPPING)

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="المناقصات المستهدفة")

    logger.info(f"✅ تم إنشاء التقرير: {filename}")
    return filename