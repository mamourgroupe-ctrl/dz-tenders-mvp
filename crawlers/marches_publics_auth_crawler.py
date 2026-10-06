"""marches_publics_auth_crawler.py — Authenticated crawler (v2, robust).

Fixes: single page reuse + delays + retries to avoid ERR_CONNECTION_CLOSED.
"""

import logging
import os
import re
import time
from pathlib import Path

from .base_crawler import BaseCrawler, sanitize_url

logger = logging.getLogger(__name__)

BASE_URL = "https://marches-publics.gov.dz"
SECTOR = "marches_publics"
DEFAULT_STATE = Path("storage/marches_state.json")


class MarchesPublicsAuthCrawler(BaseCrawler):
    """Crawler for the official Algerian public-procurement portal.

    Requires an authenticated session saved in `storage/marches_state.json`.

    Env vars:
        MARCHES_MAX_PAGES  (default 3)  — pages to fetch
        MARCHES_STATE_PATH (default storage/marches_state.json)
        MARCHES_DELAY_SEC  (default 6)  — delay between page loads
    """

    def __init__(self, base_url: str = BASE_URL):
        super().__init__(sanitize_url(base_url))
        self.state_path = Path(os.getenv("MARCHES_STATE_PATH", str(DEFAULT_STATE)))
        self.max_pages = int(os.getenv("MARCHES_MAX_PAGES", "3"))
        self.delay_sec = int(os.getenv("MARCHES_DELAY_SEC", "6"))
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ------------------------------------------------------------------ #
    def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        if not self.state_path.exists():
            raise FileNotFoundError(
                f"Session file not found: {self.state_path}. Run: python scripts/marches_login.py"
            )
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(channel="msedge", headless=False)
        self._context = self._browser.new_context(
            storage_state=str(self.state_path),
            ignore_https_errors=True,
            viewport={"width": 1400, "height": 900},
        )
        # Reuse the SAME page for all navigations (avoids connection churn)
        self._page = self._context.new_page()

    def close(self) -> None:
        import contextlib

        for obj in (self._page, self._context, self._browser):
            if obj is not None:
                with contextlib.suppress(Exception):
                    obj.close()
        if self._playwright is not None:
            with contextlib.suppress(Exception):
                self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    # ------------------------------------------------------------------ #
    def _load_page(self, url: str, retries: int = 3) -> dict | None:
        """Navigate to URL and return __NEXT_DATA__, with retries."""
        self._ensure_browser()

        for attempt in range(1, retries + 1):
            try:
                logger.info("  load %s (try %d/%d)", url, attempt, retries)
                self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
                # wait for Next.js hydration + API calls
                self._page.wait_for_timeout(self.delay_sec * 1000)

                next_data = self._page.evaluate("() => window.__NEXT_DATA__")
                if next_data:
                    return next_data

                logger.warning("  no __NEXT_DATA__ (attempt %d)", attempt)
            except Exception as e:
                logger.warning("  attempt %d failed: %s", attempt, e)

            if attempt < retries:
                time.sleep(self.delay_sec)

        return None

    # ------------------------------------------------------------------ #
    @staticmethod
    def _strip_html(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"<[^>]+>", "", text).strip()

    def parse_tenders(self, next_data: dict) -> list[dict]:
        if not next_data:
            return []
        pp = next_data.get("props", {}).get("pageProps", {})
        rows = pp.get("data", [])
        if not isinstance(rows, list):
            return []

        tenders = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            marche = row.get("marche") or {}
            service = row.get("serviceContractant") or {}

            uuid = row.get("uuid") or ""
            reference = marche.get("referenceInterne") or row.get("referenceInterne") or ""
            title = marche.get("objetMarche") or self._strip_html(row.get("description", "")) or ""
            if not title:
                continue

            details_url = f"{self.base_url}/consultation/{uuid}"
            published = (row.get("datePremiereParution") or "")[:10]

            tenders.append(
                {
                    "title": title,
                    "link": sanitize_url(details_url),
                    "reference": reference or None,
                    "organisation": service.get("denomination") or "",
                    "wilaya": service.get("wilaya") or "",
                    "product": "غير محدد",
                    "deadline": "غير محدد",
                    "status": "غير محدد",
                    "published_date": published or None,
                    "source": SECTOR,
                    "source_uuid": uuid,
                    "mode": marche.get("modePassation") or "",
                    "nature": marche.get("nature") or "",
                    "ministere": service.get("ministere") or "",
                    "commune": service.get("commune") or "",
                }
            )
        return tenders

    # ------------------------------------------------------------------ #
    def run(self) -> list[dict]:
        logger.info(
            "MarchesPublics: fetching up to %d pages (session=%s, delay=%ds)",
            self.max_pages,
            self.state_path,
            self.delay_sec,
        )

        all_tenders: list[dict] = []
        try:
            # Warm-up: load home page first (establishes context)
            logger.info("  warm-up: home page")
            self._load_page(self.base_url)

            for page_num in range(1, self.max_pages + 1):
                url = f"{self.base_url}/consultation?page={page_num}"
                next_data = self._load_page(url)
                if not next_data:
                    logger.warning("  no data on page %d", page_num)
                    continue

                rows = self.parse_tenders(next_data)
                logger.info("  page %d -> %d tenders", page_num, len(rows))
                all_tenders.extend(rows)

                if len(rows) < 12:
                    logger.info("  last page reached")
                    break

                # delay between pages
                time.sleep(self.delay_sec)
        finally:
            self.close()

        # dedupe
        seen = set()
        unique: list[dict] = []
        for t in all_tenders:
            key = t.get("source_uuid") or t.get("link")
            if key and key not in seen:
                seen.add(key)
                unique.append(t)

        logger.info("MarchesPublics: %d unique tenders", len(unique))
        return unique
