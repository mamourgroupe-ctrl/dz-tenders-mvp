"""Tests for GoogleNewsCrawler (offline, using fixtures)."""

from pathlib import Path

import pytest

from crawlers.google_news_crawler import GoogleNewsCrawler

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def crawler():
    return GoogleNewsCrawler()


def test_parse_feed_returns_tenders(crawler):
    """5-item fixture yields results."""
    xml = _load("google_news_sample.xml")
    tenders = crawler.parse_feed(xml)
    assert len(tenders) >= 1


def test_title_strips_source_suffix(crawler):
    """'- Source' stripped from title."""
    xml = _load("google_news_sample.xml")
    tenders = crawler.parse_feed(xml)
    for t in tenders:
        assert not t["title"].endswith("- \u0627\u0644\u0639\u0631\u0628\u064a\u0629")
        assert not t["title"].endswith("- Reuters")


def test_source_extracted(crawler):
    """Source extracted from <source>."""
    xml = _load("google_news_sample.xml")
    tenders = crawler.parse_feed(xml)
    assert all(t["organisation"] for t in tenders)


def test_published_date_extracted(crawler):
    """pubDate parsed to ISO."""
    xml = _load("google_news_sample.xml")
    tenders = crawler.parse_feed(xml)
    for t in tenders:
        if t["published_date"]:
            assert len(t["published_date"]) == 10


def test_empty_xml_returns_empty(crawler):
    """Empty input -> []."""
    assert crawler.parse_feed("") == []
    assert crawler.parse_feed(None) == []


def test_invalid_xml_returns_empty(crawler):
    """Malformed XML -> []."""
    assert crawler.parse_feed("<not><valid>") == []


def test_non_tender_items_filtered(crawler):
    """Items without tender keywords are dropped."""
    xml = (
        '<?xml version="1.0"?>'
        "<rss><channel>"
        "<item>"
        "<title>Weather forecast</title>"
        "<link>https://example.com/w</link>"
        "<pubDate>Mon, 14 Sep 2026 07:00:00 GMT</pubDate>"
        "</item>"
        "<item>"
        "<title>appel d'offres test item</title>"
        "<link>https://example.com/t</link>"
        "<pubDate>Mon, 14 Sep 2026 07:00:00 GMT</pubDate>"
        "</item>"
        "</channel></rss>"
    )
    tenders = crawler.parse_feed(xml)
    assert len(tenders) == 1
    assert "appel" in tenders[0]["title"]


def test_source_constant(crawler):
    """Source field is 'news_aggregator'."""
    xml = _load("google_news_sample.xml")
    tenders = crawler.parse_feed(xml)
    for t in tenders:
        assert t["source"] == "news_aggregator"


def test_run_deduplicates(crawler, monkeypatch):
    """Same title in two feeds -> 1 entry."""
    same_xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>\u0645\u0646\u0627\u0642\u0635\u0629 \u0642\u0645\u062d - Reuters</title>
        <link>https://example.com/1</link>
        <source>Reuters</source>
        <pubDate>Mon, 14 Sep 2026 07:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    monkeypatch.setattr(crawler, "fetch_feed", lambda url: same_xml)
    tenders = crawler.run()
    assert len(tenders) == 1
