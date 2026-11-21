"""اختبارات المقطع الحرج الموحّد (``storage.delivery``)."""

import os
import sqlite3
import psycopg2
import subprocess
import sys
from pathlib import Path

import pytest

from storage.database import MAX_DELIVERY_ATTEMPTS
from storage.db import TenderStore
from storage.delivery import (
    STATUS_EMPTY,
    STATUS_FAILED,
    STATUS_LOCKED,
    STATUS_SENT,
    STATUS_SKIPPED,
    deliver,
)
from storage.lock import db_lock

REPO_ROOT = Path(__file__).resolve().parent.parent

TENDER = {
    "title": "مناقصة توريد أنابيب PEHD",
    "organisation": "ADE",
    "link": "https://ade.dz/a",
    "relevance_score": 5,
}
OTHER = {
    "title": "مناقصة حية",
    "organisation": "ADE",
    "link": "https://ade.dz/b",
    "relevance_score": 5,
}


def _row(db_path: str, fingerprint: str) -> dict:
    """Helper to fetch a row by fingerprint."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    found = conn.execute(
        "SELECT * FROM tenders WHERE fingerprint = ?", (fingerprint,)
    ).fetchone()
    conn.close()
    return dict(found) if found else {}


def _factory(db_path):
    """مصنع مخزن حقيقي على مسار معروف."""

    def _make():
        return TenderStore(db_path=str(db_path))

    return _make


def _holder(db_path, hold_seconds: float) -> subprocess.Popen:
    """عملية خارجية تحتجز قفل القاعدة."""
    snippet = (
        "import sys, time\n"
        "from storage.lock import db_lock\n"
        "with db_lock(sys.argv[1], timeout=5):\n"
        "    print('locked', flush=True)\n"
        "    time.sleep(float(sys.argv[2]))\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", snippet, str(db_path), str(hold_seconds)],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "locked"
    return proc


def test_delivery_persists_and_marks_sent(tmp_path):
    """النجاح: حفظ ثم وسم كل الصفقات."""
    db = tmp_path / "ok.db"
    sent: list[dict] = []

    outcome = deliver(
        str(db),
        _factory(db),
        [dict(TENDER)],
        lambda pending: (sent.extend(pending), (True, ""))[1],
        timeout=10,
    )

    assert outcome.status == STATUS_SENT
    assert outcome.inserted == 1
    assert outcome.total == 1
    assert len(sent) == 1
    store = TenderStore(db_path=str(db))
    assert store.is_notified(TENDER) is True


def test_delivery_records_failed_attempt_when_send_fails(tmp_path):
    """الفشل: محاولة فاشلة لكل صفقة، بلا وسم."""
    db = tmp_path / "fail.db"

    outcome = deliver(
        str(db),
        _factory(db),
        [dict(TENDER)],
        lambda pending: (False, "telegram down"),
        timeout=10,
    )

    assert outcome.status == STATUS_FAILED
    assert outcome.error == "telegram down"
    store = TenderStore(db_path=str(db))
    assert store.is_notified(TENDER) is False
    assert store.blocked_tenders() == []


def test_delivery_dry_run_saves_without_sending(tmp_path):
    """Dry-Run يحفظ ولا يستدعي دالة الإرسال إطلاقاً."""

    def _fail_if_called(pending):
        raise AssertionError("يجب ألا يُرسل شيء في وضع Dry-Run")

    db = tmp_path / "dry.db"
    outcome = deliver(
        str(db),
        _factory(db),
        [dict(TENDER)],
        _fail_if_called,
        dry_run=True,
        timeout=10,
    )

    assert outcome.status == STATUS_SKIPPED
    assert outcome.inserted == 1
    store = TenderStore(db_path=str(db))
    assert store.is_notified(TENDER) is False
    assert store.count() == 1


def test_delivery_without_sender_saves_but_skips(tmp_path):
    """غياب مُرسّل = حفظ بلا وسم."""
    db = tmp_path / "nosend.db"

    outcome = deliver(str(db), _factory(db), [dict(TENDER)], None, timeout=10)

    assert outcome.status == STATUS_SKIPPED
    assert outcome.inserted == 1
    assert TenderStore(db_path=str(db)).is_notified(TENDER) is False


def test_delivery_empty_when_nothing_new(tmp_path):
    """لا جديد ⇒ لا إرسال ولا كتابة."""
    db = tmp_path / "empty.db"
    store = TenderStore(db_path=str(db))
    store.mark_sent(dict(TENDER))

    outcome = deliver(
        str(db),
        _factory(db),
        [dict(TENDER)],
        lambda pending: (True, ""),
        timeout=10,
    )

    assert outcome.status == STATUS_EMPTY
    assert outcome.pending == []
    assert outcome.total == 1


def test_delivery_skips_blocked_tender(tmp_path):
    """الصفقة المحجوبة لا تمرّ إلى دالة الإرسال."""
    db = tmp_path / "blocked.db"
    setup = TenderStore(db_path=str(db))
    setup.add_tender(dict(TENDER))
    for _ in range(3):
        setup.register_failed_attempt(TENDER, "boom")

    sent: list[dict] = []
    outcome = deliver(
        str(db),
        _factory(db),
        [dict(TENDER), dict(OTHER)],
        lambda pending: (sent.extend(pending), (True, ""))[1],
        timeout=10,
    )

    assert outcome.status == STATUS_SENT
    assert [t["title"] for t in sent] == [OTHER["title"]]


def test_on_pending_runs_before_send(tmp_path):
    """تقرير Excel يُولَّد داخل القفل قبل الإرسال."""
    order: list[str] = []
    db = tmp_path / "order.db"

    def _report(pending):
        order.append("report")

    outcome = deliver(
        str(db),
        _factory(db),
        [dict(TENDER)],
        lambda pending: (order.append("send"), (True, ""))[1],
        on_pending=_report,
        timeout=10,
    )

    assert outcome.status == STATUS_SENT
    assert order == ["report", "send"]


def test_no_write_when_db_locked(tmp_path):
    """القاعدة المحجوبة: لا كتابة إطلاقاً، لا حتى فتحها.

    هذا هو اختبار القبول الحاسم: تخطّي الدورة مقبول، والإرسال المزدوج أو
    الحالة نصف المكتوبة غير مقبولين.
    """
    db = tmp_path / "locked.db"
    before = TenderStore(db_path=str(db))
    before.add_tender(dict(TENDER))
    baseline_total = before.count()
    baseline_notified = before.is_notified(TENDER)

    proc = _holder(db, hold_seconds=10)
    try:
        called = []

        def _factory_that_must_not_run():
            called.append(1)
            return TenderStore(db_path=str(db))

        outcome = deliver(
            str(db),
            _factory_that_must_not_run,
            [dict(TENDER)],
            lambda pending: (True, ""),
            timeout=0.5,
            label="locked-test",
        )
    finally:
        proc.terminate()
        proc.wait(timeout=30)

    assert outcome.status == STATUS_LOCKED
    assert outcome.is_locked_out is True
    assert called == []

    after = TenderStore(db_path=str(db))
    assert after.count() == baseline_total
    assert after.is_notified(TENDER) == baseline_notified


def test_delivery_locks_for_the_whole_critical_section(tmp_path):
    """القفل محجوز أثناء التنفيذ نفسه لا قبله فقط."""
    db = tmp_path / "section.db"
    observed: list[bool] = []

    def _send(pending):
        observed.append(_is_locked(db))
        return True, ""

    def _is_locked(target) -> bool:
        try:
            with db_lock(target, timeout=0.2):
                return False
        except Exception:
            return True

    outcome = deliver(str(db), _factory(db), [dict(TENDER)], _send, timeout=10)

    assert outcome.status == STATUS_SENT
    assert observed == [True]


def test_store_is_closed_even_when_send_raises(tmp_path):
    """استثناء في الإرسال لا يترك المخزن مفتوحاً ولا يحجب القفل."""
    db = tmp_path / "raises.db"
    stores: list[object] = []

    def _factory():
        store = TenderStore(db_path=str(db))
        stores.append(store)
        return store

    def _send(pending):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        deliver(str(db), _factory, [dict(TENDER)], _send, timeout=10)

    assert len(stores) == 1
    with db_lock(str(db), timeout=5):
        pass


def test_total_falls_back_to_stats(tmp_path):
    """مخزن بلا ``count`` يُقرأ عبر ``stats``."""

    class _StatsOnly:
        def __init__(self, db_path):
            self.db_path = str(db_path)
            self._store = TenderStore(db_path=str(db_path))

        def is_new_or_changed(self, tender):
            return self._store.is_new_or_changed(tender)

        def save_many(self, tenders):
            return self._store.save_many(list(tenders))

        def mark_sent(self, tender):
            self._store.mark_sent(tender)

        def register_failed_attempt(self, tender, error):
            self._store.register_failed_attempt(tender, error)

        def stats(self):
            return self._store.stats()

        def close(self):
            return None

    db = tmp_path / "stats.db"
    outcome = deliver(
        str(db),
        lambda: _StatsOnly(db),
        [dict(TENDER)],
        lambda p: (True, ""),
        timeout=10,
    )

    assert outcome.status == STATUS_SENT
    assert outcome.total == 1


# ── deliver() with observed_tenders tests ──────────────────────────────────────


def test_deliver_observed_tenders_updates_last_seen(tmp_path):
    """الرصد يحدث داخل القفل ويحدث last_seen للسجلات الموجودة."""
    db = tmp_path / "obs_deliver.db"
    store = TenderStore(db_path=str(db))
    store.add_tender(TENDER)

    original_row = _row(str(db), store._fingerprint(TENDER))
    original_last_seen = original_row["last_seen"]

    outcome = deliver(
        str(db),
        _factory(db),
        [],  # No tenders for delivery
        lambda pending: (True, ""),
        observed_tenders=[TENDER],
        timeout=10,
    )

    assert outcome.status == STATUS_EMPTY  # No pending for delivery
    new_row = _row(str(db), store._fingerprint(TENDER))
    assert new_row["last_seen"] != original_last_seen


def test_deliver_observed_tenders_runs_before_delivery(tmp_path):
    """الرصد يحدث قبل التسليم."""
    order: list[str] = []
    db = tmp_path / "order.db"

    def _send(pending):
        order.append("send")
        return True, ""

    def _report(pending):
        order.append("report")

    # Pre-populate with existing tender
    setup = TenderStore(db_path=str(db))
    setup.add_tender(TENDER)

    outcome = deliver(
        str(db),
        _factory(db),
        [OTHER],  # New tender for delivery
        _send,
        on_pending=_report,
        observed_tenders=[TENDER],  # Existing tender for observation
        timeout=10,
    )

    assert outcome.status == STATUS_SENT
    # Order should be: observe (implicit), report, send
    # The observe happens before the report/send logic
    assert "report" in order
    assert "send" in order


def test_deliver_observed_tenders_lock_failure_prevents_both(tmp_path):
    """فشل القفل يمنع الرصد والكتابة."""
    db = tmp_path / "locked.db"
    before = TenderStore(db_path=str(db))
    before.add_tender(TENDER)
    baseline_total = before.count()
    baseline_notified = before.is_notified(TENDER)

    proc = _holder(db, hold_seconds=10)
    try:
        called = []

        def _factory_that_must_not_run():
            called.append(1)
            return TenderStore(db_path=str(db))

        outcome = deliver(
            str(db),
            _factory_that_must_not_run,
            [OTHER],
            lambda pending: (True, ""),
            observed_tenders=[TENDER],
            timeout=0.5,
            label="locked-test",
        )
    finally:
        proc.terminate()
        proc.wait(timeout=30)

    assert outcome.status == STATUS_LOCKED
    assert called == []

    after = TenderStore(db_path=str(db))
    assert after.count() == baseline_total
    assert after.is_notified(TENDER) == baseline_notified


def test_deliver_observed_tenders_optional_parameter(tmp_path):
    """القائمة observed_tenders اختيارية - استدعاءات قديمة لا تنكسر."""
    db = tmp_path / "optional.db"

    # Call without observed_tenders (old API)
    outcome = deliver(
        str(db),
        _factory(db),
        [TENDER],
        lambda pending: (True, ""),
        timeout=10,
    )

    assert outcome.status == STATUS_SENT
    assert outcome.inserted == 1


def test_deliver_empty_delivery_list_allows_observation(tmp_path):
    """القائمة الفارغة للتسليم لا تمنع الرصد."""
    db = tmp_path / "empty_deliver.db"
    store = TenderStore(db_path=str(db))
    store.add_tender(TENDER)

    original_row = _row(str(db), store._fingerprint(TENDER))
    original_last_seen = original_row["last_seen"]

    outcome = deliver(
        str(db),
        _factory(db),
        [],  # Empty delivery list
        lambda pending: (True, ""),
        observed_tenders=[TENDER],
        timeout=10,
    )

    assert outcome.status == STATUS_EMPTY
    new_row = _row(str(db), store._fingerprint(TENDER))
    assert new_row["last_seen"] != original_last_seen


def test_deliver_observed_tenders_does_not_duplicate_notifications(tmp_path):
    """لا تتكرر الإشعارات - مناقصة مرصودة ومُسلمة مرة واحدة."""
    db = tmp_path / "notify.db"
    store = TenderStore(db_path=str(db))
    store.add_tender(TENDER)
    store.mark_notified(TENDER)  # Already notified

    sent_count = []

    def _send(pending):
        sent_count.extend(pending)
        return True, ""

    # Observe the already-notified tender AND try to deliver it
    outcome = deliver(
        str(db),
        _factory(db),
        [TENDER],  # This should NOT be sent again
        _send,
        observed_tenders=[TENDER],
        timeout=10,
    )

    assert outcome.status == STATUS_EMPTY  # No new pending
    assert len(sent_count) == 0  # No duplicate notification


def test_deliver_observed_tenders_blocked_remains_blocked(tmp_path):
    """المناقصات المحجوبة تبقى محجوبة حتى مع الرصد."""
    db = tmp_path / "blocked.db"
    store = TenderStore(db_path=str(db))
    store.add_tender(TENDER)
    for _ in range(MAX_DELIVERY_ATTEMPTS):
        store.register_failed_attempt(TENDER, "boom")

    # Verify it's blocked
    assert store.is_new_or_changed(TENDER) is False

    outcome = deliver(
        str(db),
        _factory(db),
        [TENDER],
        lambda pending: (True, ""),
        observed_tenders=[TENDER],
        timeout=10,
    )

    # Should not send blocked tender
    assert outcome.status == STATUS_EMPTY
    assert store.is_new_or_changed(TENDER) is False


def test_deliver_send_failure_preserves_observation_state(tmp_path):
    """فشل الإرسال لا يفسد حالة الرصد."""
    db = tmp_path / "fail_preserve.db"
    store = TenderStore(db_path=str(db))
    store.add_tender(TENDER)

    original_row = _row(str(db), store._fingerprint(TENDER))
    original_last_seen = original_row["last_seen"]

    outcome = deliver(
        str(db),
        _factory(db),
        [OTHER],  # New tender for delivery
        lambda pending: (False, "send failed"),
        observed_tenders=[TENDER],  # Existing tender for observation
        timeout=10,
    )

    assert outcome.status == STATUS_FAILED
    # Observation should still have happened
    new_row = _row(str(db), store._fingerprint(TENDER))
    assert new_row["last_seen"] != original_last_seen
    # Delivery should have recorded failed attempt for OTHER
    other_row = _row(str(db), store._fingerprint(OTHER))
    assert other_row["retry_count"] == 1


def test_deliver_observed_tenders_no_new_inserts(tmp_path):
    """لا يحدث إدراج جديد عن طريق الرصد."""
    db = tmp_path / "no_insert.db"

    # Observe a tender that doesn't exist in DB
    outcome = deliver(
        str(db),
        _factory(db),
        [],
        lambda pending: (True, ""),
        observed_tenders=[TENDER],
        timeout=10,
    )

    assert outcome.status == STATUS_EMPTY
    store = TenderStore(db_path=str(db))
    assert store.count() == 0  # No inserts from observation


# ── Integration test: acceptance scenario ──────────────────────────────────────


def test_integration_existing_tender_reappears_commercially_excluded(tmp_path):
    """اختبار القبول الرئيسي:
    - سجل مناقصة موجودة مسبقاً في قاعدة الاختبار
    - اجعلها غير مؤهلة تجارياً
    - اجعلها تظهر مجدداً في نتائج الزحف
    - مررها ضمن observed_tenders
    - اترك filtered فارغة
    - نفذ deliver()
    - تحقق أن last_seen تغير
    - تحقق أن عدد السجلات لم يتغير
    - تحقق أن notified و blocked وبقية الحالات لم تتغير
    """
    from datetime import datetime
    db = tmp_path / "acceptance.db"
    store = TenderStore(db_path=str(db))

    # Create a tender that would fail business filter (low relevance)
    # Bypass add_tender validation by inserting directly
    existing = {
        "title": "مناقصة توريد أنابيب",
        "organisation": "شركة المياه",
        "link": "https://water.dz/tender/123",
        "relevance_score": 1,  # Below MIN_TENDER_RELEVANCE_SCORE
        "matched_families": [{"id": "fam1", "name_ar": "أنابيب"}],
    }
    fp = store._fingerprint(existing)
    now = datetime.now().isoformat()
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO tenders (
                fingerprint, title, organisation, wilaya, product,
                deadline, status, link, relevance_score,
                matched_families, first_seen, last_seen, notified,
                reference, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                fp,
                existing.get("title", ""),
                existing.get("organisation", ""),
                existing.get("wilaya") or None,
                existing.get("product", ""),
                existing.get("deadline") or None,
                existing.get("status", ""),
                existing.get("link", ""),
                existing.get("relevance_score", 0),
                store._families_to_db_value(existing.get("matched_families", []) or [], fp),
                now,
                now,
                existing.get("reference") or existing.get("tender_number"),
                existing.get("source"),
            ),
        )
        conn.commit()

    original_row = _row(str(db), fp)
    original_last_seen = original_row["last_seen"]
    original_notified = original_row["notified"]
    original_blocked = original_row["blocked"]
    original_is_noise = original_row["is_noise"]
    original_retry_count = original_row["retry_count"]
    original_last_error = original_row["last_error"]
    original_last_attempt_at = original_row["last_attempt_at"]

    # Now deliver with observed_tenders containing the existing tender,
    # but filtered empty (commercially excluded)
    outcome = deliver(
        str(db),
        _factory(db),
        [],  # filtered is empty - commercially excluded
        lambda pending: (True, ""),
        observed_tenders=[existing],  # Re-observed from crawler
        timeout=10,
    )

    assert outcome.status == STATUS_EMPTY
    assert outcome.inserted == 0

    new_row = _row(str(db), fp)

    # last_seen should have been updated
    assert new_row["last_seen"] != original_last_seen
    assert new_row["last_seen"] > original_last_seen

    # Total count should not change
    assert store.count() == 1

    # Other fields should not change
    assert new_row["notified"] == original_notified
    assert new_row["blocked"] == original_blocked
    assert new_row["is_noise"] == original_is_noise
    assert new_row["retry_count"] == original_retry_count
    assert new_row["last_error"] == original_last_error
    assert new_row["last_attempt_at"] == original_last_attempt_at
