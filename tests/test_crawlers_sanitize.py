from urllib.parse import urljoin

from crawlers.ade_crawler import ADECrawler
from crawlers.algeria_tenders_crawler import AlgeriaTendersCrawler
from crawlers.base_crawler import sanitize_url
from crawlers.marches_publics_crawler import MarchesPublicsCrawler
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

ADE_RAW_HREF = "/appels d'offres/  tuyaux pvc  "
ADE_HTML = (
    '<div class="tender-item">'
    "<h3>Fourniture de tuyaux PVC</h3>"
    f'<a href="{ADE_RAW_HREF}">detail</a>'
    '<span class="date">2026-10-01</span>'
    "</div>"
    '<div class="tender-item">'
    '<a href="javascript:void(0)">Fourniture de conduites PVC</a>'
    '<span class="date">2026-10-02</span>'
    "</div>"
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


def test_ade_crawler_passes_links_through_sanitize_url():
    """رابط ADE يُنظَّف، والصفقة التي رابطها javascript تُحذف كلياً."""
    crawler = ADECrawler()

    tenders = crawler.parse_tenders(ADE_HTML)

    assert len(tenders) == 1
    assert tenders[0]["title"] == "Fourniture de tuyaux PVC"
    _assert_is_sanitized(tenders[0]["link"], crawler.base_url, ADE_RAW_HREF)


def test_ade_crawler_falls_back_to_base_url_when_item_has_no_link():
    """صفقة ADE بلا رابط تأخذ رابط المصدر النظيف بدل رابط فارغ."""
    crawler = ADECrawler()
    html = '<div class="tender-item"><h3>Fourniture de citernes</h3></div>'

    tenders = crawler.parse_tenders(html)

    assert len(tenders) == 1
    assert tenders[0]["link"] == crawler.base_url


def test_marches_publics_crawler_sanitizes_base_url_and_reference_link():
    """رابط المصدر ورابط البيانات المرجعية يمرّان على sanitize_url."""
    crawler = MarchesPublicsCrawler("https://www.marches-publics.gov.dz//  ")

    assert crawler.base_url == "https://www.marches-publics.gov.dz/"

    tenders = crawler.run()

    assert len(tenders) == 1
    assert tenders[0]["link"] == sanitize_url(tenders[0]["link"])
    assert " " not in tenders[0]["link"]
