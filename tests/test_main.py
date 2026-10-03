import sys
from unittest.mock import patch

import pytest

import main
from config import AppConfig
from crawlers.algeria_tenders_crawler import AlgeriaTendersCrawler
from crawlers.marches_publics_crawler import MarchesPublicsCrawler
from crawlers.ona_crawler import ONACrawler
from main import apply_filter, build_notifier, build_summary_message, drop_reference_data

LIVE_TENDER = {"title": "مناقصة توريد أنابيب PEHD", "link": "https://ade.dz/a"}


class FakeStore:
    """بديل خفيف لقاعدة البيانات يمنع أي كتابة على القرص أثناء الاختبار."""

    instances: list["FakeStore"] = []

    def __init__(self, db_path=None):
        self.db_path = db_path
        self.marked: list[dict] = []
        self.saved: list[dict] = []
        self.failed: list[dict] = []
        self.failed_attempt_error = ""
        self.closed = False
        FakeStore.instances.append(self)

    def is_new_or_changed(self, tender):
        return True

    def count(self):
        return len(self.saved)

    def save_many(self, tenders):
        self.saved.extend(tenders)
        return len(tenders)

    def mark_notified(self, tender):
        self.marked.append(tender)

    def mark_sent(self, tender):
        self.marked.append(tender)

    def register_failed_attempt(self, tender, error=""):
        self.failed.append(tender)
        self.failed_attempt_error = error
        return len(self.failed)

    def close(self):
        self.closed = True


def _patch_run(monkeypatch, config: AppConfig):
    """يثبّت خط التشغيل بلا شبكة ولا ملف Excel."""
    FakeStore.instances.clear()
    monkeypatch.setattr(
        main.AppConfig, "from_env", classmethod(lambda cls, load_env_file=True: config)
    )
    monkeypatch.setattr(main, "TenderStore", FakeStore)
    monkeypatch.setattr(main, "scrape_all_sources", lambda: [dict(LIVE_TENDER)])
    monkeypatch.setattr(main, "apply_filter", lambda tenders: list(tenders))
    monkeypatch.setattr(main, "build_excel_report", lambda tenders: "report.xlsx")
    monkeypatch.setattr(main, "setup_logging", lambda level: None)


def test_apply_filter():
    """اختبار دالة apply_filter للتأكد من استدعاء TenderFilter بشكل صحيح وإرجاع النتائج المفلترة."""
    sample_tenders = [{"title": "مناقصة توريد أنابيب PEHD"}]
    expected_filtered = [{"title": "مناقصة توريد أنابيب PEHD", "score": 5}]

    with patch("main.TenderFilter") as mock_tender_filter_cls:
        mock_instance = mock_tender_filter_cls.return_value
        mock_instance.filter_tenders.return_value = expected_filtered

        result = apply_filter(sample_tenders)

        mock_tender_filter_cls.assert_called_once()
        mock_instance.filter_tenders.assert_called_once_with(sample_tenders)
        assert result == expected_filtered


def test_apply_filter_empty_list():
    """اختبار دالة apply_filter عند تمرير قائمة مناقصات فارغة."""
    empty_tenders = []

    with patch("main.TenderFilter") as mock_tender_filter_cls:
        mock_instance = mock_tender_filter_cls.return_value
        mock_instance.filter_tenders.return_value = []

        result = apply_filter(empty_tenders)

        mock_tender_filter_cls.assert_called_once()
        mock_instance.filter_tenders.assert_called_once_with(empty_tenders)
        assert result == []


def test_apply_filter_no_matches():
    """اختبار دالة apply_filter عندما لا تطابق أي مناقصة معايير الفلترة."""
    unmatched_tenders = [{"title": "مناقصة صيانة سيارات غير مستهدفة"}]

    with patch("main.TenderFilter") as mock_tender_filter_cls:
        mock_instance = mock_tender_filter_cls.return_value
        mock_instance.filter_tenders.return_value = []

        result = apply_filter(unmatched_tenders)

        mock_tender_filter_cls.assert_called_once()
        mock_instance.filter_tenders.assert_called_once_with(unmatched_tenders)
        assert result == []


