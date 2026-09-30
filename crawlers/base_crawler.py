import logging
import re
from urllib.parse import quote, urlsplit, urlunsplit

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+", flags=re.UNICODE)
_TRAILING_JUNK_RE = re.compile(r"[.,;]+$")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_ESCAPE_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_MULTI_SLASH_RE = re.compile(r"/{2,}")

ALLOWED_SCHEMES = ("http", "https")
BLOCKED_SCHEMES = ("javascript:", "data:", "vbscript:", "file:", "about:", "mailto:")

_PATH_SAFE = "/:@!$&'()*+,;=-._~"
_QUERY_SAFE = "/?:@!$&'()*+,;=-._~"
_NETLOC_SAFE = ":@!$&'()*+,;=-._~[]"


def _encode_component(component: str, safe: str) -> str:
    """ترميز محارف الجزء المحدد مع الحفاظ على التسلسلات المرمّزة مسبقاً."""
    if not component:
        return component
    pieces = []
    cursor = 0
    for match in _ESCAPE_RE.finditer(component):
        pieces.append(quote(component[cursor : match.start()], safe=safe))
        pieces.append(match.group(0).upper())
        cursor = match.end()
    pieces.append(quote(component[cursor:], safe=safe))
    return "".join(pieces)


def sanitize_url(url: str) -> str:
    """تنظيف رابط ويب من المسافات الزائدة والمحارف غير الصالحة.

    تُحذف محارف التحكم والمسافات (بما فيها غير المرئية)، وتُزال علامات الاقتباس
    المحيطة، ثم يُرمّز كل جزء وفق معيار URI دون ترميز التسلسلات المئوية الموجودة
    مسبقاً. الروابط ذات المخططات غير المدعومة (مثل ``javascript``) تُرجع نصاً فارغاً.

    Args:
        url: الرابط الخام القادم من صفحة HTML.

    Returns:
        الرابط بعد التنظيف، أو نص فارغ إذا كان غير قابل للاستخدام.
    """
    if not isinstance(url, str):
        return ""

    cleaned = _CONTROL_CHARS_RE.sub("", url)
    cleaned = _WHITESPACE_RE.sub("", cleaned).strip().strip("\"'`<>{}|\\^")
    cleaned = _TRAILING_JUNK_RE.sub("", cleaned)
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    if lowered.startswith(BLOCKED_SCHEMES):
        return ""

    scheme_match = _SCHEME_RE.match(cleaned)
    if scheme_match and scheme_match.group(0)[:-1].lower() not in ALLOWED_SCHEMES:
        return ""

    if not scheme_match:
        cleaned = "https://" + cleaned.lstrip("/")

    parts = urlsplit(cleaned)
    netloc = _encode_component(parts.netloc.lower(), _NETLOC_SAFE)
    path = _MULTI_SLASH_RE.sub("/", _encode_component(parts.path, _PATH_SAFE))
    query = _encode_component(parts.query, _QUERY_SAFE)
    fragment = _encode_component(parts.fragment, _QUERY_SAFE)

    return urlunsplit((parts.scheme.lower(), netloc, path, query, fragment))


class BaseCrawler:
    """
    الكلاس الأساسي (Base Class) لجميع الكرولرز في المشروع
    """

    def __init__(self, base_url):
        self.base_url = base_url

    @staticmethod
    def sanitize_url(url: str) -> str:
        """نفس سلوك ``crawlers.base_crawler.sanitize_url`` كطريقة على الكلاس."""
        return sanitize_url(url)

    def fetch_page(self, url):
        raise NotImplementedError("يجب تطبيق هذه الدالة في الكلاس الفرعي")

    def parse_tenders(self, html_content):
        raise NotImplementedError("يجب تطبيق هذه الدالة في الكلاس الفرعي")

    def run(self):
        raise NotImplementedError("يجب تطبيق هذه الدالة في الكلاس الفرعي")
