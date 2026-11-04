"""Offline tests for the BAOSEM and BOMOP public listing crawlers."""

import json

from crawlers.baosem import BAOSEMCrawler
from crawlers.baosem import main as baosem_main
from crawlers.bomop import BOMOPCrawler
from crawlers.bomop import main as bomop_main
from storage.database import TenderDatabase


def test_baosem_parses_listing_fields_and_unknown_wilaya():
    """BAOSEM records expose requested fields and the unknown-wilaya fallback."""
    html = """
    <article class="tender-item">
      <h2><a href="/site/notice/123">Travaux de maintenance</a></h2>
      <p>Référence: AO-15/2026</p>
      <p>Date de publication: 04/10/2026</p>
      <p>Date limite de dépôt: 20/11/2026</p>
    </article>
    """

    tenders = BAOSEMCrawler().parse_tenders(html)

    assert tenders == [
        {
            "title": "Travaux de maintenance",
            "reference": "AO-15/2026",
            "publication_date": "2026-10-04",
            "published_date": "2026-10-04",
            "deadline": "2026-11-20",
            "source_url": "https://baosem.com/site/notice/123",
            "link": "https://baosem.com/site/notice/123",
            "source": "BAOSEM",
            "wilaya": "غير محدد",
            "organisation": "BAOSEM",
            "product": "غير محدد",
            "status": "مفتوحة",
        }
    ]


def test_bomop_parses_arabic_wilaya_and_date_labels():
    """BOMOP records retain an explicitly labeled wilaya."""
    html = """
    <div class="annonce-item">
      <a href="/ar/annonce/456"><h3>اقتناء تجهيزات</h3></a>
      <p>رقم الإعلان: 12/2026</p>
      <p>تاريخ النشر: 2026-10-03</p>
      <p>آخر أجل: 2026-11-08</p>
      <p>ولاية: الجزائر</p>
    </div>
    """

    tender = BOMOPCrawler().parse_tenders(html)[0]

    assert tender["title"] == "اقتناء تجهيزات"
    assert tender["reference"] == "12/2026"
    assert tender["publication_date"] == "2026-10-03"
    assert tender["deadline"] == "2026-11-08"
    assert tender["wilaya"] == "الجزائر"
    assert tender["source_url"] == "https://bomop.anep.dz/ar/annonce/456"
    assert tender["source"] == "BOMOP"


def test_listing_page_without_tender_cards_returns_empty_list():
    """Navigation and promotional copy are not parsed as tenders."""
    html = """
    <nav><a href="/annonces">Toutes les annonces</a></nav>
    <main><p>Abonnez-vous pour consulter les offres.</p></main>
    """

    assert BOMOPCrawler().parse_tenders(html) == []


def test_listing_wrapper_does_not_merge_multiple_tender_cards():
    """A tender-list wrapper is ignored so its individual cards remain distinct."""
    html = """
    <div class="tender-list">
      <article class="tender-item">
        <h2><a href="/tender/1">First tender title</a></h2>
        <p>Reference: 1/2026</p>
      </article>
      <article class="tender-item">
        <h2><a href="/tender/2">Second tender title</a></h2>
        <p>Reference: 2/2026</p>
      </article>
    </div>
    """

    tenders = BAOSEMCrawler().parse_tenders(html)

    assert [tender["reference"] for tender in tenders] == ["1/2026", "2/2026"]


def test_baosem_dry_run_prints_json_without_creating_database(monkeypatch, capsys):
    """The CLI dry-run prints results and never initializes database storage."""
    expected = [{"title": "Tender", "source": "BAOSEM"}]
    monkeypatch.setattr(BAOSEMCrawler, "run", lambda self: expected)

    class UnexpectedDatabase:
        def __init__(self):
            raise AssertionError("dry-run must not initialize the database")

    monkeypatch.setattr("crawlers.public_tender_crawler.TenderDatabase", UnexpectedDatabase)

    assert baosem_main(["--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_bomop_cli_saves_parsed_records(monkeypatch, tmp_path):
    """The normal BOMOP CLI inserts accepted records into the tender database."""
    expected = [
        {
            "title": "Tender",
            "source_url": "https://bomop.anep.dz/tender/1",
            "source": "BOMOP",
            "reference": "AO-1/2026",
            "deadline": "2026-12-01",
            "organisation": "BOMOP",
        }
    ]
    monkeypatch.setattr(BOMOPCrawler, "run", lambda self: expected)
    database = TenderDatabase(str(tmp_path / "bomop.db"))
    monkeypatch.setattr(
        "crawlers.public_tender_crawler.TenderDatabase",
        lambda: database,
    )

    assert bomop_main([]) == 0
    with database._connect() as connection:
        row = connection.execute(
            "SELECT title, link, source, reference, deadline FROM tenders"
        ).fetchone()

    assert tuple(row) == (
        "Tender",
        expected[0]["source_url"],
        "BOMOP",
        "AO-1/2026",
        "2026-12-01",
    )
