"""اختبارات قفل قاعدة البيانات: حصرية حقيقية بين العمليات، لا محاكاة."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from storage.lock import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    LOCK_TIMEOUT_EXIT_CODE,
    DbLockTimeout,
    db_lock,
    lock_path_for,
    lock_timeout_seconds,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

#: يبني عملية تحتجز القفل ثم تُبلغ بموعد الالتقاط وتنتظر.
_HOLDER = """
import sys, time
from storage.lock import db_lock

db_path, hold_seconds = sys.argv[1], float(sys.argv[2])
with db_lock(db_path, timeout=5):
    print("locked", flush=True)
    time.sleep(hold_seconds)
"""


def _spawn_holder(db_path, hold_seconds: float) -> subprocess.Popen:
    """بدء عملية تحتجز القفل، وتُعاد بعد تأكيد حجزها."""
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(db_path), str(hold_seconds)],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "locked"
    return proc


def test_lock_path_appends_lock_suffix(tmp_path):
    """ملف القفل هو مسار القاعدة مع ``.lock``."""
    assert lock_path_for(tmp_path / "a.db") == f"{tmp_path / 'a.db'}.lock"


def test_lock_acquires_when_free(tmp_path):
    """القفل متاح حين لا توجد عملية أخرى."""
    with db_lock(tmp_path / "free.db", timeout=5) as held:
        assert Path(held).exists()


def test_lock_is_exclusive_across_processes(tmp_path):
    """عملية أخرى تحتجز ⇒ هذا القفل يفشل، لا يتشاركان."""
    db = tmp_path / "busy.db"
    proc = _spawn_holder(db, hold_seconds=5)
    try:
        with pytest.raises(DbLockTimeout), db_lock(db, timeout=0.5, label="unit-test"):
            pytest.fail("يجب ألا يُحجز القفل المُحجوز")
    finally:
        proc.terminate()
        proc.wait(timeout=30)


def test_lock_is_reacquired_after_holder_exits(tmp_path):
    """بعد انتهاء الحاجز السابق يُحجز القفل من جديد بلا تدخل."""
    db = tmp_path / "handover.db"
    proc = _spawn_holder(db, hold_seconds=0.2)
    proc.wait(timeout=30)

    with db_lock(db, timeout=10):
        pass


def test_lock_released_after_process_kill(tmp_path):
    """قتل الحاجز لا يترك قفلاً يتيماً — لا ``O_EXCL`` هنا."""
    db = tmp_path / "killed.db"
    proc = _spawn_holder(db, hold_seconds=120)
    proc.kill()
    proc.wait(timeout=30)

    started = time.monotonic()
    with db_lock(db, timeout=15):
        pass
    assert time.monotonic() - started < 15


def test_lock_released_after_exception(tmp_path):
    """الاستثناء داخل القفل لا يُسرّب القفل."""
    db = tmp_path / "raises.db"

    with pytest.raises(RuntimeError), db_lock(db, timeout=5):
        raise RuntimeError("boom")

    with db_lock(db, timeout=5):
        pass


def test_lock_survives_body_that_never_returns(tmp_path):
    """الخروج من السياق بالعودة المبكرة يحرّر القفل."""
    db = tmp_path / "early.db"

    def _return_early():
        with db_lock(db, timeout=5):
            return "done"

    assert _return_early() == "done"
    with db_lock(db, timeout=5):
        pass


def test_timeout_default_is_generous(monkeypatch):
    """المهلة الافتراضية أوسع من دورة كاملة بأضعاف."""
    monkeypatch.delenv("LOCK_TIMEOUT_SECONDS", raising=False)
    assert lock_timeout_seconds() == float(DEFAULT_LOCK_TIMEOUT_SECONDS)
    assert DEFAULT_LOCK_TIMEOUT_SECONDS >= 300


def test_timeout_reads_env(monkeypatch):
    """``LOCK_TIMEOUT_SECONDS`` تضبط المهلة."""
    monkeypatch.setenv("LOCK_TIMEOUT_SECONDS", "42")
    assert lock_timeout_seconds() == 42.0


def test_timeout_ignores_garbage(monkeypatch):
    """قيمة غير رقمية لا تُعطِّل التشغيل."""
    monkeypatch.setenv("LOCK_TIMEOUT_SECONDS", "soon")
    assert lock_timeout_seconds() == float(DEFAULT_LOCK_TIMEOUT_SECONDS)

    monkeypatch.setenv("LOCK_TIMEOUT_SECONDS", "0")
    assert lock_timeout_seconds() == float(DEFAULT_LOCK_TIMEOUT_SECONDS)

    monkeypatch.setenv("LOCK_TIMEOUT_SECONDS", "-5")
    assert lock_timeout_seconds() == float(DEFAULT_LOCK_TIMEOUT_SECONDS)


def test_exit_code_is_ex_tempfail():
    """رمز الخروج 75 يسمح للمجدولة بإعادة المحاولة."""
    assert LOCK_TIMEOUT_EXIT_CODE == 75


def test_two_sequential_holders_do_not_overlap(tmp_path):
    """تسلسل حاملين: الثاني ينتظر الأول ثم يدخل — لا تداخل."""
    db = tmp_path / "serial.db"
    order: list[str] = []

    with db_lock(db, timeout=5):
        order.append("first-in")
        time.sleep(0.3)
        order.append("first-out")

    with db_lock(db, timeout=5):
        order.append("second-in")

    assert order == ["first-in", "first-out", "second-in"]
