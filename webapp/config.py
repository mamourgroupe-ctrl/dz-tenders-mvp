"""Runtime settings for the public platform (Phase 1).

Follows the repository convention (``config.AppConfig``): a frozen dataclass
built from environment variables through ``python-dotenv``. No secret has a
usable default: production boots only with explicit configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from config import parse_bool

#: Repository root; relative SQLite paths resolve against it, exactly like
#: ``storage.paths.resolve_db_path`` does for the legacy pipeline.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Default product database, deliberately separate from ``storage/tenders.db``.
DEFAULT_DB_RELATIVE = "storage/platform.db"


def _env_int(name: str, default: int) -> int:
    """Read an integer environment value, falling back on malformed input."""
    raw = os.getenv(name)
    if not raw or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_database_url() -> str:
    """Build the SQLite SQLAlchemy URL for ``storage/platform.db``."""
    raw = os.getenv("APP_DATABASE_URL", "").strip()
    if raw:
        return raw
    path = REPO_ROOT / DEFAULT_DB_RELATIVE
    return f"sqlite+pysqlite:///{path}"


@dataclass(frozen=True)
class Settings:
    """Immutable application settings.

    Attributes:
        app_env: ``development``, ``test`` or ``production``.
        database_url: SQLAlchemy URL (SQLite by default).
        base_url: Public base URL used in canonical links and sitemaps; empty
            means "derive from the incoming request".
        page_size: Default page size of the public listings.
        max_page_size: Hard upper bound for ``per_page``.
        session_ttl_hours: Lifetime of an authenticated browser session.
        cookie_secure: ``Secure`` flag on cookies; auto-enabled in production.
        fts_enabled: Use SQLite FTS5 when available (LIKE fallback otherwise).
        login_rate_limit: Failed/successful login attempts per window and phone.
        ip_rate_limit: Login attempts per window and IP.
        rate_limit_window_minutes: Window for both limits.
        upload_dir: Root for payment proofs and announcement attachments.
        max_upload_bytes: Maximum accepted upload size.
        wilayas_file: Optional JSON override of the seeded wilaya list.
        admin_phone/admin_email/admin_password: Optional bootstrap admin.
        contact_email/contact_phone: Displayed on the contact page.
        trust_proxy: Honour ``X-Forwarded-*`` headers (behind a reverse proxy).
    """

    app_env: str = "development"
    database_url: str = field(default_factory=_default_database_url)
    base_url: str = ""
    page_size: int = 12
    max_page_size: int = 48
    session_ttl_hours: int = 72
    cookie_secure: bool | None = None
    fts_enabled: bool = True
    login_rate_limit: int = 5
    ip_rate_limit: int = 10
    rate_limit_window_minutes: int = 15
    upload_dir: str = str(REPO_ROOT / "storage" / "uploads")
    max_upload_bytes: int = 5 * 1024 * 1024
    wilayas_file: str = ""
    admin_phone: str = ""
    admin_email: str = ""
    admin_password: str = ""
    contact_email: str = "contact@example.dz"
    contact_phone: str = ""
    trust_proxy: bool = False

    @property
    def is_production(self) -> bool:
        """Whether the app runs with production-safe defaults."""
        return self.app_env.lower() == "production"

    @property
    def secure_cookies(self) -> bool:
        """Whether cookies must carry the ``Secure`` flag."""
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production

    @property
    def public_base_url(self) -> str:
        """Configured public base URL without a trailing slash."""
        return self.base_url.rstrip("/")

    def database_path(self) -> Path | None:
        """Return the SQLite file path when the URL is a local SQLite file."""
        prefix = "sqlite+pysqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        raw = self.database_url[len(prefix) :]
        if raw.startswith(":memory:") or raw.startswith("file:"):
            return None
        return Path(raw)

    @classmethod
    def from_env(cls, load_env_file: bool = True) -> Settings:
        """Create settings from environment variables."""
        if load_env_file:
            load_dotenv(override=False)

        cookie_secure_raw = os.getenv("APP_COOKIE_SECURE", "").strip()
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            database_url=_default_database_url(),
            base_url=os.getenv("APP_BASE_URL", ""),
            page_size=max(1, _env_int("APP_PAGE_SIZE", 12)),
            max_page_size=max(1, _env_int("APP_MAX_PAGE_SIZE", 48)),
            session_ttl_hours=max(1, _env_int("APP_SESSION_TTL_HOURS", 72)),
            cookie_secure=(
                parse_bool(cookie_secure_raw) if cookie_secure_raw else None
            ),
            fts_enabled=parse_bool(os.getenv("APP_FTS_ENABLED"), default=True),
            login_rate_limit=max(1, _env_int("APP_LOGIN_RATE_LIMIT", 5)),
            ip_rate_limit=max(1, _env_int("APP_IP_RATE_LIMIT", 10)),
            rate_limit_window_minutes=max(
                1, _env_int("APP_RATE_LIMIT_WINDOW_MINUTES", 15)
            ),
            upload_dir=os.getenv(
                "APP_UPLOAD_DIR", str(REPO_ROOT / "storage" / "uploads")
            ),
            max_upload_bytes=max(
                1024, _env_int("APP_MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
            ),
            wilayas_file=os.getenv("APP_WILAYAS_FILE", ""),
            admin_phone=os.getenv("APP_ADMIN_PHONE", ""),
            admin_email=os.getenv("APP_ADMIN_EMAIL", ""),
            admin_password=os.getenv("APP_ADMIN_PASSWORD", ""),
            contact_email=os.getenv("APP_CONTACT_EMAIL", "contact@example.dz"),
            contact_phone=os.getenv("APP_CONTACT_PHONE", ""),
            trust_proxy=parse_bool(os.getenv("APP_TRUST_PROXY"), default=False),
        )


__all__ = ["DEFAULT_DB_RELATIVE", "REPO_ROOT", "Settings"]
