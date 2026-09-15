"""
crawlers/smart_crawler.py
Smart crawler for sources from sources_master.json
"""

import requests
import logging
import unicodedata
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from .base_crawler import BaseCrawler

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SmartCrawler(BaseCrawler):
    """Smart crawler with keyword detection"""

    KEYWORDS = [
        "pvc", "pehd", "polyéthylène", "polyethylene",
        "tuyau", "tuyaux", "conduite", "conduites", "raccord",
        "canalisation", "réservoir", "reservoir", "citerne",
        "cuve", "tank",
        "نابيب", "نبوب", "خزانات", "خزان", "قنوات", "قناة",
        "بلاستيك", "بولي يثيلين", "صرف", "ري",
        "eau", "assainissement", "irrigation", "adduction",
        "مياه", "تطهير", "سقي",
    ]

    def __init__(self, source_name: str, base_url: str, priority: str = "1"):
        super().__init__(base_url)
        self.source_name = source_name
        self.priority = priority

    def _normalize(self, text: str) -> str:
        if not text:
            return ""
        return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8").lower().strip()

    def _fetch(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ar,fr;q=0.9,en;q=0.8",
        }
        try:
            r = requests.get(url, headers=headers, timeout=20, verify=False)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text if r.status_code == 200 else ""
        except Exception as e:
            logging.debug(f"{self.source_name}: {type(e).__name__}")
            return ""

    def run(self):
        logging.info(f"SmartCrawler: {self.source_name}")
        html = self._fetch(self.base_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        tenders = []
        seen = set()

        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            if not text or len(text) < 15:
                continue

            norm = self._normalize(text)
            if not any(kw in norm for kw in self.KEYWORDS):
                continue

            href = link["href"]
            if href.startswith("javascript") or href == "#":
                continue

            full_link = urljoin(self.base_url, href)
            if full_link in seen:
                continue
            seen.add(full_link)

            tenders.append({
                "title": text[:200],
                "organisation": self.source_name,
                "wilaya": "غير محددة",
                "product": "PE/PEHD/PVC",
                "deadline": "غير محدد",
                "status": "مفتوحة",
                "link": full_link,
            })

        logging.info(f"  -> {len(tenders)} tenders from {self.source_name}")
        return tenders
