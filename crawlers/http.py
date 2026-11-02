"""Shared HTTP access for crawlers with verified TLS by default.

Background: two crawlers used to call ``requests.get(..., verify=False)`` and
silenced ``InsecureRequestWarning`` globally. That made every download of a
procurement page vulnerable to interception, including the links and text that
end up published on the site.

The default here is strict certificate verification. A source may opt out only
through an explicit environment variable, which is logged every time it is used:

* ``CRAWLER_VERIFY_SSL`` — global switch, ``true`` by default.
* ``CRAWLER_VERIFY_SSL_<SOURCE>`` — per-source override, for example
  ``CRAWLER_VERIFY_SSL_SMART=false`` for a legacy host with a broken chain.
* ``CRAWLER_CA_BUNDLE`` — path to a private CA bundle, honoured when
  verification is enabled.

Disabling verification is meant as a temporary, documented workaround. The
preferred fix for a broken host is adding its CA to ``CRAWLER_CA_BUNDLE``.

No module-level warning filter is installed: disabling TLS verification stays
visible in the logs instead of being hidden.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

#: Environment variable that enables/disables verification globally.
VERIFY_ENV = "CRAWLER_VERIFY_SSL"

#: Optional path to a CA bundle used when verification is enabled.
CA_BUNDLE_ENV = "CRAWLER_CA_BUNDLE"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_warned_sources: set[str] = set()


def _source_env_key(source: str) -> str:
    """Normalise a source name into an environment-variable suffix."""
    return re.sub(r"[^A-Z0-9]+", "_", source.upper()).strip("_")


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    """Parse a permissive boolean, falling back to ``default``."""
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    logger.warning("Ignoring invalid boolean %r for TLS verification", raw)
    return default


def verify_setting(source: str | None = None) -> bool | str:
    """Return the ``requests`` ``verify`` argument for a source.

    Args:
        source: Optional crawler identifier (``algeria_tenders``, ``smart``…).
            When given, ``CRAWLER_VERIFY_SSL_<SOURCE>`` takes precedence over
            the global switch.

    Returns:
        ``True`` for default CA verification, a CA-bundle path when
        ``CRAWLER_CA_BUNDLE`` is set, or ``False`` only when an environment
        variable explicitly disables verification.
    """
    enabled = _parse_bool(os.getenv(VERIFY_ENV), default=True)
    source_env = None
    if source:
        source_env = f"{VERIFY_ENV}_{_source_env_key(source)}"
        specific = os.getenv(source_env)
        if specific is not None and specific.strip():
            enabled = _parse_bool(specific, default=enabled)

    if not enabled:
        if source and source not in _warned_sources:
            _warned_sources.add(source)
            logger.warning(
                "TLS verification disabled for crawler %r via %s; "
                "prefer CRAWLER_CA_BUNDLE",
                source,
                source_env or VERIFY_ENV,
            )
        return False

    bundle = os.getenv(CA_BUNDLE_ENV, "").strip()
    return bundle or True


def get(
    url: str,
    *,
    source: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    **kwargs: Any,
) -> requests.Response:
    """Perform a GET with verified TLS unless a source explicitly opts out."""
    return requests.get(
        url,
        headers=headers,
        timeout=timeout,
        verify=verify_setting(source),
        **kwargs,
    )


def session(source: str | None = None) -> requests.Session:
    """Return a ``requests`` session configured for the given source."""
    client = requests.Session()
    client.verify = verify_setting(source)
    return client


__all__ = ["CA_BUNDLE_ENV", "VERIFY_ENV", "get", "session", "verify_setting"]
