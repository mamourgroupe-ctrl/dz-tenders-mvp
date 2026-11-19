"""Offline tests: legacy crawlers must validate TLS certificates (SEC-01)."""

from unittest.mock import MagicMock

import pytest
import requests

from crawlers.algeria_tenders_crawler import AlgeriaTendersCrawler
from crawlers.smart_crawler import SmartCrawler


def _ok_response(text: str = "<html></html>") -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.text = text
    response.apparent_encoding = "utf-8"
    return response


def _smart_fetch(crawler: SmartCrawler):
    return crawler._fetch("https://example.dz/")


def _algeria_fetch(crawler: AlgeriaTendersCrawler):
    return crawler.fetch_page("https://example.dz/")


CASES = [
    pytest.param(
        lambda: SmartCrawler("test", "https://example.dz/"),
        "crawlers.smart_crawler.requests.get",
        _smart_fetch,
        "",
        id="smart",
    ),
    pytest.param(
        lambda: AlgeriaTendersCrawler("https://example.dz/"),
        "crawlers.algeria_tenders_crawler.requests.get",
        _algeria_fetch,
        None,
        id="algeria",
    ),
]


@pytest.mark.parametrize(("factory", "target", "fetch", "_empty"), CASES)
def test_requests_do_not_disable_tls_verification(
    monkeypatch, factory, target, fetch, _empty
):
    """No request may pass verify=False."""
    mock_get = MagicMock(return_value=_ok_response())
    monkeypatch.setattr(target, mock_get)

    fetch(factory())

    assert mock_get.call_args.kwargs.get("verify", True) is not False


@pytest.mark.parametrize(("factory", "target", "fetch", "empty"), CASES)
def test_ssl_error_returns_empty_and_logs_warning(
    monkeypatch, caplog, factory, target, fetch, empty
):
    """An invalid certificate yields the crawler's empty value and a warning."""
    monkeypatch.setattr(
        target, MagicMock(side_effect=requests.exceptions.SSLError("bad cert"))
    )

    with caplog.at_level("WARNING"):
        result = fetch(factory())

    assert result == empty
    assert any(
        "TLS" in record.getMessage() and record.levelname == "WARNING"
        for record in caplog.records
    )
