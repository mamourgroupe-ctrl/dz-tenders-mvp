"""اختبارات توحيد مسار قاعدة البيانات (``storage.paths``)."""

import os
from pathlib import Path

from storage.database import DEFAULT_DB_PATH
from storage.paths import (
    DEFAULT_RELATIVE_DB_PATH,
    is_default_db_path,
    resolve_db_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_resolve_db_path_returns_absolute_path():
    """المسار الافتراضي يُطبَّع إلى مسار مطلق."""
    resolved = resolve_db_path()

    assert os.path.isabs(resolved)
    assert resolved == str(Path(resolved).resolve())


def test_resolve_db_path_is_cwd_independent(tmp_path, monkeypatch):
    """المسار الن��بي يشير إلى الملف نفسه من أي مجلد عمل."""
    from_root = resolve_db_path(DEFAULT_RELATIVE_DB_PATH)

    monkeypatch.chdir(tmp_path)
    from_tmp = resolve_db_path(DEFAULT_RELATIVE_DB_PATH)

    assert from_root == from_tmp


def test_resolve_db_path_matches_database_default():
    """توافق خلفي: القيمة المطلقة تطابق ``DEFAULT_DB_PATH`` بلا وسائط."""
    assert is_default_db_path(resolve_db_path()) is True
    assert is_default_db_path(resolve_db_path(DEFAULT_DB_PATH)) is True


def test_resolve_db_path_honours_explicit_override(tmp_path):
    """الوسيط الصريح يتغلّب على كل شيء ولا يُنسب إلى الجذر."""
    target = tmp_path / "custom.db"

    resolved = resolve_db_path(str(target))

    assert resolved == str(target.resolve())
    assert is_default_db_path(resolved) is False


def test_resolve_db_path_reads_env_when_no_argument(monkeypatch, tmp_path):
    """غياب الوسيط يُقرأ من ``DB_PATH``."""
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "from_env.db"))

    assert resolve_db_path() == str((tmp_path / "from_env.db").resolve())


def test_resolve_db_path_expands_user_home(monkeypatch):
    """``~`` في المسار يُوسَّع إلى الدليل الفعلي."""
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv("DB_PATH", "~/tenders_home.db")

    resolved = resolve_db_path()

    assert "~" not in resolved
    assert Path(resolved).is_absolute()


def test_resolve_db_path_from_nested_cwd_still_hits_repo_db(tmp_path, monkeypatch):
    """تشغيل سكربت من مجلد متشعّب لا يولّد قاعدة بيانات ثانية."""
    monkeypatch.delenv("DB_PATH", raising=False)
    nested = tmp_path / "deep" / "deeper"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    resolved = resolve_db_path()

    assert Path(resolved) == REPO_ROOT / "storage" / "tenders.db"