def test_build_summary_message_counts_tenders_and_families():
    """اختبار تعداد المناقصات وتوزيعها على العائلات."""
    tenders = [
        {
            "title": "مناقصة توريد أنابيب PEHD",
            "matched_families": [{"name_ar": "مواد البناء"}],
        },
        {
            "title": "مناقصة صيانة طرق",
            "matched_families": [{"name_ar": "البنية التحتية"}, {"name_ar": "مواد البناء"}],
        },
    ]

    result = build_summary_message(tenders)

    assert "🔔 <b>تقرير DZ-TENDERS</b>" in result
    assert "📋 2 مناقصة جديدة:" in result
    assert "• مواد البناء: 2" in result
    assert "• البنية التحتية: 1" in result


def test_build_summary_message_sorts_families_by_count_desc():
    """اختبار ترتيب العائلات تنازليًا حسب عدد المطابقات."""
    tenders = [
        {"title": "أ", "matched_families": [{"name_ar": "أولى"}, {"name_ar": "ثالثة"}]},
        {"title": "ب", "matched_families": [{"name_ar": "ثالثة"}]},
    ]

    result = build_summary_message(tenders)
    lines = result.splitlines()
    first_family_line = next(i for i, line in enumerate(lines) if line.startswith("• "))
    family_lines = [line for line in lines[first_family_line:] if line.startswith("• ")]

    assert family_lines == ["• ثالثة: 2", "• أولى: 1"]


def test_build_summary_message_uses_fallback_family_name():
    """اختبار اسم العائلة الافتراضي عند غياب name_ar."""
    tenders = [{"title": "مناقصة", "matched_families": [{"code": "X1"}]}]

    result = build_summary_message(tenders)

    assert "• غير مصنّف: 1" in result


def test_build_summary_message_lists_at_most_five_titles():
    """اختبار اقتصار قائمة العناوين على أول 5 مناقصات."""
    tenders = [{"title": f"مناقصة رقم {i}"} for i in range(1, 8)]

    result = build_summary_message(tenders)
    lines = result.splitlines()
    separator_index = next(i for i, line in enumerate(lines) if "━" in line)
    numbered = [line for line in lines[separator_index + 1 :] if line[:2].rstrip(".").isdigit()]

    assert len(numbered) == 5
    assert numbered[0] == "1. مناقصة رقم 1"
    assert numbered[-1] == "5. مناقصة رقم 5"
    assert "مناقصة رقم 6" not in result


def test_build_summary_message_truncates_long_title():
    """اختبار اقتصاص العنوان عند تجاوزه 80 حرفًا."""
    long_title = "ط" * 120
    tenders = [{"title": long_title}]

    result = build_summary_message(tenders)

    assert f"1. {'ط' * 80}" in result
    assert f"1. {'ط' * 81}" not in result


def test_build_summary_message_handles_missing_title_and_key():
    """اختبار التعامل مع مناقصة بلا عنوان أو بلا مفتاح matched_families."""
    tenders = [{}, {"title": "مناقصة صيانة"}]

    result = build_summary_message(tenders)

    assert "📋 2 مناقصة جديدة:" in result
    assert "1. بدون عنوان" in result
    assert "2. مناقصة صيانة" in result
    assert "• " not in result


def test_build_summary_message_empty_list():
    """اختبار توليد التقرير عند عدم وجود مناقصات جديدة."""
    result = build_summary_message([])

    assert "📋 0 مناقصة جديدة:" in result
    assert "\n━━━━━━━━━━━━━━━━━━" in result
    assert result.strip().endswith("━━━━━━━━━━━━━━━━━━")


def test_drop_reference_data_removes_samples_by_default():
    """البيانات المرجعية تُحذف افتراضياً حتى لا تُبلَّغ كصفقات حقيقية."""
    tenders = [
        {"title": "حية", "is_sample": False},
        {"title": "مرجعية", "is_sample": True, "source_status": "reference"},
        {"title": "بلا وسم"},
    ]

    result = drop_reference_data(tenders)

    assert [t["title"] for t in result] == ["حية", "بلا وسم"]


def test_drop_reference_data_keeps_samples_when_explicitly_enabled():
    """تضمين البيانات المرجعية ممكن عبر include_samples صراحةً."""
    tenders = [{"title": "مرجعية", "is_sample": True}]

    assert drop_reference_data(tenders, include_samples=True) == tenders


def test_drop_reference_data_does_not_mutate_input():
    """الدالة لا تعدّل القائمة الأصلية."""
    tenders = [{"title": "مرجعية", "is_sample": True}]

    drop_reference_data(tenders)

    assert tenders == [{"title": "مرجعية", "is_sample": True}]


