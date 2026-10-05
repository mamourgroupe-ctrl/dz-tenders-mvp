"""email_sender.py - SMTP email sender for daily digests."""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def is_email_configured() -> bool:
    """Check whether SMTP env vars are present."""
    required = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO")
    return all(os.getenv(k) for k in required)


def send_digest_email(
    html_body: str,
    subject: str,
    to_addrs: list[str] | None = None,
) -> bool:
    """Send HTML digest via SMTP.

    Config from env:
        SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD,
        SMTP_FROM (default = SMTP_USER), DIGEST_TO (comma-separated).

    Returns:
        True on success, False otherwise.
    """
    if not is_email_configured() and not to_addrs:
        logger.warning("SMTP not configured and no to_addrs given; skipping")
        return False

    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM") or user

    if to_addrs is None:
        to_addrs = [a.strip() for a in os.getenv("DIGEST_TO", "").split(",") if a.strip()]

    if not to_addrs:
        logger.warning("No recipients; skipping")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.set_content("Please view this email in HTML mode.")
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
        logger.info("Digest email sent to %s", to_addrs)
        return True
    except Exception as e:
        logger.error("SMTP send failed: %s", type(e).__name__)
        return False
