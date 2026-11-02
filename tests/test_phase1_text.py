"""Arabic normalisation, slugs and search-query safety."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta

import pytest

from webapp.text import (
    build_fts_query,
    escape_like,
    format_dzd,
    normalize_arabic,
    normalize_search,
    search_tokens,
    slugify,
    truncate_words,
)
from webapp.timeutils import deadline_label, format_date_ar


@pytest.mark.parametrize(
    "variant",
    [
        "أنابيب المياه",
        "انابيب المياه",
        "أَنَابِيبُ المِيَاه",
        "انابيب المياه",
        "أنـابيب المياه",
    ],
)
def test_hamza_diacritics_and_tatweel_fold_to_one_form(variant: str) -> None:
    assert normalize_arabic(variant) == "انابيب المياه"


def test_ta_marbuta_and_alef_maqsura_are_folded() -> None:
    assert normalize_arabic("إدارة") == normalize_arabic("اداره")
    assert normalize_arabic("مستشفى") == normalize_arabic("مستشفي")


def test_arabic_indic_digits_are_ascii() -> None:
    assert normalize_arabic("١٢٣٤٥") == "12345"


def test_latin_accents_and_punctuation() -> None:
    assert (
        normalize_arabic("Étude technique, PVC-U/PEHD") == "etude technique pvc u pehd"
    )


def test_empty_text_normalises_to_empty() -> None:
    assert normalize_arabic("") == ""
    assert normalize_search(None) == ""  # type: ignore[arg-type]


def test_search_tokens_drop_punctuation() -> None:
    assert search_tokens("خزانات 1000 لتر!") == ["خزانات", "1000", "لتر"]


def test_fts_query_is_prefix_and_uses_and() -> None:
    query = build_fts_query("أنابيب مياه")
    assert query == '"انابيب"* AND "مياه"*'


def test_fts_query_removes_operators_and_quotes() -> None:
    query = build_fts_query('PVC " OR * NEAR(')
    assert '"' in query
    assert query.count('"') % 2 == 0
    assert " OR " not in query
    assert query.count("AND") >= 1


def test_fts_query_empty_and_capped() -> None:
    assert build_fts_query("   ") == ""
    capped = build_fts_query(" ".join(f"كلمة{i}" for i in range(12)))
    assert capped.count("AND") == 7


def test_slugify_keeps_arabic_and_removes_combining_marks() -> None:
    slug = slugify("اقتناء أنابيب PVC — مياه الشرب")
    assert " " not in slug
    assert "pvc" in slug
    assert not any(unicodedata.combining(char) for char in slug)
    assert not slug.startswith("-") and not slug.endswith("-")
    assert "--" not in slug


def test_slugify_fallback_and_truncation() -> None:
    assert slugify("!!!", fallback="annonce") == "annonce"
    long_slug = slugify("كلمة " * 40)
    assert len(long_slug) <= 90


def test_escape_like_escapes_wildcards() -> None:
    assert escape_like("100%_test\\") == "100\\%\\_test\\\\"


def test_truncate_words_and_dzd() -> None:
    assert truncate_words("كلمة " * 100, limit=20).endswith("…")
    assert format_dzd(12500) == "12 500 دج"
    assert format_dzd(None) == "—"


def test_deadline_label() -> None:
    now = datetime(2026, 11, 2, 12, 0)
    assert deadline_label(now + timedelta(days=3), now=now) == "باقٍ 3 أيام"
    assert deadline_label(now, now=now) == "ينتهي اليوم"
    assert deadline_label(now - timedelta(days=1), now=now) == "انتهى الأجل"
    assert deadline_label(None, now=now) == "أجل غير محدد"


def test_format_date_ar_uses_arabic_months() -> None:
    assert format_date_ar(datetime(2026, 10, 12)) == "12 أكتوبر 2026"
