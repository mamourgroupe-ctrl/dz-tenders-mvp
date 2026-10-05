"""Tests for notifications/email_sender.py."""

from unittest.mock import MagicMock, patch

from notifications.email_sender import is_email_configured, send_digest_email


def test_is_configured_false_when_env_missing(monkeypatch):
    """No env vars -> False."""
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO"):
        monkeypatch.delenv(k, raising=False)
    assert is_email_configured() is False


def test_is_configured_true_when_all_set(monkeypatch):
    """All env vars set -> True."""
    monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
    monkeypatch.setenv("SMTP_USER", "u@test.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("DIGEST_TO", "a@test.com")
    assert is_email_configured() is True


def test_send_returns_false_when_not_configured(monkeypatch):
    """Not configured + no to_addrs -> False."""
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO"):
        monkeypatch.delenv(k, raising=False)
    result = send_digest_email("<html></html>", "Test")
    assert result is False


def test_send_success(monkeypatch):
    """Successful send -> True."""
    monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "u@test.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("DIGEST_TO", "a@test.com")

    mock_smtp = MagicMock()
    with patch("smtplib.SMTP") as smtp_cls:
        smtp_cls.return_value.__enter__.return_value = mock_smtp
        result = send_digest_email("<html></html>", "Subject")

    assert result is True
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("u@test.com", "secret")
    mock_smtp.send_message.assert_called_once()


def test_send_failure_returns_false(monkeypatch):
    """SMTP exception -> False."""
    monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
    monkeypatch.setenv("SMTP_USER", "u@test.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("DIGEST_TO", "a@test.com")

    with patch("smtplib.SMTP", side_effect=Exception("boom")):
        result = send_digest_email("<html></html>", "Subject")

    assert result is False
