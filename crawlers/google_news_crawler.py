"""google_news_crawler.py - Google News RSS aggregator."""

import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from .base_crawler import BaseCrawler, sanitize_url

logger = logging.getLogger(__name__)

SECTOR = "news_aggregator"
UNKNOWN_VALUE = "غير محدد"

#: Google News RSS feeds (AR + FR).
FEEDS = [
    "https://news.google.com/rss/search?q=%D9%85%D9%86%D8%A7%D9%82%D8%B5%D8%A9+%D8%A7%D9%84%D8%AC%D8%B2%D8%A7%D8%A6%D8%B1&hl=ar&gl=DZ&ceid=DZ:ar",
    "https://news.google.com/rss/search?q=appel+d%27offres+Alg%C3%A9rie&hl=fr&gl=DZ&ceid=DZ:fr",
    "https://news.google.com/rss/search?q=%D8%A7%D8%B3%D8%AA%D8%B4%D8%A7%D8%B1%D8%A9+%D8%B9%D9%85%D9%88%D9%85%D9%8A%D8%A9&hl=ar&gl=DZ&ceid=DZ:ar",
]

#: Keywords that indicate a tender-related news.
TENDER_KEYWORDS = [
    "مناقصة",
    "مناقصات",
    "استشارة",
    "عروض",
    "appel d'offres",
    "appel d affaires",
    "consultation",
    "tender",
    "procurement",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class GoogleNewsCrawler(BaseCrawler):
    """
    Crawler for Google News RSS.

    This crawler aggregates tender-related news from 50+ Algerian sources
    (newspapers, online media) via Google News RSS feeds. It does not
    scrape the sources directly; it consumes the public RSS API.

    Output entries are "signals" — news articles announcing tenders —
    not official tender notices. Use as early-warning indicators.
    """

    def __init__(self, base_url="https://news.google.com"):
        super().__init__(sanitize_url(base_url))

    def fetch_feed(self, url):
        """Fetch one RSS feed."""
        try:
            headers = {"User-Agent": USER_AGENT}
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            logger.error("RSS fetch error for %s: %s", url, e)
            return None

    @staticmethod
    def _is_tender_related(text):
        """Check if the text contains a tender keyword."""
        if not text:
            return False
        lower = text.lower()
        return any(kw.lower() in lower for kw in TENDER_KEYWORDS)

    def _parse_item(self, item):
        """Parse one <item> element -> tender dict, or None."""
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        source_el = item.find("source")

        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        source = (source_el.text or "").strip() if source_el is not None else ""

        if not title or not link:
            return None

        # فلترة مبدئية: فقط الأخبار المتعلقة بالمناقصات
        if not self._is_tender_related(title):
            return None

        # اطرح "- source" من نهاية العنوان
        if source and title.endswith(f"- {source}"):
            title = title[: -(len(source) + 2)].strip()

        # تاريخ النشر
        pub_date = None
        if pub_el is not None and pub_el.text:
            try:
                dt = parsedate_to_datetime(pub_el.text)
                pub_date = dt.date().isoformat()
            except (ValueError, TypeError):
                pub_date = None

        return {
            "title": title,
            "link": link,
            "reference": None,
            "organisation": source or UNKNOWN_VALUE,
            "wilaya": "",
            "product": UNKNOWN_VALUE,
            "deadline": UNKNOWN_VALUE,
            "status": UNKNOWN_VALUE,
            "published_date": pub_date,
            "pdf_url": None,
            "source": SECTOR,
        }

    def parse_feed(self, xml_text):
        """Parse RSS XML -> list of tenders."""
        if not xml_text:
            return []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("RSS parse error: %s", e)
            return []

        items = root.findall(".//item")
        tenders = []
        for item in items:
            t = self._parse_item(item)
            if t:
                tenders.append(t)
        return tenders

    def run(self):
        """Fetch all feeds + parse. Deduplicate by title."""
        all_tenders = []
        for feed_url in FEEDS:
            logger.info("GoogleNews feed: %s", feed_url[:60])
            xml = self.fetch_feed(feed_url)
            tenders = self.parse_feed(xml)
            logger.info("  parsed %d tender-related", len(tenders))
            all_tenders.extend(tenders)

        # إزالة التكرار حسب العنوان
        seen = set()
        unique = []
        for t in all_tenders:
            key = t["title"].lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(t)

        logger.info("GoogleNews: extracted %d unique tenders", len(unique))
        return unique
