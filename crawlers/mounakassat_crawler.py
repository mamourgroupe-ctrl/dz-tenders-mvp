"""Session-authenticated crawler for MounakassatDZ announcements."""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from storage.database import TenderDatabase
from storage.tender_quality import MIN_TENDER_RELEVANCE_SCORE

from .base_crawler import BaseCrawler, sanitize_url

logger = logging.getLogger(__name__)
BASE_URL = "https://mounakassatdz.com/"
PROGRESS_PATH = Path(__file__).with_name("mounakassat_progress.json")
DATE_RE = re.compile(r"(?<!\d)\d{2}[-/]\d{2}[-/]\d{4}(?!\d)")
REFERENCE_RE = re.compile(
    r"(?:r[eé]f[eé]rence|r[eé]f\.?|رقم\s*(?:المرجع|الإعلان)?|n[°ºo])"
    r"\s*[:#-]?\s*([\w./-]+)",
    re.IGNORECASE,
)


class MounakassatCrawler(BaseCrawler):
    """Fetch MounakassatDZ listing pages using an authenticated HTTP session."""

    def __init__(
        self,
        start_page: int | None = None,
        max_pages: int | None = None,
        dry_run: bool = False,
        session: requests.Session | None = None,
        database: TenderDatabase | None = None,
        progress_path: Path = PROGRESS_PATH,
    ) -> None:
        """Initialize session, storage, and resume position."""
        super().__init__(BASE_URL)
        self.progress_path = Path(progress_path)
        resolved_start_page = start_page if start_page is not None else self._resume_page()
        if resolved_start_page < 1:
            raise ValueError("start_page must be at least 1")
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        self.session = session or requests.Session()
        self.dry_run = dry_run
        self.max_pages = max_pages
        self.database = (
            database if database is not None else (None if dry_run else TenderDatabase())
        )
        self.start_page = resolved_start_page

    def _resume_page(self) -> int:
        """Return the page after the last successfully stored page."""
        if not self.progress_path.exists():
            return 1
        progress = json.loads(self.progress_path.read_text(encoding="utf-8"))
        last_page = progress.get("last_page")
        if not isinstance(last_page, int) or last_page < 1:
            raise ValueError(f"Invalid crawler progress file: {self.progress_path}")
        return last_page + 1

    def login(self) -> None:
        """Authenticate with phone/password from environment and retain cookies."""
        phone = os.getenv("MOUN_PHONE", "").strip()
        password = os.getenv("MOUN_PASSWORD", "")
        if not phone or not password:
            raise RuntimeError("Set MOUN_PHONE and MOUN_PASSWORD in the environment or .env")
        response = self.session.post(
            urljoin(self.base_url, "/api/signin"),
            data={"telephone": phone, "password": password},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("success"):
            raise RuntimeError("MounakassatDZ login failed; check credentials")

    def fetch_page(self, url: str) -> str:
        """Fetch one authenticated listing page and reject login redirects."""
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        if "/login" in urlsplit(response.url).path or 'id="form_signin"' in response.text:
            raise RuntimeError("MounakassatDZ session expired or login was rejected")
        return response.text

    def parse_tenders(self, html_content: str | None) -> list[dict]:
        """Parse announcement cards into tender dictionaries."""
        if not html_content:
            return []
        soup = BeautifulSoup(html_content, "html.parser")
        cards = soup.select("main article")
        if not cards:
            candidates = soup.select('main [class*="card"], main [class*="annonce"]')
            candidate_ids = {id(card) for card in candidates}
            cards = [
                card
                for card in candidates
                if not any(id(parent) in candidate_ids for parent in card.parents)
            ]

        tenders = []
        seen_urls: set[str] = set()
        for card in cards:
            title_link = card.select_one(".m-card__title a[href]")
            if title_link is None:
                title_link = card.select_one("h1 a[href], h2 a[href], h3 a[href]")
            if title_link is None:
                continue
            title = title_link.get_text(" ", strip=True)
            details_url = sanitize_url(urljoin(self.base_url, title_link["href"]))
            if not title or not details_url or details_url in seen_urls:
                continue

            text = card.get_text(" ", strip=True)
            reference_match = REFERENCE_RE.search(text)
            published_text = next(
                (
                    span.get_text(" ", strip=True)
                    for span in card.select(".m-card__meta span")
                    if DATE_RE.search(span.get_text(" ", strip=True))
                ),
                "",
            )
            date_match = DATE_RE.search(published_text)
            published_date = None
            if date_match:
                published_date = (
                    datetime.strptime(date_match.group().replace("/", "-"), "%d-%m-%Y")
                    .date()
                    .isoformat()
                )

            wilaya_text = next(
                (
                    span.get_text(" ", strip=True)
                    for span in card.select(".m-card__meta span")
                    if "ولاية" in span.get_text(" ", strip=True)
                ),
                "",
            )
            organisation = card.select_one(".m-card__who")
            category = card.select_one(".m-card__secs")
            tender = {
                "title": title,
                "reference": reference_match.group(1) if reference_match else None,
                "details_url": details_url,
                "link": details_url,
                "published_date": published_date,
                "organisation": (
                    organisation.get_text(" ", strip=True) if organisation else "MounakassatDZ"
                ),
                "wilaya": wilaya_text.replace("ولاية", "", 1).strip() or None,
                "product": category.get_text(" ", strip=True) if category else None,
                "deadline": None,
                "status": "مفتوحة",
                "source": "MOUNAKASSATDZ",
            }
            tenders.append(tender)
            seen_urls.add(details_url)
        return tenders

    @staticmethod
    def _last_page(html_content: str, current_page: int) -> int:
        """Read the last page number from listing pagination links."""
        soup = BeautifulSoup(html_content, "html.parser")
        page_numbers = []
        for link in soup.select('a[href*="page="]'):
            page = parse_qs(urlsplit(link["href"]).query).get("page", [None])[0]
            if page and page.isdigit():
                page_numbers.append(int(page))
        return max(page_numbers, default=current_page)

    def _save_progress(self, page: int) -> None:
        """Atomically record the last successfully scraped page."""
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.progress_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps({"last_page": page}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary_path.replace(self.progress_path)

    def run(self) -> list[dict]:
        """Login, scrape listing pages with delays, and persist non-duplicate records."""
        self.login()
        page = self.start_page
        pages_scraped = 0
        tenders = []
        while True:
            if pages_scraped:
                time.sleep(random.uniform(3, 5))
            page_url = urljoin(self.base_url, f"/annonces/?page={page}")
            html = self.fetch_page(page_url)
            page_tenders = self.parse_tenders(html)
            if not page_tenders:
                break
            pages_scraped += 1
            tenders.extend(page_tenders)
            if not self.dry_run:
                if self.database is None:
                    raise RuntimeError("Database is unavailable outside dry-run mode")
                for tender in page_tenders:
                    self.database.add_tender(
                        {
                            **tender,
                            "relevance_score": MIN_TENDER_RELEVANCE_SCORE,
                        }
                    )
                self._save_progress(page)
            if self.max_pages is not None and pages_scraped >= self.max_pages:
                break
            if page >= self._last_page(html, page):
                break
            page += 1
        logger.info("MounakassatDZ: parsed %d tenders", len(tenders))
        return tenders


def main(argv: list[str] | None = None) -> int:
    """Run the MounakassatDZ crawler CLI."""
    parser = argparse.ArgumentParser(description="Crawl MounakassatDZ announcements")
    parser.add_argument("--start-page", type=int, help="Override the saved resume page")
    parser.add_argument("--max-pages", type=int, help="Limit the number of pages to crawl")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print without database or progress-file writes",
    )
    args = parser.parse_args(argv)
    load_dotenv()
    tenders = MounakassatCrawler(
        start_page=args.start_page,
        max_pages=args.max_pages,
        dry_run=args.dry_run,
    ).run()
    if args.dry_run:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(tenders, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
