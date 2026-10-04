import logging
import re
import unicodedata
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base_crawler import BaseCrawler, sanitize_url

logger = logging.getLogger(__name__)

#: صنف بطاقة طلب العروض في صفحة ``categorie/appel-doffres``.
#:
#: كان الكود يبحث عن ``div.tender-item`` وهو صنف **غير موجود** في موقع ADE،
#: فلم يكن الكرولر يُخرج أي مناقصة إطلاقاً. الصفحة الجذرية ``ade.dz`` موقع
#: مؤسسي بلا قائمة مناقصات، والقائمة تُبنى في مسار التصنيف أدناه.
CARD_CLASS = "service-block-two"

#: مسار صفحة طلبات العروض داخل الموقع (وليس الصفحة الجذرية).
LISTING_PATH = "categorie/appel-doffres"

#: الجهة الناشررة — ADE هي الناشر نفسه، فهذه قيمة ثابتة **صادقة** لا مفترضة،
#: بخلاف ``wilaya`` و``product`` التي لا تظهر في صفحة القائمة.
ADE_ORGANISATION = "Algérienne des Eaux (ADE)"

#: القيمة الصادقة عند غياب المعلومة من صفحة القائمة.
#: تُكتب صراحةً بدل ترك الخلية فارغة، ليعرف القارئ أن المعلومة غير منشورة
#: لا أنها فشلت في الاستخراج.
UNKNOWN_VALUE = "غير محدد"

#: سنة النشر من الرابط.
SLUG_YEAR_RE = re.compile(r"n-\d{1,2}-(20\d{2})", re.IGNORECASE)

TITLE_YEAR_RE = re.compile(r"n[°o]?\s*\d{1,2}\s*-\s*(20\d{2})", re.IGNORECASE)

REFERENCE_YEAR_RE = TITLE_YEAR_RE

POST_DATE_RE = re.compile(
    r'<div class="post-date">\s*<h5>\s*(?:[a-z]+\s+)?([a-zA-Zéûôçà]{3,10})\s+(\d{4})\s*</h5>',
    re.IGNORECASE,
)

FRENCH_MONTHS = {
    "jan": 1, "fev": 2, "avr": 4, "mai": 5, "jui": 6, "jul": 7,
    "aou": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _fold(text: str) -> str:
    """تصغير النص مع إزالة الحركات."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


class ADECrawler(BaseCrawler):
    """
    كلاس خاص بجلب المناقصات من موقع ADE (Algérienne Des Eaux).
    """

    def __init__(self, base_url="https://www.ade.dz"):
        super().__init__(sanitize_url(base_url))
        self._detail_dates: dict[str, date | None] = {}

    @property
    def listing_url(self) -> str:
        """رابط صفحة طلبات العروض.

        ``base_url`` يبقى جذر الموقع لأنه يُستخدم في حلّ الروابط النسبية
        (``../article/...``) وفي رابط الاحتياط.
        """
        return urljoin(self.base_url, LISTING_PATH)

    def fetch_page(self, url):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            # العناوين الفرنسية فيها ’ و é، وتخمين requests للترميز ينتج نصاً مشوهاً.
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException as e:
            logger.error(f"خطأ أثناء الاتصال بالموقع {url}: {e}")
            return None

    def parse_tenders(self, html_content):
        """استخراج المناقصات من HTML مع تنظيف رابط كل صفقة.

        صفحة القائمة تنشر العنوان والرابط فقط. لذلك:

        - ``organisation`` ثابتة صادقة: ADE هي الناشر.
        - ``wilaya`` تُترك فارغة عمداً؛ ``tender_filter.classify_tender``
          يستنتجها من العنوان ويملؤها قبل توليد التقرير، فلا داعي لتكرار المنطق.
        - ``product`` و``deadline`` و``status`` لا تظهر في القائمة إطلاقاً،
          فتُكتب ``UNKNOWN_VALUE`` بدل اختلاق قيمة.

        الحقل ``date`` لم يكن موجوداً في الموقع إطلاقاً، وقد حُذف: كان ينتج
        عموداً إنجليزياً (``date``) لا وجود له في ``COLUMNS_MAPPING``.

        Args:
            html_content: محتوى صفحة طلبات العروض بعد الجلب.

        Returns:
            قائمة من القواميس تضم ``title`` و``link`` و``organisation``
            و``wilaya`` و``product`` و``deadline`` و``status``.
        """
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        tenders = []

        for card in soup.find_all("div", class_=CARD_CLASS):
            title = self._card_title(card)
            anchor = card.select_one("h3 a[href]") or card.find("a", href=True)

            link = sanitize_url(urljoin(self.base_url, anchor["href"])) if anchor else self.base_url
            if not link:
                continue

            href = anchor["href"] if anchor else ""
            slug = href.rstrip("/").rsplit("/", 1)[-1]
            published = self._published_date(slug, title, link if href else None)

            tenders.append(
                {
                    "title": title,
                    "link": link,
                    "organisation": ADE_ORGANISATION,
                    "wilaya": "",
                    "product": UNKNOWN_VALUE,
                    "deadline": UNKNOWN_VALUE,
                    "status": UNKNOWN_VALUE,
                    "published_date": published.isoformat() if published else None,
                }
            )

        return tenders

    @staticmethod
    def _card_title(card) -> str:
        """استخراج عنوان البطاقة.

        البنية الحقيقية تضع الرابط داخل ``h3``، لكن صفحات أخرى تضعه شقيقاً
        لـ``h3``، و``img[alt]`` يحمل العنوان أيضاً. يُجرَّب الثلاثة بالترتيب.
        """
        heading = card.select_one("h3 a")
        if heading is not None:
            text = heading.get_text(strip=True)
            if text:
                return text

        bare_heading = card.find("h3")
        if bare_heading is not None:
            text = bare_heading.get_text(strip=True)
            if text:
                return text

        image = card.select_one("figure.image-box img[alt]")
        if image is not None:
            return image.get("alt", "").strip()

        return "بدون عنوان"


    def _year_from_reference(self, slug: str, title: str) -> int | None:
        """سنة النشر من الرابط أو العنوان."""
        for pattern, text in ((SLUG_YEAR_RE, slug), (TITLE_YEAR_RE, title)):
            match = pattern.search(text or "")
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _published_from_detail(html: str) -> date | None:
        """تاريخ النشر من صفحة التفاصيل."""
        if not html:
            return None
        match = POST_DATE_RE.search(html)
        if match:
            month = FRENCH_MONTHS.get(_fold(match.group(1))[:3])
            if month:
                return date(int(match.group(2)), month, 1)
        match = REFERENCE_YEAR_RE.search(html)
        if match:
            return date(int(match.group(1)), 1, 1)
        return None

    def _published_date(self, slug: str, title: str, detail_url: str | None) -> date | None:
        """تاريخ النشر من الرابط، ثم التفاصيل."""
        year = self._year_from_reference(slug, title)
        if year:
            return date(year, 1, 1)
        if not detail_url:
            return None
        if detail_url not in self._detail_dates:
            try:
                html = self.fetch_page(detail_url)
            except Exception:
                html = None
            self._detail_dates[detail_url] = self._published_from_detail(html)
        return self._detail_dates[detail_url]

    def run(self):
        logger.info(f"بدء عملية جلب المناقصات من: {self.listing_url}")
        html = self.fetch_page(self.listing_url)
        if html:
            results = self.parse_tenders(html)
            logger.info(f"تم استخراج {len(results)} مناقصة بنجاح.")
            return results

        logger.warning("لم يتم الحصول على أي بيانات.")
        return []
