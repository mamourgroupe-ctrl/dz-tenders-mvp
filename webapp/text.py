"""Arabic-aware text normalisation, slugs and formatting helpers.

Search must be tolerant of the spelling variants that Algerian procurement
documents mix freely: ``أ/إ/آ/ا``, ``ى/ي``, ``ة/ه``, ``ؤ/و``, ``ئ/ي``,
diacritics, tatweel, Arabic-Indic digits and French accents. The normaliser is
used symmetrically when indexing and when querying, which is what makes FTS5
results predictable.
"""

from __future__ import annotations

import re
import unicodedata

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_TATWEEL = "\u0640"
_COMBINING_MARKS = re.compile(r"[\u0300-\u036f]")
_NON_WORD = re.compile(r"[^\w]+", flags=re.UNICODE)
_WHITESPACE = re.compile(r"\s+", flags=re.UNICODE)
_MULTI_HYPHEN = re.compile(r"-{2,}")
_SLUG_KEEP = re.compile(r"[^\w\u0600-\u06ff-]+", flags=re.UNICODE)
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_ARABIC_TRANSLATION = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ئ": "ي",
        "ؤ": "و",
        "ة": "ه",
    }
)

LATIN_TRANSLITERATION = str.maketrans(
    {
        "à": "a",
        "â": "a",
        "ä": "a",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ç": "c",
        "œ": "oe",
        "æ": "ae",
        "ñ": "n",
    }
)


def normalize_arabic(text: str) -> str:
    """Fold Arabic spelling variants into one canonical form.

    The output is *not* meant for display: ``ة`` becomes ``ه`` and diacritics
    disappear. It is safe to store in the search index and to match queries.
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    value = value.translate(_ARABIC_DIGITS)
    value = value.replace(_TATWEEL, "")
    value = unicodedata.normalize("NFKD", value)
    # Decomposition turns ``أ`` into ``ا`` + a combining hamza, so the
    # Arabic marks must be stripped *after* NFKD as well.
    value = _COMBINING_MARKS.sub("", value)
    value = _ARABIC_DIACRITICS.sub("", value)
    value = value.translate(_ARABIC_TRANSLATION)
    value = value.casefold()
    value = _NON_WORD.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip()


def normalize_search(text: str) -> str:
    """Alias used by search code; keeps one documented entry point."""
    return normalize_arabic(text)


def fold_latin(text: str) -> str:
    """Lowercase Latin text and strip accents, preserving Arabic letters."""
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", str(text))
    value = _COMBINING_MARKS.sub("", value)
    return _WHITESPACE.sub(" ", value.casefold()).strip()


def search_tokens(text: str) -> list[str]:
    """Normalise then split into searchable tokens (length >= 1)."""
    return [token for token in normalize_search(text).split(" ") if token]


#: Minimum token length before the Arabic definite article is probed.
_ARTICLE_MIN = 3


def search_token_variants(token: str) -> list[str]:
    """Return the token plus its optional ``ال`` (definite article) variant.

    Arabic writes the article attached to the noun (``المياه``), while users
    often type the bare form (``مياه``). Matching both directions keeps recall
    high without a full morphological analyser.
    """
    variants = [token]
    is_arabic = any("\u0600" <= char <= "\u06ff" for char in token)
    if not is_arabic:
        return variants
    if token.startswith("ال") and len(token) > _ARTICLE_MIN + 1:
        variants.append(token[2:])
    elif len(token) >= _ARTICLE_MIN:
        variants.append(f"ال{token}")
    return variants


def build_fts_query(text: str, *, mode: str = "and") -> str:
    """Build a safe FTS5 MATCH expression from user text.

    Each token becomes a quoted prefix term. All quote/operator characters are
    removed by normalisation, so the result cannot inject FTS syntax.

    Args:
        text: Raw user query.
        mode: ``and`` (all tokens) or ``or`` (any token).

    Returns:
        A MATCH expression, or an empty string when nothing remains.
    """
    tokens = search_tokens(text)
    if not tokens:
        return ""
    joiner = " OR " if mode == "or" else " AND "
    groups = []
    for token in tokens[:8]:
        parts = [f'"{variant}"*' for variant in search_token_variants(token)]
        groups.append(f"({parts[0]})" if len(parts) == 1 else f"({' OR '.join(parts)})")
    return joiner.join(groups)


def build_tsquery(text: str) -> str:
    """Build a PostgreSQL ``to_tsquery`` expression from user text.

    Tokens are already normalised by :func:`normalize_search`, so only word
    characters reach the expression. Each token is a prefix match with an
    optional definite-article variant.
    """
    tokens = search_tokens(text)
    if not tokens:
        return ""
    groups = []
    for token in tokens[:8]:
        parts = [f"{variant}:*" for variant in search_token_variants(token)]
        groups.append(f"({' | '.join(parts)})")
    return " & ".join(groups)


def slugify(text: str, fallback: str = "annonce", max_length: int = 90) -> str:
    """Create a URL-safe slug that preserves Arabic letters.

    Latin input is transliterated to ASCII punctuation-free words; Arabic is
    kept as-is because Arabic slugs are the requirement (and are perfectly
    valid in IRIs). The result never starts or ends with a hyphen.

    Args:
        text: Title or name.
        fallback: Used when the input has no usable characters.
        max_length: Maximum slug length (truncated at a word boundary).
    """
    if not text:
        return fallback
    value = unicodedata.normalize("NFKC", str(text)).translate(_ARABIC_DIGITS)
    value = value.translate(_ARABIC_TRANSLATION)
    value = _ARABIC_DIACRITICS.sub("", value).replace(_TATWEEL, "")
    value = value.translate(LATIN_TRANSLITERATION)
    value = unicodedata.normalize("NFKD", value)
    value = _COMBINING_MARKS.sub("", value)
    value = _SLUG_KEEP.sub("-", value.casefold())
    value = _MULTI_HYPHEN.sub("-", value).strip("-_")
    if len(value) > max_length:
        value = value[:max_length].rsplit("-", 1)[0].strip("-")
    return value or fallback


def truncate_words(text: str, limit: int = 160, suffix: str = "…") -> str:
    """Truncate at a word boundary without cutting HTML (caller escapes)."""
    if not text:
        return ""
    clean = _WHITESPACE.sub(" ", str(text)).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rsplit(" ", 1)[0].rstrip("،.,;")
    return f"{cut}{suffix}"


def escape_like(term: str) -> str:
    """Escape ``LIKE`` wildcards for a literal substring fallback."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def format_dzd(amount: int | None) -> str:
    """Format an integer amount in Algerian dinars."""
    if amount is None:
        return "—"
    return f"{amount:,}".replace(",", " ") + " دج"


def mask_phone(phone: str) -> str:
    """Mask a phone number for account screens."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 4:
        return "—"
    return f"•••• {digits[-3:]}"


__all__ = [
    "build_fts_query",
    "escape_like",
    "fold_latin",
    "format_dzd",
    "mask_phone",
    "normalize_arabic",
    "normalize_search",
    "search_tokens",
    "slugify",
    "truncate_words",
]
