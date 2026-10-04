"""
storage/paths.py
مصدر واحد لمسار قاعدة البيانات: مسار مطلق واحد مهما اختلف مجلد العمل.
"""

import os
from pathlib import Path

from .database import DEFAULT_DB_PATH

#: المسار النسبي الافتراضي، نفسه حرفياً في ``config.AppConfig.db_path``.
DEFAULT_RELATIVE_DB_PATH = "storage/tenders.db"

#: جذر المستودع — أي المسار النسبي يُحلّ نسبةً إليه لا نسبةً لمجلد العمل.
REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> str:
    """تحديد المسار المطلق لقاعدة بيانات المناقصات.

    المسار النسبي (``storage/tenders.db``) يُحلّ في الأصل نسبةً إلى مجلد العمل
    الجاري، فتشير قيمته إلى ملف مختلف كلما تغيّر ذلك المجلد — ويصير حينها
    ``DB_PATH`` في ``main.py`` و ``DEFAULT_DB_PATH`` في ``run_smart_scraper.py``
    على ملفين مختلفين بصمت، ويفقد القفل معناه. لذلك يُربط كل مسار نسبي
    بجذر المستودع بدل مجلد العمل، فيصبح الملف واحداً على كل نظام، ويُطابق
    ``storage.database.DEFAULT_DB_PATH`` بلا وسائط.

    Args:
        db_path: مسار صريح من الوسطاء (``AppConfig.db_path`` أو ``--db``).
            عند None يُقرأ ``DB_PATH`` من البيئة، ثم يقع على الافتراضي.

    Returns:
        المسار المطلق المطبَّع، صالح مباشرةً لـ ``sqlite3.connect``.
    """
    raw = db_path or os.getenv("DB_PATH") or DEFAULT_RELATIVE_DB_PATH
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return str(path.resolve())


def is_default_db_path(db_path: str | os.PathLike[str]) -> bool:
    """هل يشير المسار إلى نفس الملف الذي يستخدمه ``TenderDatabase`` بلا وسائط؟"""
    return Path(db_path) == Path(DEFAULT_DB_PATH)


__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_RELATIVE_DB_PATH",
    "is_default_db_path",
    "resolve_db_path",
]
