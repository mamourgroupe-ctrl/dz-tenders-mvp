"""Logging configuration for DZ Tenders."""

import logging
import sys
from pathlib import Path


def setup_logging(
    log_level: str = "INFO",
    log_file: str = "logs/app.log",
) -> None:
    """Configure console and file logging.

    The file logger stores runtime logs in UTF-8, which is important
    because the project logs Arabic messages.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(log_format))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))

    logging.basicConfig(
        level=level,
        handlers=[console_handler, file_handler],
        force=True,
    )
