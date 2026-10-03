"""اختبارات طبقة التخزين: الترحيل، عدّاد المحاولات، الحجب، وفك الحجب."""

import sqlite3

import pytest

from storage.database import MAX_DELIVERY_ATTEMPTS, TenderDatabase
from storage.db import TenderStore

TENDER = {
    "title": "مناقصة أنابيب PEHD",
    "organisation": "TEST ORG",
    "link": "https://ade.dz/diag",
    "relevance_score": 5,
    "matched_families": [{"id": "fam1", "name_ar": "مواد البناء"}],
}


def _legacy_db(tmp_path, rows: int = 0, unnotified: int = 0) -> str:
    """بناء قاعدة بالمخطط القديم (قبل بنود المحاولات) على النمط المحدد في الخطة."""
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            organisation TEXT,
            wilaya TEXT,
            product TEXT,
            deadline TEXT,
            status TEXT,
            link TEXT,
            relevance_score INTEGER DEFAULT 0,
            matched_families TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            notified INTEGER DEFAULT 0
        );
    """)
    for i in range(rows):
        conn.execute(
            """
            INSERT INTO tenders (
                fingerprint, title, first_seen, last_seen, notified
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (f"fp{i}", f"صفقة {i}", "2026-01-01", "2026-01-01", i >= unnotified),
        )
    conn.commit()
    conn.close()
    return path


