"""Tests for notifications/digest.py."""

from datetime import date

from notifications.digest import build_digest_html


def _tender(title, score, **overrides):
    base = {
        "title": title,
        "link": "https://example.com",
        "organisation": "TestOrg",
        "wilaya": "Alger",
        "deadline": "2026-12-01",
        "matched_products": ["pe_tanks"],
        "relevance_score": score,
    }
    base.update(overrides)
    return base


def test_empty_tenders_yields_valid_html():
    """Empty list -> valid HTML with Total 0."""
    html = build_digest_html([], date(2026, 10, 5))
    assert "<!DOCTYPE html>" in html
    assert "Daily Digest" in html
    assert ">0<" in html or ">0\n" in html


def test_p1_tender_in_p1_table():
    """Score >= 85 -> P1."""
    html = build_digest_html([_tender("P1 test", 90)], date(2026, 10, 5))
    assert "Priority 1" in html
    assert "P1 test" in html


def test_p2_tender_in_p2_table():
    """70 <= score < 85 -> P2."""
    html = build_digest_html([_tender("P2 test", 75)], date(2026, 10, 5))
    assert "Priority 2" in html
    assert "P2 test" in html


def test_p3_tender_in_p3_table():
    """50 <= score < 70 -> P3."""
    html = build_digest_html([_tender("P3 test", 60)], date(2026, 10, 5))
    assert "Priority 3" in html
    assert "P3 test" in html


def test_below_p3_not_shown():
    """Score < 50 -> P4, not rendered."""
    html = build_digest_html([_tender("P4 test", 30)], date(2026, 10, 5))
    assert "P4 test" not in html


def test_multiple_tiers():
    """Multiple tiers render correctly."""
    tenders = [
        _tender("A", 90),
        _tender("B", 75),
        _tender("C", 60),
    ]
    html = build_digest_html(tenders, date(2026, 10, 5))
    assert "Priority 1" in html
    assert "Priority 2" in html
    assert "Priority 3" in html
    assert ">3<" in html or ">3\n" in html


def test_html_escapes_title():
    """XSS attempt in title is escaped."""
    html = build_digest_html([_tender("<script>x</script>", 90)], date(2026, 10, 5))
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_run_date_rendered():
    """Run date appears in output."""
    html = build_digest_html([], date(2026, 10, 5))
    assert "2026-10-05" in html
