import logging
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


class ADECrawler(BaseCrawler):
    """
    كلاس خاص بجلب المناقصات من موقع ADE (Algérienne Des Eaux).
    """

    def __init__(self, base_url="https://www.ade.dz"):
        super().__init__(sanitize_url(base_url))

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

            tenders.append(
                {
                    "title": title,
                    "link": link,
                    "organisation": ADE_ORGANISATION,
                    "wilaya": "",
                    "product": UNKNOWN_VALUE,
                    "deadline": UNKNOWN_VALUE,
                    "status": UNKNOWN_VALUE,
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

    def run(self):
        logger.info(f"بدء عملية جلب المناقصات من: {self.listing_url}")
        html = self.fetch_page(self.listing_url)
        if html:
            results = self.parse_tenders(html)
            logger.info(f"تم استخراج {len(results)} مناقصة بنجاح.")
            return results

        logger.warning("لم يتم الحصول على أي بيانات.")
        return []