def test_reference_tenders_are_flagged(monkeypatch):
    """كل البيانات المرجعية في الزواحف موسومة is_sample و source_status."""
    ona = ONACrawler()
    monkeypatch.setattr(ona, "fetch_page", lambda url: "<html></html>")
    algeria = AlgeriaTendersCrawler()
    monkeypatch.setattr(algeria, "fetch_page", lambda url: "<html></html>")

    batches = [
        ona.run(),
        algeria.run(),
        MarchesPublicsCrawler().run(),
    ]

    assert batches[0] and batches[1] and batches[2]
    for tender in [t for batch in batches for t in batch]:
        assert tender["is_sample"] is True, tender["title"]
        assert tender["source_status"] == "reference", tender["title"]


def test_is_sample_flag_survives_filtering():
    """وسم البيانات المرجعية ينجو من مرحلة الفلترة قبل الوصول إلى التنبيه."""
    samples = [
        {
            "title": "Acquisition de tuyaux PVC assainissement CR8 DN 200/315",
            "is_sample": True,
        }
    ]

    filtered = apply_filter(samples)

    assert len(filtered) == 1
    assert filtered[0]["is_sample"] is True
    assert "relevance_score" in filtered[0]


def test_build_notifier_returns_none_without_token():
    """غياب التوكن يعيد None بدل KeyError."""
    config = AppConfig(dry_run=False, telegram_bot_token=None, telegram_chat_id="123")

    assert build_notifier(config) is None


def test_build_notifier_returns_none_without_chat_id():
    """غياب معرّف المحادثة يعيد None أيضاً."""
    config = AppConfig(dry_run=False, telegram_bot_token="123:ABC", telegram_chat_id=None)

    assert build_notifier(config) is None


def test_build_notifier_returns_manager_when_configured():
    """الإعداد الكامل يعيد مُرسّلاً مسجّلاً عليه قناة تلغرام."""
    config = AppConfig(dry_run=False, telegram_bot_token="123:ABC", telegram_chat_id="42")

    notifier = build_notifier(config)

    assert notifier is not None
    assert [ch.name for ch in notifier.channels] == ["TelegramChannel"]


def test_run_completes_in_dry_run_without_token(monkeypatch):
    """التشغيل في وضع Dry-Run يكتمل بلا توكن ولا استدعاء للمُرسِل."""
    config = AppConfig(dry_run=True, telegram_bot_token=None, telegram_chat_id=None)
    _patch_run(monkeypatch, config)

    def _fail_if_called(cfg):
        raise AssertionError("يجب ألا يُبنى المُرسِل في وضع Dry-Run")

    monkeypatch.setattr(main, "build_notifier", _fail_if_called)

    main.run()

    assert FakeStore.instances[0].closed is True
    assert FakeStore.instances[0].marked == []


def test_run_skips_send_when_notifier_none(monkeypatch):
    """غياب الإعدادات مع dry_run=False يتخطّى الإرسال بدل الانهيار."""
    config = AppConfig(dry_run=False, telegram_bot_token=None, telegram_chat_id=None)
    _patch_run(monkeypatch, config)
    monkeypatch.setattr(main, "build_notifier", lambda cfg: None)

    main.run()

    assert FakeStore.instances[0].closed is True
    assert FakeStore.instances[0].marked == []


class FakeNotifier:
    """مُرسِل يُعيد نتائج جاهزة بدل الاتصال بتلغرام."""

    def __init__(self, results):
        self.results = results
        self.broadcast_calls: list[str] = []

    def broadcast(self, message, filepath=None):
        self.broadcast_calls.append(message)
        return self.results


def test_run_persists_tenders_in_dry_run(monkeypatch):
    """Dry-Run يحفظ الصفقات ولا يبلّغ ولا يزيد عدّاد المحاولات."""
    config = AppConfig(dry_run=True)
    _patch_run(monkeypatch, config)
    monkeypatch.setattr(main, "build_notifier", lambda cfg: pytest.fail("Dry-Run لا يبني مُرسّلاً"))

    main.run()

    store = FakeStore.instances[0]
    assert store.saved == [dict(LIVE_TENDER)]
    assert store.count() == 1
    assert store.marked == []
    assert store.failed == []


