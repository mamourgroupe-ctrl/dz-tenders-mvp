from urllib.parse import urljoin

from crawlers.algeria_tenders_crawler import AlgeriaTendersCrawler
from crawlers.base_crawler import sanitize_url
from crawlers.ona_crawler import ONACrawler
from crawlers.smart_crawler import SmartCrawler

ONA_RAW_HREF = "/appels d'offres/  tuyaux pvc  "
ONA_HTML = f'<a href="{ONA_RAW_HREF}">Fourniture de tuyaux PVC pour assainissement</a>'

SMART_RAW_HREF = "/marches/ appel\u200bd'offres/ tuyaux  "
SMART_HTML = (
    f'<a href="javascript:void(0)">Fourniture de tuyaux PVC pour assainissement</a>'
    f'<a href="{SMART_RAW_HREF}">Fourniture de tuyaux PVC pour assainissement</a>'
)

ALGERIA_RAW_HREF = "/appel d'offres/  tuyaux pvc  "
ALGERIA_HTML = (
    f'<a href="{ALGERIA_RAW_HREF}">'
    "Fourniture de tuyaux PVC et raccords pour le reseau d'assainissement"
    "</a>"
)


def _assert_is_sanitized(link: str, base_url: str, raw_href: str) -> None:
    """يتأكد أن الرابط نظيف وأنه ناتج sanitize_url على الرابط الخام."""
    assert link == sanitize_url(urljoin(base_url, raw_href))
    assert " " not in link
    assert "\u200b" not in link
    assert link.startswith("https://")


def test_ona_crawler_passes_links_through_sanitize_url(monkeypatch):
    """رابط ONA الفوضوي يُنظَّف قبل التخزين في المناقصة."""
    crawler = ONACrawler()
    monkeypatch.setattr(crawler, "fetch_page", lambda url: ONA_HTML)

    tenders = crawler.run()

    assert len(tenders) == 1
    _assert_is_sanitized(tenders[0]["link"], crawler.base_url, ONA_RAW_HREF)


def test_smart_crawler_passes_links_through_sanitize_url(monkeypatch):
    """روابط SmartCrawler تُنظَّف، ورابط javascript يُتخطى كلياً."""
    crawler = SmartCrawler(source_name="test", base_url="https://source.dz")
    monkeypatch.setattr(crawler, "_fetch", lambda url: SMART_HTML)

    tenders = crawler.run()

    assert len(tenders) == 1
    _assert_is_sanitized(tenders[0]["link"], crawler.base_url, SMART_RAW_HREF)


def test_algeria_tenders_crawler_passes_links_through_sanitize_url():
    """رابط AlgeriaTendersCrawler يُنظَّف قبل التخزين في المناقصة."""
    crawler = AlgeriaTendersCrawler()

    tenders = crawler.parse_tenders(ALGERIA_HTML)

    assert len(tenders) == 1
    _assert_is_sanitized(tenders[0]["link"], crawler.base_url, ALGERIA_RAW_HREF)
