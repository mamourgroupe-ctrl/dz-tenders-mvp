"""Offline tests for the MounakassatDZ session crawler."""

import json

import pytest

from crawlers.mounakassat_crawler import MounakassatCrawler
from storage.database import TenderDatabase

CARD_HTML = """
<main>
  <article class="m-card">
    <div class="m-card__secs"><span>الصرف الصحي وأشغال المياه</span></div>
    <h2 class="m-card__title">
      <a href="/details/abc123-title">تنفيذ أشغال المياه</a>
    </h2>
    <div class="m-card__who"><span>محافظة الغابات ولاية باتنة</span></div>
    <div class="m-card__meta">
      <span>ولاية باتنة</span>
      <span>نُشر <bdi>03-11-2026</bdi></span>
      <span>باقي 8 يوم</span>
    </div>
  </article>
  <nav aria-label="الصفحات">
    <a href="/annonces/?page=2">2</a>
    <a href="/annonces/?page=454">454</a>
  </nav>
</main>
"""


class FakeResponse:
    """Minimal response object for authentication tests."""

    url = "https://mounakassatdz.com/api/signin"
    text = ""

    def raise_for_status(self):
        """Simulate a successful HTTP response."""

    @staticmethod
    def json():
        """Return a successful sign-in result."""
        return {"success": True}


class FakeSession:
    """Record requests without network access."""

    def __init__(self):
        self.posts = []
        self.gets = []
        self.responses = []

    def post(self, url, **kwargs):
        """Record a POST and return a fake successful response."""
        self.posts.append((url, kwargs))
        return FakeResponse()

    def get(self, url, **kwargs):
        """Return the next preconfigured listing response."""
        self.gets.append((url, kwargs))
        return self.responses.pop(0)


def test_login_uses_site_form_fields_and_session(monkeypatch, tmp_path):
    """Credentials are sent using the telephone/password fields from the form."""
    monkeypatch.setenv("MOUN_PHONE", "0790000000")
    monkeypatch.setenv("MOUN_PASSWORD", "test-password")
    session = FakeSession()
    crawler = MounakassatCrawler(dry_run=True, session=session, progress_path=tmp_path / "p.json")

    crawler.login()

    url, options = session.posts[0]
    assert url == "https://mounakassatdz.com/api/signin"
    assert options["data"] == {
        "telephone": "0790000000",
        "password": "test-password",
    }


def test_login_requires_both_environment_variables(monkeypatch, tmp_path):
    """Missing credentials fail before any request is sent."""
    monkeypatch.delenv("MOUN_PHONE", raising=False)
    monkeypatch.delenv("MOUN_PASSWORD", raising=False)
    session = FakeSession()
    crawler = MounakassatCrawler(dry_run=True, session=session, progress_path=tmp_path / "p.json")

    with pytest.raises(RuntimeError, match="MOUN_PHONE and MOUN_PASSWORD"):
        crawler.login()

    assert session.posts == []


def test_parse_tender_card_extracts_fields_and_absolute_details_url(tmp_path):
    """Observed MounakassatDZ card markup maps to tender fields."""
    crawler = MounakassatCrawler(dry_run=True, progress_path=tmp_path / "p.json")

    tenders = crawler.parse_tenders(CARD_HTML)

    assert len(tenders) == 1
    assert tenders[0]["title"] == "تنفيذ أشغال المياه"
    assert tenders[0]["details_url"] == ("https://mounakassatdz.com/details/abc123-title")
    assert tenders[0]["published_date"] == "2026-11-03"
    assert tenders[0]["wilaya"] == "باتنة"
    assert tenders[0]["source"] == "MOUNAKASSATDZ"


def test_resume_uses_page_after_last_completed_page(tmp_path):
    """The saved last page resumes at the following page."""
    progress_path = tmp_path / "progress.json"
    progress_path.write_text(json.dumps({"last_page": 17}), encoding="utf-8")

    crawler = MounakassatCrawler(dry_run=True, progress_path=progress_path)

    assert crawler.start_page == 18


def test_start_page_overrides_saved_resume_page(tmp_path):
    """An explicit start page takes precedence over progress state."""
    progress_path = tmp_path / "progress.json"
    progress_path.write_text(json.dumps({"last_page": 17}), encoding="utf-8")

    crawler = MounakassatCrawler(
        start_page=1,
        dry_run=True,
        progress_path=progress_path,
    )

    assert crawler.start_page == 1


def test_max_pages_limits_a_listing_with_more_pages(monkeypatch, tmp_path):
    """A bounded run stops after the requested pages despite later pagination."""
    monkeypatch.setenv("MOUN_PHONE", "0790000000")
    monkeypatch.setenv("MOUN_PASSWORD", "test-password")
    session = FakeSession()
    session.responses = [_listing_response(CARD_HTML)]
    crawler = MounakassatCrawler(
        start_page=1,
        max_pages=1,
        dry_run=True,
        session=session,
        progress_path=tmp_path / "progress.json",
    )

    tenders = crawler.run()

    assert len(tenders) == 1
    assert len(session.gets) == 1


def test_dry_run_does_not_write_database_or_progress(monkeypatch, tmp_path):
    """Dry-run parses and prints nothing persistent, even across pages."""
    monkeypatch.setenv("MOUN_PHONE", "0790000000")
    monkeypatch.setenv("MOUN_PASSWORD", "test-password")
    session = FakeSession()
    session.responses = [
        _listing_response(CARD_HTML),
        _listing_response(CARD_HTML.replace("page=454", "page=2")),
    ]
    crawler = MounakassatCrawler(
        start_page=1,
        dry_run=True,
        session=session,
        progress_path=tmp_path / "progress.json",
    )
    monkeypatch.setattr("crawlers.mounakassat_crawler.time.sleep", lambda _: None)

    tenders = crawler.run()

    assert len(tenders) == 2
    assert not crawler.progress_path.exists()


def test_run_saves_to_database_idempotently_and_records_progress(monkeypatch, tmp_path):
    """Normal runs use the storage API and retain the successful page marker."""
    monkeypatch.setenv("MOUN_PHONE", "0790000000")
    monkeypatch.setenv("MOUN_PASSWORD", "test-password")
    db = TenderDatabase(str(tmp_path / "tenders.db"))
    session = FakeSession()
    one_page_html = CARD_HTML.replace("page=454", "page=1").replace("page=2", "page=1")
    session.responses = [_listing_response(one_page_html)]
    progress_path = tmp_path / "progress.json"
    crawler = MounakassatCrawler(
        start_page=1,
        session=session,
        database=db,
        progress_path=progress_path,
    )

    tenders = crawler.run()
    with db._connect() as connection:
        row = connection.execute("SELECT title, source FROM tenders").fetchone()

    assert len(tenders) == 1
    assert tuple(row) == ("تنفيذ أشغال المياه", "MOUNAKASSATDZ")
    assert json.loads(progress_path.read_text(encoding="utf-8")) == {"last_page": 1}

    duplicate_session = FakeSession()
    duplicate_session.responses = [_listing_response(one_page_html)]
    duplicate_crawler = MounakassatCrawler(
        start_page=1,
        session=duplicate_session,
        database=db,
        progress_path=progress_path,
    )

    duplicate_crawler.run()

    with db._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 1


def _listing_response(html):
    """Create a successful fake listing response."""

    class ListingResponse:
        url = "https://mounakassatdz.com/annonces/?page=1"
        text = html

        @staticmethod
        def raise_for_status():
            """Simulate a successful HTTP response."""

    return ListingResponse()
