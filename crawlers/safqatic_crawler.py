"""Safqatic crawler — poste & telecom tenders via Playwright."""

import contextlib
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_crawler import BaseCrawler, sanitize_url

logger = logging.getLogger(__name__)

BASE_URL = "https://www.safqatic.dz"
SECTOR = "poste_telecom"
ORGANISATION = "Ministere de la Poste et des Telecommunications"
UNKNOWN_VALUE = "غير محدد"

LISTING_PATHS = [
    "index.php?type=1",  # Appels d'offres
    "index.php?type=2",  # Avis de consultation
]

REFERENCE_RE = re.compile(r"N[°o]\s*:?\s*(\d{1,4})\s*/\s*(\d{4})", re.IGNORECASE)
DETAIL_ID_RE = re.compile(r"id=(\d+)")
PDF_OFFRE_RE = re.compile(r"docs/offres/.+\.pdf", re.IGNORECASE)


class SafqaticCrawler(BaseCrawler):
    """
    Crawler for Safqatic.

    The site blocks plain requests, so fetch_page uses Playwright
    (Edge channel, pre-installed on Windows).
    """

    def __init__(self, base_url=BASE_URL):
        super().__init__(sanitize_url(base_url))
        self._playwright = None
        self._browser = None

    def _ensure_browser(self):
        """Lazy-launch Playwright browser."""
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(channel="msedge", headless=True)

    def close(self):
        """Close browser and Playwright."""
        if self._browser:
            with contextlib.suppress(Exception):
                self._browser.close()
        if self._playwright:
            with contextlib.suppress(Exception):
                self._playwright.stop()
        self._browser = None
        self._playwright = None

    def fetch_page(self, url, timeout_ms=30000):
        """Fetch a page via Playwright."""
        self._ensure_browser()
        page = self._browser.new_page()
        try:
            page.goto(url, timeout=timeout_ms)
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            return page.content()
        except Exception as e:
            logger.error("Playwright error for %s: %s", url, e)
            return None
        finally:
            page.close()

    def _extract_detail_ids(self, html):
        """Extract detail IDs from a listing page."""
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        ids = []
        for link in soup.select("a[href*='detail_offre']"):
            href = link.get("href", "")
            m = DETAIL_ID_RE.search(href)
            if m:
                ids.append(m.group(1))
        # الأحدث أولاً (ID أكبر)
        return sorted(set(ids), key=int, reverse=True)

    def _extract_year(self, text):
        """Extract publication year from reference number."""
        if not text:
            return None
        m = REFERENCE_RE.search(text)
        if m:
            return int(m.group(2))
        return None

    def parse_detail(self, html, detail_url):
        """Parse one detail page -> tender dict, or None."""
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        # العنوان + المرجع من <p>
        title = ""
        reference = ""
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 30 and not title:
                title = text
            if REFERENCE_RE.search(text) and not reference:
                reference = text

        if not title:
            return None

        year = self._extract_year(reference) or self._extract_year(title)

        # PDF الرسمي
        pdf_url = None
        for a in soup.select("a[href$='.pdf']"):
            href = a.get("href", "")
            if PDF_OFFRE_RE.search(href):
                pdf_url = urljoin(self.base_url, href)
                break

        return {
            "title": title,
            "link": detail_url,
            "reference": reference or None,
            "organisation": ORGANISATION,
            "wilaya": "",
            "product": UNKNOWN_VALUE,
            "deadline": UNKNOWN_VALUE,
            "status": UNKNOWN_VALUE,
            # السنة فقط متاحة من الرابط، فنعتبرها صادرة في آخر السنة (لا أولها)
            # حتى لا تُسقطها W17-A بسبب النافذة 90-يوم.
            "published_date": f"{year}-12-31" if year else None,
            "pdf_url": pdf_url,
            "source": SECTOR,
        }

    def parse_tenders(self, html):
        """Parse listing page -> list of detail URLs (for tests)."""
        ids = self._extract_detail_ids(html)
        return [urljoin(self.base_url, f"detail_offre.php?id={tid}") for tid in ids]

    def run(self):
        """Fetch all listings + details, return tenders."""
        all_tenders = []
        try:
            for path in LISTING_PATHS:
                listing_url = urljoin(self.base_url, path)
                logger.info("Safqatic listing: %s", listing_url)
                html = self.fetch_page(listing_url)
                ids = self._extract_detail_ids(html)
                logger.info("  found %d tenders", len(ids))

                for tid in ids:
                    detail_url = urljoin(self.base_url, f"detail_offre.php?id={tid}")
                    detail_html = self.fetch_page(detail_url)
                    tender = self.parse_detail(detail_html, detail_url)
                    if tender:
                        all_tenders.append(tender)
        finally:
            self.close()

        logger.info("Safqatic: extracted %d tenders", len(all_tenders))
        return all_tenders
