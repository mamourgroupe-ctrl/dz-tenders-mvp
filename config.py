"""Application configuration for DZ Tenders.

Centralizes environment variable handling in one place.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse boolean-like environment values."""
    if value is None:
        return default

    return value.strip().lower() in TRUE_VALUES


@dataclass(frozen=True)
class AppConfig:
    """Runtime application configuration."""

    app_env: str = "development"
    log_level: str = "INFO"
    db_path: str = "storage/tenders.db"
    dry_run: bool = True
    include_samples: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @classmethod
    def from_env(cls, load_env_file: bool = True) -> "AppConfig":
        """Build config from environment variables."""
        if load_env_file:
            load_dotenv(override=False)

        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            db_path=os.getenv("DB_PATH", "storage/tenders.db"),
            dry_run=parse_bool(os.getenv("DRY_RUN"), default=True),
            include_samples=parse_bool(os.getenv("INCLUDE_SAMPLES"), default=False),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        )
