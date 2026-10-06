"""Tests for MarchesPublicsAuthCrawler (offline, using fixture)."""

import json
from pathlib import Path

import pytest

from crawlers.marches_publics_auth_crawler import MarchesPublicsAuthCrawler

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def crawler():
    return MarchesPublicsAuthCrawler()


@pytest.fixture
def next_data():
    return json.loads((FIXTURES / "marches_sample.json").read_text(encoding="utf-8"))


def test_parse_tenders_returns_list(crawler, next_data):
    """5-item fixture -> 5 tenders."""
    tenders = crawler.parse_tenders(next_data)
    assert len(tenders) == 5


def test_title_extracted(crawler, next_data):
    """marche.objetMarche becomes title."""
    tenders = crawler.parse_tenders(next_data)
    assert tenders[0]["title"]
    assert len(tenders[0]["title"]) > 3


def test_reference_extracted(crawler, next_data):
    """referenceInterne is captured."""
    tenders = crawler.parse_tenders(next_data)
    assert tenders[0]["reference"]  # e.g., '18/2026'


def test_organisation_from_service(crawler, next_data):
    """serviceContractant.denomination -> organisation."""
    tenders = crawler.parse_tenders(next_data)
    assert tenders[0]["organisation"]


def test_wilaya_from_service(crawler, next_data):
    """serviceContractant.wilaya -> wilaya."""
    tenders = crawler.parse_tenders(next_data)
    assert tenders[0]["wilaya"]


def test_published_date_iso(crawler, next_data):
    """datePremiereParution trimmed to YYYY-MM-DD."""
    tenders = crawler.parse_tenders(next_data)
    d = tenders[0]["published_date"]
    assert d and len(d) == 10 and d[4] == "-"


def test_link_points_to_consultation(crawler, next_data):
    """link is /consultation/{uuid}."""
    tenders = crawler.parse_tenders(next_data)
    assert "/consultation/" in tenders[0]["link"]


def test_source_constant(crawler, next_data):
    """Source = 'marches_publics'."""
    tenders = crawler.parse_tenders(next_data)
    for t in tenders:
        assert t["source"] == "marches_publics"


def test_empty_next_data(crawler):
    """Empty dict -> []."""
    assert crawler.parse_tenders({}) == []
    assert crawler.parse_tenders(None) == []


def test_strip_html_helper(crawler):
    """_strip_html removes tags."""
    assert crawler._strip_html("<p>Hello <b>World</b></p>") == "Hello World"
    assert crawler._strip_html("") == ""


def test_missing_uuid_still_parses(crawler):
    """Row with no uuid -> link is malformed but not crashed."""
    data = {
        "props": {
            "pageProps": {
                "data": [
                    {
                        "marche": {"objetMarche": "Test"},
                        "uuid": "",
                        "referenceInterne": "X/2026",
                    }
                ]
            }
        }
    }
    tenders = crawler.parse_tenders(data)
    assert len(tenders) == 1
    assert tenders[0]["title"] == "Test"


def test_missing_marche_key(crawler):
    """Row without marche key -> uses description fallback."""
    data = {
        "props": {
            "pageProps": {
                "data": [
                    {
                        "description": "<p>Fallback title</p>",
                        "uuid": "abc",
                    }
                ]
            }
        }
    }
    tenders = crawler.parse_tenders(data)
    assert len(tenders) == 1
    assert tenders[0]["title"] == "Fallback title"