def _columns(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {row[1] for row in conn.execute("PRAGMA table_info(tenders)")}
    conn.close()
    return names


def _row(db_path: str, fingerprint: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    found = conn.execute("SELECT * FROM tenders WHERE fingerprint = ?", (fingerprint,)).fetchone()
    conn.close()
    return dict(found) if found else {}


# ── نقطة 5: تسامح matched_families بلا id ────────────────────────────────────


def test_add_tender_tolerates_family_without_id(tmp_path, caplog):
    """عائلة بلا id تُتجاوز بتحذير ولا تُسقط الصف."""
    db_path = str(tmp_path / "no_id.db")
    store = TenderStore(db_path=db_path)
    payload = {**TENDER, "matched_families": [{"name_ar": "بلا معرّف"}]}

    with caplog.at_level("WARNING"):
        assert store.add_tender(payload) is True

    row = _row(db_path, store._fingerprint(payload))
    assert row["matched_families"] == ""
    assert "بلا معرّف id" in caplog.text


def test_add_tender_keeps_valid_family_ids(tmp_path):
    """العائلات التي تحمل id تُحفظ كما هي."""
    store = TenderStore(db_path=str(tmp_path / "ok.db"))

    store.add_tender(TENDER)

    row = _row(store.db_path, store._fingerprint(TENDER))
    assert row["matched_families"] == "fam1"


# ── نقطة 6أ/6ب: المخطط والترحيل ────────────────────────────────────────────


def test_migration_adds_columns_to_existing_db(tmp_path):
    """قاعدة قديمة تُرحَّل: أعمدة جديدة + صفوف قديمة باقية."""
    db_path = _legacy_db(tmp_path, rows=2, unnotified=1)

    TenderStore(db_path=db_path)

    columns = _columns(db_path)
    assert {"retry_count", "blocked", "last_error", "last_attempt_at"} <= columns
    assert TenderStore(db_path=db_path).count() == 2


def test_migration_is_idempotent(tmp_path, caplog):
    """إنشاء المتجر مرتين لا يكرّر الحجب ولا يرمي استثناء."""
    db_path = _legacy_db(tmp_path, rows=3, unnotified=0)

    TenderStore(db_path=db_path)
    with caplog.at_level("WARNING"):
        TenderStore(db_path=db_path)

    assert "تم حجب" not in caplog.text


def test_one_time_guard_blocks_unnotified_rows_once(tmp_path, caplog):
    """الحماية تحجب الصفقات القديمة غير المُبلَّغ مرة واحدة فقط."""
    db_path = _legacy_db(tmp_path, rows=4, unnotified=2)

    with caplog.at_level("WARNING"):
        TenderStore(db_path=db_path)
        first_message = caplog.text
        caplog.clear()
        TenderStore(db_path=db_path)

    blocked_first = [fp for fp in ("fp0", "fp1") if _row(db_path, fp)["blocked"] == 1]
    notified = [fp for fp in ("fp2", "fp3") if _row(db_path, fp)["blocked"] == 0]

    assert len(blocked_first) == 2
    assert len(notified) == 2
    assert "حجب 2 صفقة" in first_message
    assert "unblock --all" in first_message
    assert "تم حجب" not in caplog.text


def test_migration_survives_concurrent_initialisation(tmp_path):
    """قاعدتان تبدآن معاً على مخطط قديم: لا «duplicate column name»."""
    db_path = _legacy_db(tmp_path, rows=1, unnotified=0)
    columns_before = _columns(db_path)

    first = TenderStore(db_path=db_path)
    second = TenderStore(db_path=db_path)

    assert columns_before < _columns(db_path)
    assert first.count() == second.count() == 1


# ── نقطة 6د: عدّاد المحاولات والحجب ─────────────────────────────────────────


def test_failed_attempts_are_counted(tmp_path):
    """كل محاولة فاشلة تزيد العدّاد وتسجّل الخطأ ووقت المحاولة."""
    store = TenderStore(db_path=str(tmp_path / "retry.db"))
    store.add_tender(TENDER)

    store.register_failed_attempt(TENDER, "timeout")
    store.register_failed_attempt(TENDER, "timeout")

    row = _row(store.db_path, store._fingerprint(TENDER))
    assert row["retry_count"] == 2
    assert row["blocked"] == 0
    assert row["last_error"] == "timeout"
    assert row["last_attempt_at"]


def test_third_failure_marks_blocked(tmp_path):
    """الوصول إلى الحدّ يحجب الصفقة."""
    store = TenderStore(db_path=str(tmp_path / "blocked.db"))
    store.add_tender(TENDER)

    for _ in range(MAX_DELIVERY_ATTEMPTS):
        attempts = store.register_failed_attempt(TENDER, "boom")

    assert attempts == MAX_DELIVERY_ATTEMPTS
    assert _row(store.db_path, store._fingerprint(TENDER))["blocked"] == 1


def test_register_failed_attempt_ignores_missing_row(tmp_path):
    """محاولة فاشلة لصفقة غير مخزَّنة لا ترمي استثناء."""
    store = TenderStore(db_path=str(tmp_path / "missing.db"))

    assert store.register_failed_attempt(TENDER, "boom") == 0


def test_blocked_tenders_lists_rows(tmp_path):
    """عرض الصفقات المحجوبة مع سبب آخر فشل."""
    store = TenderStore(db_path=str(tmp_path / "list.db"))
    store.add_tender(TENDER)
    for _ in range(MAX_DELIVERY_ATTEMPTS):
        store.register_failed_attempt(TENDER, "401 Unauthorized")

    rows = store.blocked_tenders()

    assert len(rows) == 1
    assert rows[0]["retry_count"] == MAX_DELIVERY_ATTEMPTS
    assert "401" in rows[0]["last_error"]


def test_unblock_clears_blocked_flag(tmp_path):
    """فك الحجب بالجماعة يعيد الصفقة للانتظار."""
    store = TenderStore(db_path=str(tmp_path / "unblock.db"))
    store.add_tender(TENDER)
    for _ in range(MAX_DELIVERY_ATTEMPTS):
        store.register_failed_attempt(TENDER, "boom")

    assert store.unblock_all() == 1

    row = _row(store.db_path, store._fingerprint(TENDER))
    assert row["blocked"] == 0
    assert row["retry_count"] == 0


def test_unblock_tender_by_fingerprint(tmp_path):
    """فك حجب صفقة واحدة عبر بصمتها، والباقي يبقى محجوباً."""
    store = TenderStore(db_path=str(tmp_path / "one.db"))
    store.add_tender(TENDER)
    other = {**TENDER, "link": "https://ade.dz/other"}
    store.add_tender(other)
    for payload in (TENDER, other):
        for _ in range(MAX_DELIVERY_ATTEMPTS):
            store.register_failed_attempt(payload, "boom")

    assert store.unblock_tender(store._fingerprint(TENDER)) is True

    assert _row(store.db_path, store._fingerprint(TENDER))["blocked"] == 0
    assert _row(store.db_path, store._fingerprint(other))["blocked"] == 1


def test_unblock_tender_unknown_fingerprint_returns_false(tmp_path):
    """بصمة غير موجودة تعيد False بلا استثناء."""
    store = TenderStore(db_path=str(tmp_path / "unknown.db"))

    assert store.unblock_tender("0" * 64) is False


# ── نقطة 3: مصفوفة is_new_or_changed ────────────────────────────────────────


def test_is_new_or_changed_true_when_row_missing(tmp_path):
    """صفقة غير مخزَّنة تحتاج إشعاراً."""
    store = TenderStore(db_path=str(tmp_path / "matrix.db"))

    assert store.is_new_or_changed(TENDER) is True


def test_is_new_or_changed_true_for_stored_but_unnotified(tmp_path):
    """الصفقة المخزَّنة وغير المُبلَّغ تعود للانتظار (إغلاق الفخ ب)."""
    store = TenderStore(db_path=str(tmp_path / "matrix.db"))
    store.add_tender(TENDER)

    assert store.is_new_or_changed(TENDER) is True


def test_is_new_or_changed_false_when_notified(tmp_path):
    """الصفقة المُبلَّغة سابقاً لا تُعاد."""
    store = TenderStore(db_path=str(tmp_path / "matrix.db"))
    store.mark_sent(TENDER)

    assert store.is_new_or_changed(TENDER) is False


def test_is_new_or_changed_false_when_blocked(tmp_path):
    """الصفقة المحجوبة لا تُعاد حتى فك الحجب."""
    store = TenderStore(db_path=str(tmp_path / "matrix.db"))
    store.add_tender(TENDER)
    for _ in range(MAX_DELIVERY_ATTEMPTS):
        store.register_failed_attempt(TENDER, "boom")

    assert store.is_new_or_changed(TENDER) is False

    store.unblock_all()
    assert store.is_new_or_changed(TENDER) is True


def test_mark_sent_persists_and_flags(tmp_path):
    """mark_sent تُدرِج الصفقة وتعلّمها في عملية واحدة."""
    store = TenderStore(db_path=str(tmp_path / "sent.db"))

    store.mark_sent(TENDER)

    row = _row(store.db_path, store._fingerprint(TENDER))
    assert row["notified"] == 1
    assert store.count() == 1


def test_fresh_database_has_delivery_columns(tmp_path):
    """قاعدة جديدة تُنشأ بالمخطط الكامل مباشرة."""
    db_path = str(tmp_path / "fresh.db")
    TenderDatabase(db_path=db_path)

    assert {"retry_count", "blocked", "last_error", "last_attempt_at"} <= _columns(db_path)
    assert TenderStore(db_path=db_path).count() == 0


# ── نقطة 6e: CLI ────────────────────────────────────────────────────────────


def test_cli_unblock_all(tmp_path, capsys):
    """--all يفك حجب كل الصفقات."""
    from storage import tools

    db_path = str(tmp_path / "cli_all.db")
    store = TenderStore(db_path=db_path)
    store.add_tender(TENDER)
    for _ in range(MAX_DELIVERY_ATTEMPTS):
        store.register_failed_attempt(TENDER, "boom")

    code = tools.main(["--db", db_path, "unblock", "--all"])

    assert code == 0
    assert "1" in capsys.readouterr().out
    assert _row(db_path, store._fingerprint(TENDER))["blocked"] == 0


def test_cli_unblock_single_fingerprint(tmp_path, capsys):
    """--fp يفك حجب صفقة واحدة فقط."""
    from storage import tools

    db_path = str(tmp_path / "cli_fp.db")
    store = TenderStore(db_path=db_path)
    store.add_tender(TENDER)
    for _ in range(MAX_DELIVERY_ATTEMPTS):
        store.register_failed_attempt(TENDER, "boom")

    code = tools.main(["--db", db_path, "unblock", "--fp", store._fingerprint(TENDER)])

    assert code == 0
    assert _row(db_path, store._fingerprint(TENDER))["blocked"] == 0


def test_cli_unblock_unknown_fingerprint_exits_two(tmp_path, capsys):
    """بصمة غير معروفة تُرجع رمز 2 بلا تغيير على البيانات."""
    from storage import tools

    db_path = str(tmp_path / "cli_miss.db")

    code = tools.main(["--db", db_path, "unblock", "--fp", "0" * 64])

    assert code == 2
    assert "لم يُعثر" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["unblock"],
        ["unblock", "--all", "--fp", "x"],
    ],
)
def test_cli_unblock_requires_exactly_one_mode(tmp_path, capsys, argv):
    """بلا --all أو --fp، أو بالاثنين معاً: خطأ استخدام بلا أي أثر."""
    from storage import tools

    db_path = str(tmp_path / "cli_bad.db")
    TenderStore(db_path=db_path)

    code = tools.main(["--db", db_path, *argv])

    assert code == 1
    assert capsys.readouterr().err


