"""اختبارات قبول W7: القفل على مستوى نقاط الدخول لا على مستوى الوحدة فقط."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import main
import run_smart_scraper
import storage.delivery
import storage.tools
import test_run
from storage.lock import LOCK_TIMEOUT_EXIT_CODE

REPO_ROOT = Path(__file__).resolve().parent.parent

TENDER = {
    "title": "مناقصة توريد أنابيب PEHD",
    "link": "https://ade.dz/a",
    "organisation": "ADE",
}


def _hold_lock(db_path, hold_seconds: float) -> subprocess.Popen:
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


class _RecordingStore:
    """مخزن يسجّل استدعاءاته ويكتب على قاعدة حقيقية في مسار معروف."""

    instances: list["_RecordingStore"] = []

    def __init__(self, db_path=None):
        from storage.db import TenderStore

        self.db_path = db_path
        self._store = TenderStore(db_path=db_path)
        _RecordingStore.instances.append(self)

    def __getattr__(self, name):
        return getattr(self._store, name)

    def close(self):
        return None


def test_all_entrypoints_use_shared_deliver():
    """كل نقطة دخول تمرّ بالمعاملة نفسها، لا بنسخة منها.

    هذا هو حارس ضد عودة العلة الأصلية: نسختان أو ثلاث من منطق التسليم
    تعني أن أحدها قد يفلت من القفل لاحقاً.
    """
    assert main.deliver is storage.delivery.deliver
    assert run_smart_scraper.deliver is storage.delivery.deliver
    assert test_run.deliver is storage.delivery.deliver


def test_admin_tools_share_the_same_lock_primitive():
    """الأوامر الإدارية تستعمل القفل نفسه، لا نسخة منه.

    ``storage.tools`` لا يمرّ بـ ``deliver`` لأنه لا يُرسل، لكنه يشترك في
    القفل نفسه حتى لا يفكّح أمرٌ إداريٌّ على دورة جارية.
    """
    assert storage.tools.db_lock is storage.delivery.db_lock
    assert storage.tools.DbLockTimeout is storage.delivery.DbLockTimeout


def test_main_exits_75_and_writes_nothing_when_db_locked(tmp_path, monkeypatch):
    """``main.run()`` يخرج بـ75 ولا ينشئ المخزن أصلاً حين تكون القاعدة محجوبة."""
    db_path = tmp_path / "main.db"
    _RecordingStore.instances.clear()
    monkeypatch.setenv("LOCK_TIMEOUT_SECONDS", "0.5")

    from config import AppConfig

    config = AppConfig(dry_run=False, db_path=str(db_path))
    monkeypatch.setattr(
        main.AppConfig, "from_env", classmethod(lambda cls, load_env_file=True: config)
    )
    monkeypatch.setattr(main, "TenderStore", _RecordingStore)
    monkeypatch.setattr(main, "scrape_all_sources", lambda: [dict(TENDER)])
    monkeypatch.setattr(main, "apply_filter", lambda tenders: list(tenders))
    monkeypatch.setattr(main, "build_excel_report", lambda tenders: "report.xlsx")
    monkeypatch.setattr(main, "setup_logging", lambda level: None)
    monkeypatch.setattr(main, "build_notifier", lambda cfg: None)

    proc = _hold_lock(db_path, hold_seconds=10)
    try:
        with pytest.raises(SystemExit) as excinfo:
            main.run()
    finally:
        proc.terminate()
        proc.wait(timeout=30)

    assert excinfo.value.code == LOCK_TIMEOUT_EXIT_CODE
    assert _RecordingStore.instances == []
    assert not db_path.exists()


def test_main_persists_in_dry_run_while_holding_lock(tmp_path, monkeypatch):
    """Dry-Run يحفظ داخل القفل ولا يرسل شيئاً."""
    db_path = tmp_path / "dry.db"
    _RecordingStore.instances.clear()

    from config import AppConfig

    config = AppConfig(dry_run=True, db_path=str(db_path))
    monkeypatch.setattr(
        main.AppConfig, "from_env", classmethod(lambda cls, load_env_file=True: config)
    )
    monkeypatch.setattr(main, "TenderStore", _RecordingStore)
    monkeypatch.setattr(main, "scrape_all_sources", lambda: [dict(TENDER)])
    monkeypatch.setattr(main, "apply_filter", lambda tenders: list(tenders))
    monkeypatch.setattr(main, "build_excel_report", lambda tenders: "report.xlsx")
    monkeypatch.setattr(main, "setup_logging", lambda level: None)
    monkeypatch.setattr(main, "build_notifier", lambda cfg: pytest.fail("Dry-Run لا يبني مُرسّلاً"))

    main.run()

    store = _RecordingStore.instances[0]
    assert store.is_notified(TENDER) is False
    assert store.count() == 1


def test_tools_cli_returns_75_when_db_locked(tmp_path, monkeypatch):
    """الأمر الإداري لا يكتب فوق دورة جارية، ويخرج بـ75."""
    db_path = tmp_path / "tools.db"
    monkeypatch.setenv("LOCK_TIMEOUT_SECONDS", "0.5")

    proc = _hold_lock(db_path, hold_seconds=10)
    try:
        code = storage.tools.main(["--db", str(db_path), "unblock", "--all"])
    finally:
        proc.terminate()
        proc.wait(timeout=30)

    assert code == LOCK_TIMEOUT_EXIT_CODE
    assert not db_path.exists()


def test_lock_file_is_not_tracked_in_git():
    """ملف القفل مُتجاهَل حتى لا يفسد حالة المستودع."""
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "*.lock" in ignored
