"""Shared HTML parsing and CLI support for public tender listing crawlers."""

import argparse
import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from storage.database import TenderDatabase
from storage.tender_quality import MIN_TENDER_RELEVANCE_SCORE

from .base_crawler import BaseCrawler, sanitize_url

logger = logging.getLogger(__name__)

UNKNOWN_WILAYA = "غير محدد"
_ITEM_RE = re.compile(r"tender|appel|offre|annonce|avis|publication", re.IGNORECASE)
_CONTAINER_RE = re.compile(
    r"list|liste|listing|grid|container|wrapper|archive|results?|"
    r"r[eé]sultats?|section|navigation",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b"
)
_PUBLICATION_LABEL_RE = re.compile(
    r"(?:date.{0,20}(?:publication|parution)|publi[ée]\s+le|تاريخ\s+(?:النشر|الإعلان))",
    re.IGNORECASE,
)
_DEADLINE_LABEL_RE = re.compile(
    r"(?:date.{0,30}(?:limite|cl[oô]ture|d[eé]p[oô]t)|dernier\s+d[eé]lai|"
    r"آخر\s+(?:أجل|موعد))",
    re.IGNORECASE,
)
_REFERENCE_RE = re.compile(
    r"(?:r[eé]f[eé]rence|r[eé]f\.?|num[eé]ro|n[°ºo])\s*[:#\-]?\s*"
    r"([A-Z0-9][A-Z0-9/_.-]{1,})|"
    r"(?:رقم\s*(?:المرجع|الإعلان|المناقصة)?)\s*[:#\-]?\s*"
    r"([A-Z0-9\u0660-\u0669][A-Z0-9\u0660-\u0669/_.-]{1,})",
    re.IGNORECASE,
)
_WILAYA_RE = re.compile(
    r"(?:wilaya|ولاية)\s*[:\-]?\s*(.{2,60}?)"
    r"(?=\s+(?:date|deadline|r[eé]f|publication|dernier|"
    r"تاريخ|رقم|آخر)|[|;,\n]|$)",
    re.IGNORECASE,
)
_URL_SKIP_RE = re.compile(r"^(?:#|javascript:|mailto:)", re.IGNORECASE)


