import pytest

from crawlers.base_crawler import BaseCrawler, sanitize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  https://ade.dz/appels/offres  ", "https://ade.dz/appels/offres"),
        ("https://ade.dz\t/appels", "https://ade.dz/appels"),
        ("https://ade.dz/appels\u200b/page", "https://ade.dz/appels/page"),
        ('"https://ade.dz/a b"', "https://ade.dz/ab"),
        ("https://ade.dz/appels.", "https://ade.dz/appels"),
        ("HTTPS://ADE.DZ/Appels", "https://ade.dz/Appels"),
        ("ade.dz/appels", "https://ade.dz/appels"),
        ("https://ade.dz//a///b", "https://ade.dz/a/b"),
        ("https://ade.dz/ملف", "https://ade.dz/%D9%85%D9%84%D9%81"),
        ("https://ade.dz/a%20b", "https://ade.dz/a%20b"),
        ("https://ade.dz/a%2fb", "https://ade.dz/a%2Fb"),
        ("https://ade.dz/p?a=b c&d=é", "https://ade.dz/p?a=bc&d=%C3%A9"),
    ],
)
def test_sanitize_url_cleans_and_encodes(raw, expected):
    assert sanitize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["javascript:void(0)", "JavaScript:alert(1)", "data:text/html;base64,AAA", "mailto:a@b.dz"],
)
def test_sanitize_url_blocks_unsupported_schemes(raw):
    assert sanitize_url(raw) == ""


@pytest.mark.parametrize("raw", ["", "   ", None, 123])
def test_sanitize_url_returns_empty_for_invalid_input(raw):
    assert sanitize_url(raw) == ""


def test_sanitize_url_rejects_unknown_http_scheme():
    assert sanitize_url("ftp://ade.dz/file") == ""


def test_sanitize_url_keeps_valid_url_unchanged():
    url = "https://www.marches-publics.gov.dz/index.php?page=appel&ref=2024/05"
    assert sanitize_url(url) == url


def test_base_crawler_exposes_sanitize_url():
    assert BaseCrawler.sanitize_url(" https://ade.dz/x ") == "https://ade.dz/x"
