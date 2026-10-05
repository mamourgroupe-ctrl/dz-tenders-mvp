"""Tests for SafqaticCrawler (offline, using fixtures)."""

from pathlib import Path

import pytest

from crawlers.safqatic_crawler import SafqaticCrawler

FIXTURES = Path(__file__).parent / "fixtures" / "safqatic"


def _load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def crawler():
    return SafqaticCrawler()


def test_extracts_five_detail_ids(crawler):
    """Listing page contains 5 detail links."""
    html = _load("listing.html")
    ids = crawler._extract_detail_ids(html)
    assert len(ids) == 5
    assert "83789" in ids


def test_ids_sorted_descending(crawler):
    """Newest (highest ID) first."""
    html = _load("listing.html")
    ids = crawler._extract_detail_ids(html)
    assert ids == sorted(ids, key=int, reverse=True)


def test_parse_tenders_returns_urls(crawler):
    """parse_tenders returns full detail URLs."""
    html = _load("listing.html")
    urls = crawler.parse_tenders(html)
    assert len(urls) == 5
    assert all("detail_offre.php?id=" in u for u in urls)


def test_parse_detail_extracts_title(crawler):
    """Detail page title from <p>."""
    html = _load("detail_83789.html")
    url = "https://www.safqatic.dz/detail_offre.php?id=83789"
    tender = crawler.parse_detail(html, url)

    assert tender is not None
    assert "APPEL D'OFFRES" in tender["title"]
    assert "05/2026" in tender["reference"]


def test_parse_detail_extracts_year(crawler):
    """Published year from reference number."""
    html = _load("detail_83789.html")
    url = "https://www.safqatic.dz/detail_offre.php?id=83789"
    tender = crawler.parse_detail(html, url)

    assert tender["published_date"] == "2026-12-31"


def test_parse_detail_extracts_pdf(crawler):
    """Official PDF URL from docs/offres/."""
    html = _load("detail_83789.html")
    url = "https://www.safqatic.dz/detail_offre.php?id=83789"
    tender = crawler.parse_detail(html, url)

    assert tender["pdf_url"] is not None
    assert "docs/offres/" in tender["pdf_url"]
    assert "cadre_legal" not in tender["pdf_url"]


def test_parse_detail_sets_organisation(crawler):
    """Organisation is constant."""
    html = _load("detail_83789.html")
    url = "https://www.safqatic.dz/detail_offre.php?id=83789"
    tender = crawler.parse_detail(html, url)

    assert "Poste" in tender["organisation"]


def test_parse_detail_empty_html(crawler):
    """Empty HTML -> None."""
    assert crawler.parse_detail("", "http://x") is None
    assert crawler.parse_detail(None, "http://x") is None


def test_parse_detail_no_title(crawler):
    """HTML without meaningful <p> -> None."""
    html = "<html><body><p>short</p></body></html>"
    assert crawler.parse_detail(html, "http://x") is None