def test_run_does_not_mark_sent_when_all_channels_fail(monkeypatch):
    """فشل كل القنوات = محاولة فاشلة لكل صفقة، بلا وسم."""
    config = AppConfig(dry_run=False, telegram_bot_token="123:ABC", telegram_chat_id="42")
    _patch_run(monkeypatch, config)
    monkeypatch.setattr(
        main,
        "build_notifier",
        lambda cfg: FakeNotifier(
            [
                {"channel": "TelegramChannel", "error": "ValueError: boom"},
                {"channel": "OtherChannel", "error": "TimeoutError: late"},
            ]
        ),
    )

    main.run()

    store = FakeStore.instances[0]
    assert store.marked == []
    assert store.failed == [dict(LIVE_TENDER)]
    assert store.failed_attempt_error == "ValueError: boom; TimeoutError: late"


def test_run_marks_sent_when_one_channel_succeeds(monkeypatch):
    """نجاح قناة واحدة يكفي للوسم، ويُقرأ الناتج بـ .get لتحمّل channel/error."""
    config = AppConfig(dry_run=False, telegram_bot_token="123:ABC", telegram_chat_id="42")
    _patch_run(monkeypatch, config)
    monkeypatch.setattr(
        main,
        "build_notifier",
        lambda cfg: FakeNotifier(
            [
                {"channel": "TelegramChannel", "text_ok": True, "file_ok": True},
                {"channel": "OtherChannel", "error": "ValueError: boom"},
            ]
        ),
    )

    main.run()

    store = FakeStore.instances[0]
    assert store.marked == [dict(LIVE_TENDER)]
    assert store.failed == []


def test_smart_scraper_skips_blocked_tender(tmp_path, monkeypatch, capsys):
    """الكرولز الذكي يستثني الصفقة المحجوبة ويُبلّغ الحيّة فقط."""
    from run_smart_scraper import main as smart_main
    from storage.db import TenderStore

    blocked = {**LIVE_TENDER, "title": "مناقصة محجوبة", "link": "https://ade.dz/blocked"}
    fresh = {**LIVE_TENDER, "title": "مناقصة حية", "link": "https://ade.dz/fresh"}

    store = TenderStore(db_path=str(tmp_path / "smart.db"))
    store.add_tender(blocked)
    for _ in range(3):
        store.register_failed_attempt(blocked, "boom")
    assert store.is_new_or_changed(blocked) is False

    sent: list[str] = []

    class FakeCrawler:
        def __init__(self, name, url, priority="1"):
            self.url = url

        def run(self):
            return [dict(blocked), dict(fresh)]

    class FakeNotifier:
        def __init__(self, token, chat_id):
            pass

        def send_message(self, message):
            sent.append(message)
            return True

    monkeypatch.setattr(
        "run_smart_scraper.SourcesLoader",
        lambda: type(
            "L", (), {"crawlable": lambda self, priority=None: [{"tp": "https://x.dz", "ar": "X"}]}
        )(),
    )
    monkeypatch.setattr(
        "run_smart_scraper.TenderFilter",
        lambda: type("F", (), {"filter_tenders": lambda self, tenders: list(tenders)})(),
    )
    monkeypatch.setattr("run_smart_scraper.SmartCrawler", FakeCrawler)
    monkeypatch.setattr("run_smart_scraper.TelegramNotifier", FakeNotifier)
    monkeypatch.setattr("run_smart_scraper.TenderStore", lambda: store)
    monkeypatch.setattr(sys, "argv", ["run_smart_scraper.py", "1", "5"])

    smart_main()

    assert len(sent) == 1
    assert "مناقصة حية" in sent[0]
    assert "مناقصة محجوبة" not in sent[0]
    assert store.is_notified(fresh) is True
    assert store.is_new_or_changed(blocked) is False
    assert store.blocked_tenders()[0]["title"] == "مناقصة محجوبة"
    assert "Sent 1 to Telegram" in capsys.readouterr().out


def test_T2_tests_still_pass_after_T1():
    """اختبارات T2 الأساسية ما زالت تحمي العقود التي بُنيت عليها."""
    from notifications.base import NotificationChannel, NotificationManager

    class Broken(NotificationChannel):
        def send_text(self, message):
            raise ValueError("فشل")

        def send_file(self, filepath, caption=""):
            return False

    manager = NotificationManager()
    manager.register(Broken())
    results = manager.broadcast("hi")

    assert results[0]["error"].startswith("ValueError")
    assert build_notifier(AppConfig(dry_run=True)) is None
    partial = AppConfig(dry_run=False, telegram_bot_token="x", telegram_chat_id=None)
    assert build_notifier(partial) is None
