"""Shared quality checks for records entering the tenders table."""

import os
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

MIN_TENDER_RELEVANCE_SCORE = 3
_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")
_UNKNOWN_VALUES = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "غير محدد",
    "غير معروف",
}


def _has_value(value: Any) -> bool:
    """Return whether a field contains a meaningful non-placeholder value."""
    if value is None:
        return False
    if isinstance(value, datetime | date):
        return True
    text = str(value).strip().casefold()
    return text not in _UNKNOWN_VALUES


def _has_deadline(value: Any) -> bool:
    """Return whether a deadline contains a valid ISO date."""
    if isinstance(value, datetime | date):
        return True
    if not isinstance(value, str):
        return False
    match = _DATE_PREFIX.match(value.strip())
    if not match:
        return False
    try:
        date.fromisoformat(match.group())
    except ValueError:
        return False
    return True


def _allow_news_as_tenders() -> bool:
    """Read the opt-in allowing news articles into the tender pipeline."""
    return os.getenv("ALLOW_NEWS_AS_TENDERS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_news_tender(tender: dict[str, Any]) -> bool:
    """Detect RSS news using its persisted source marker or Google News URL."""
    source = str(tender.get("source") or "").strip().casefold()
    if source == "news_aggregator":
        return True
    link = str(tender.get("link") or "").strip()
    try:
        return urlparse(link).hostname == "news.google.com"
    except ValueError:
        return False


def is_valid_tender(tender: dict[str, Any]) -> bool:
    """Check minimum evidence and relevance before storing or sending a tender."""
    if is_news_tender(tender) and not _allow_news_as_tenders():
        return False

    try:
        score = int(tender.get("relevance_score") or 0)
    except (TypeError, ValueError):
        return False
    if score < MIN_TENDER_RELEVANCE_SCORE:
        return False

    evidence = _has_deadline(tender.get("deadline")) or any(
        _has_value(tender.get(field))
        for field in ("reference", "tender_number", "reference_number")
    ) or any(
        _has_value(tender.get(field))
        for field in ("contracting_authority", "organisation", "organization")
    )
    return evidence
