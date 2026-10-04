"""اختبارات المقطع الحرج الموحّد (``storage.delivery``)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

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

TENDER = {"title": "مناقصة توريد أنابيب PEHD", "organisation": "ADE", "link": "https://ade.dz/a"}
OTHER = {"title": "مناقصة حية", "organisation": "ADE", "link": "https://ade.dz/b"}


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
