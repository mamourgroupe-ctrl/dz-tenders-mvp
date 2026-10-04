"""اختبارات سكربت الفحص ``test_run.py`` — المسار الذي تشغّله المهمة المجدولة."""

import importlib
import os

import pytest

import test_run

TENDER = {
    "title": "مناقصة توريد أنابيب PEHD",
    "link": "https://ade.dz/a",
    "organisation": "ADE",
}


class _FakeCrawler:
    """كرولر وهمي بلا شبكة."""

    def __init__(self, *args, **kwargs):
        self.name = type(self).__name__

    def run(self):
        return [dict(TENDER)]


class _ExplodingNotifier:
    """لو بُني مُرسّل في وضع Dry-Run فسنعرف فوراً."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("وضع Dry-Run لا يجوز أن يبني مُرسّلاً")


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """يعزل السكربت عن الشبكة ومن مجلد العمل ومن ملف CI."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(test_run, "ADECrawler", _FakeCrawler)
    monkeypatch.setattr(test_run, "ONACrawler", _FakeCrawler)
    monkeypatch.setattr(test_run, "AlgeriaTendersCrawler", _FakeCrawler)
    monkeypatch.setattr(test_run, "MarchesPublicsCrawler", _FakeCrawler)
    monkeypatch.setattr(test_run, "TelegramNotifier", _ExplodingNotifier)
    monkeypatch.setattr(
        test_run,
        "TenderFilter",
        lambda: type(
            "F",
            (),
            {
                "filter_tenders": lambda self, tenders: list(tenders),
                "summary": lambda self, t: {"total_filtered": len(t)},
            },
        )(),
    )
    return tmp_path


def test_module_is_importable_without_credentials(monkeypatch):
    """استيراد السكربت لا يُنشئ استثناءً ولا يقرأ البيئة.

    كان الفحص سابقاً يرفع ``ValueError`` وقت الاستيراد، فصار غير قابل
        للاختبار ولا يمكن تشغيله في وضع Dry-Run بلا أسرار. كما كان يستدعي
        ``load_dotenv`` ويثبّت بيانات تلغرام كثوابت عند الاستيراد، فيلوّث
        بيئ أي اختبار آخر يستورده.
    """
    monkeypatch.setattr(test_run, "_credentials", lambda: (None, None, None))

    assert test_run._build_parser().parse_args(["--dry-run"]).dry_run is True


def test_import_has_no_env_side_effect(monkeypatch):
    """إعادة استيراد الوحدة لا تُحمّل ``.env`` ولا تفرض ثوابت بيئة.

    حارس ضد عودة العلة: ``load_dotenv`` عند الاستيراد كان يلوّث بيئ أي
    اختبار يستورد هذه الوحدة، وبيانات تلغرام كانت تُلتقط قبل التحميل.
    """
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    importlib.reload(test_run)

    assert "TELEGRAM_BOT_TOKEN" not in os.environ
    assert not hasattr(test_run, "TELEGRAM_BOT_TOKEN")
    assert not hasattr(test_run, "TELEGRAM_CHAT_ID")


def test_credentials_are_read_at_call_time(monkeypatch):
    """بيانات تلغرام تُقرأ عند النداء لا عند الاستيراد."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    assert test_run._credentials()[0] is None

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "late-bound-token")
    assert test_run._credentials()[0] == "late-bound-token"


def test_dry_run_persists_without_sending(isolated, monkeypatch, capsys):
    """Dry-Run يحفظ الصفقات ويكتب التقارير ولا يبني مُرسّلاً."""
    from storage.db import TenderStore

    db = isolated / "ci.db"
    monkeypatch.setattr(test_run, "resolve_db_path", lambda *a: str(db))

    test_run.main(["--dry-run", "--db", str(db)])

    store = TenderStore(db_path=str(db))
    assert store.count() == 1
    assert store.is_notified(TENDER) is False

    assert (isolated / "tenders_results.json").exists()
    assert (isolated / "tenders_results.xlsx").exists()
    assert "DRY-RUN" in capsys.readouterr().out


def test_dry_run_needs_no_credentials(isolated, monkeypatch):
    """Dry-Run يعمل بلا أي متغير بيئة."""
    monkeypatch.setattr(test_run, "_credentials", lambda: (None, None, None))
    db = isolated / "ci2.db"

    test_run.main(["--dry-run", "--db", str(db)])

    assert db.exists()


def test_send_mode_requires_credentials(isolated, monkeypatch):
    """دون Dry-Run، غياب التوكن يبقى خطأ صريحاً."""
    monkeypatch.setattr(test_run, "_credentials", lambda: (None, None, None))

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        test_run.main(["--db", str(isolated / "ci3.db")])


def test_second_cycle_reports_nothing_new(isolated, monkeypatch):
    """الدورة الثانية لا ترى جديداً — لا فيض إشعارات."""
    from storage.db import TenderStore

    db = isolated / "ci4.db"
    monkeypatch.setattr(test_run, "resolve_db_path", lambda *a: str(db))

    test_run.main(["--dry-run", "--db", str(db)])
    test_run.main(["--dry-run", "--db", str(db)])

    store = TenderStore(db_path=str(db))
    assert store.count() == 1