def _normalize_date(value: str | None) -> str | None:
    """Return a recognized date in ISO format, preserving unrecognized values."""
    if not value:
        return None
    match = _DATE_RE.search(value)
    if not match:
        return None

    date_text = match.group(0).replace(".", "/").replace("-", "/")
    for date_format in ("%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_text, date_format).date().isoformat()
        except ValueError:
            continue
    return date_text


def _labeled_date(text: str, label_pattern: re.Pattern[str]) -> str | None:
    """Find a date following one of the source's date labels."""
    label_match = label_pattern.search(text)
    if not label_match:
        return None
    return _normalize_date(text[label_match.end() : label_match.end() + 80])


def _extract_reference(text: str) -> str | None:
    """Extract the first explicitly labeled tender reference."""
    match = _REFERENCE_RE.search(text)
    if not match:
        return None
    return next((value.strip(" .,:;") for value in match.groups() if value), None)


def _extract_wilaya(text: str) -> str:
    """Extract an explicitly labeled wilaya or return the standard unknown value."""
    match = _WILAYA_RE.search(text)
    if not match:
        return UNKNOWN_WILAYA
    value = re.split(
        r"\s+(?:date|deadline|r[eé]f|publication|dernier|تاريخ|رقم|آخر)\b",
        match.group(1),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" \t:,-")
    return value or UNKNOWN_WILAYA


class PublicTenderCrawler(BaseCrawler):
    """Parse tender cards from a public HTML listing page."""

    def __init__(self, base_url: str, source: str):
        super().__init__(sanitize_url(base_url))
        self.source = source

    def fetch_page(self, url: str) -> str | None:
        """Fetch a page using requests, returning None for HTTP/network failures."""
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; DZ-Tenders/1.0)"},
                timeout=20,
            )
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text
        except requests.RequestException as exc:
            logger.error("Could not fetch %s: %s", url, exc)
            return None

    def _candidate_items(self, soup: BeautifulSoup) -> list[Tag]:
        """Return likely record containers while excluding listing wrappers."""
        candidates: list[Tag] = []
        for element in soup.find_all(True):
            identity = " ".join(
                [
                    str(element.get("id") or ""),
                    " ".join(element.get("class", [])),
                ]
            )
            is_container = _CONTAINER_RE.search(identity)
            if not is_container and (
                element.name in {"article", "tr"} or _ITEM_RE.search(identity)
            ):
                candidates.append(element)

        candidate_ids = {id(element) for element in candidates}
        return [
            element
            for element in candidates
            if not any(id(parent) in candidate_ids for parent in element.parents)
        ]

    def _parse_item(self, item: Tag) -> dict | None:
        """Parse one listing item, ignoring cards without a title and safe URL."""
        heading = item.find(re.compile(r"^h[1-6]$"))
        title = heading.get_text(" ", strip=True) if heading else ""

        anchors = item.find_all("a", href=True)
        if not title:
            title = next(
                (anchor.get_text(" ", strip=True) for anchor in anchors
                 if len(anchor.get_text(" ", strip=True)) > 8),
                "",
            )
        if not title:
            return None

        anchor = heading.find("a", href=True) if heading else None
        if anchor is None:
            anchor = next(
                (
                    candidate
                    for candidate in anchors
                    if not _URL_SKIP_RE.match(str(candidate.get("href", "")).strip())
                ),
                None,
            )
        if anchor is None:
            return None

        source_url = sanitize_url(urljoin(self.base_url, str(anchor["href"])))
        if not source_url:
            return None

        text = item.get_text(" ", strip=True)
        publication_date = _labeled_date(text, _PUBLICATION_LABEL_RE)
        deadline = _labeled_date(text, _DEADLINE_LABEL_RE)

        return {
            "title": title,
            "reference": _extract_reference(text),
            "publication_date": publication_date,
            "published_date": publication_date,
            "deadline": deadline,
            "source_url": source_url,
            "link": source_url,
            "source": self.source,
            "wilaya": _extract_wilaya(text),
            "organisation": self.source,
            "product": UNKNOWN_WILAYA,
            "status": "مفتوحة",
        }

    def parse_tenders(self, html_content: str | None) -> list[dict]:
        """Parse tender records from listing cards in the supplied HTML."""
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        tenders = []
        seen_urls: set[str] = set()
        for item in self._candidate_items(soup):
            tender = self._parse_item(item)
            if tender and tender["source_url"] not in seen_urls:
                tenders.append(tender)
                seen_urls.add(tender["source_url"])
        return tenders

    def run(self) -> list[dict]:
        """Fetch and parse the configured public listing page."""
        html = self.fetch_page(self.base_url)
        tenders = self.parse_tenders(html)
        logger.info("%s: extracted %d tenders", self.source, len(tenders))
        return tenders


def run_cli(crawler_type: type[PublicTenderCrawler], argv: list[str] | None = None) -> int:
    """Run a crawler, printing JSON in dry-run mode or saving records otherwise."""
    parser = argparse.ArgumentParser(description=f"Crawl {crawler_type.__name__} tenders.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print parsed records as JSON without writing to the database.",
    )
    args = parser.parse_args(argv)
    tenders = crawler_type().run()

    if args.dry_run:
        print(json.dumps(tenders, ensure_ascii=False, indent=2))
        return 0

    database = TenderDatabase()
    saved = 0
    for tender in tenders:
        storage_record = {
            **tender,
            "link": tender["source_url"],
            "relevance_score": MIN_TENDER_RELEVANCE_SCORE,
        }
        saved += database.add_tender(storage_record)
    logger.info("%s: saved %d of %d tenders", crawler_type.__name__, saved, len(tenders))
    return 0