def test_cli_blocked_lists_blocked_rows(tmp_path, capsys):
    """أمر blocked يعرض الصفقات المحجوبة وسببها."""
    from storage import tools

    db_path = str(tmp_path / "cli_show.db")
    store = TenderStore(db_path=db_path)
    store.add_tender(TENDER)
    for _ in range(MAX_DELIVERY_ATTEMPTS):
        store.register_failed_attempt(TENDER, "boom")

    code = tools.main(["--db", db_path, "blocked"])

    assert code == 0
    out = capsys.readouterr().out
    assert "صفقة محجوبة" in out
    assert "boom" in out


def test_cli_blocked_on_empty_database(tmp_path, capsys):
    """قاعدة بلا محجوبات ⇒ رسالة واضحة لا جدولاً فارغاً."""
    from storage import tools

    db_path = str(tmp_path / "cli_empty.db")
    TenderStore(db_path=db_path)

    code = tools.main(["--db", db_path, "blocked"])

    assert code == 0
    assert "لا توجد صفقات محجوبة" in capsys.readouterr().out


def test_cli_defaults_to_app_config_db_path(tmp_path, monkeypatch, capsys):
    """بدون --db يُؤخذ المسار من إعداد التطبيق (DB_PATH)."""
    from storage import tools

    db_path = str(tmp_path / "cli_default.db")
    monkeypatch.setenv("DB_PATH", db_path)

    code = tools.main(["blocked"])

    assert code == 0
    assert db_path in capsys.readouterr().out


@pytest.mark.parametrize("column", ["retry_count", "blocked", "last_error", "last_attempt_at"])
def test_declared_migration_columns_cover_new_schema(column):
    """كل عمود في المخطط الجديد مذكور في عبارات الترحيل."""
    from storage.database import MIGRATION_COLUMNS

    assert any(f"ADD COLUMN {column} " in statement for statement in MIGRATION_COLUMNS)
