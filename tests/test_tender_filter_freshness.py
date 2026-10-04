"""اختبارات فلتر الحداثة — المناقصة المنتهية لا تُبلَّغ."""

from datetime import date
from pathlib import Path

import pytest
import requests

from crawlers.ade_crawler import ADECrawler
from tender_filter import TenderFilter

FIXTURES = Path(__file__).parent / "fixtures"

TODAY = date(2026, 10, 4)


def _load(name: str) -> str:
    """قراءة لقطة من ملفات الاختبار."""
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """يمنع أي طلب شبكة صامت."""

    def _boom(*args, **kwargs):
        raise AssertionError("network blocked in freshness tests")

    monkeypatch.setattr(requests, "get", _boom)


def _tender(**overrides) -> dict:
    """صفقة افتراضية."""
    base = {"title": "صفقة", "deadline": "غير محدد", "link": "https://x/1"}
    base.update(overrides)
    return base


def test_past_deadline_is_dropped():
    kept, dropped = TenderFilter().filter_fresh([_tender(deadline="2026-09-01")], today=TODAY)
    assert kept == []
    assert dropped[0][0] == "deadline_passed"


def test_future_deadline_is_kept():
    kept, dropped = TenderFilter().filter_fresh(
        [_tender(deadline="2026-12-01", published_date="2020-01-01")], today=TODAY
    )
    assert len(kept) == 1
    assert dropped == []


def test_unknown_deadline_with_old_published_date_is_dropped():
    kept, dropped = TenderFilter().filter_fresh([_tender(published_date="2023-01-01")], today=TODAY)
    assert kept == []
    assert dropped[0][0] == "published_stale"


def test_unknown_deadline_with_recent_published_date_is_kept():
    kept, dropped = TenderFilter().filter_fresh([_tender(published_date="2026-09-20")], today=TODAY)
    assert len(kept) == 1
    assert dropped == []


def test_window_boundary_is_inclusive():
    on_edge = _tender(published_date="2026-07-06")
    just_past = _tender(published_date="2026-07-05")
    kept, dropped = TenderFilter().filter_fresh([on_edge, just_past], today=TODAY, window_days=90)
    assert len(kept) == 1
    assert dropped[0][0] == "published_stale"


def test_unparseable_deadline_text_is_treated_as_unknown():
    kept, dropped = TenderFilter().filter_fresh(
        [
            _tender(title="أ", deadline="غير محدد"),
            _tender(title="ب", deadline="مفتوحة حالياً"),
            _tender(title="ج", deadline="آخر جل"),
            _tender(title="د", deadline="2026-02-30"),
        ],
        today=TODAY,
    )
    assert len(kept) == 4
    assert dropped == []


def test_real_ade_capture_yields_zero_surviving():
    crawler = ADECrawler()
    crawler.fetch_page = lambda url: None
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))
    kept, dropped = TenderFilter().filter_fresh(tenders, today=TODAY)
    assert len(tenders) == 4
    assert kept == []
    assert {reason for reason, _ in dropped} == {"published_stale", "undated_dated_source"}


def test_undated_source_without_the_key_is_kept():
    kept, dropped = TenderFilter().filter_fresh(
        [_tender(deadline="غير محدد", organisation="الديوان الوطني للتطهير")],
        today=TODAY,
    )
    assert len(kept) == 1
    assert dropped == []


def test_sample_rows_bypass_freshness():
    kept, dropped = TenderFilter().filter_fresh(
        [_tender(deadline="2020-01-01", is_sample=True, source_status="reference")],
        today=TODAY,
    )
    assert len(kept) == 1
    assert dropped == []


def test_window_is_configurable_via_env(monkeypatch):
    monkeypatch.setenv("FRESHNESS_WINDOW_DAYS", "10")
    kept, _ = TenderFilter().filter_fresh([_tender(published_date="2026-09-20")], today=TODAY)
    assert kept == []


def test_env_garbage_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("FRESHNESS_WINDOW_DAYS", "soon")
    assert TenderFilter().freshness_window_days == 90
    monkeypatch.setenv("FRESHNESS_WINDOW_DAYS", "0")
    assert TenderFilter().freshness_window_days == 90


def test_freshness_kill_switch_disables_everything(monkeypatch):
    monkeypatch.setenv("FRESHNESS_ENABLED", "false")
    kept, dropped = TenderFilter().filter_fresh([_tender(deadline="2020-01-01")], today=TODAY)
    assert len(kept) == 1
    assert dropped == []
