"""Logging configuration with UTF-8 console support."""

import contextlib
import logging
import sys
from pathlib import Path


def _force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 (fixes CP1252 emoji errors on Windows).

    Must be called before creating StreamHandlers. Uses the stdlib
    ``reconfigure`` method (Python 3.7+), which safely replaces the
    encoding of an existing text stream.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            # Stream may not support reconfiguration (e.g., pytest capture).
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def setup_logging(
    log_level: str = "INFO",
    log_file: str = "logs/app.log",
) -> None:
    """Configure console and file logging.

    The file logger stores runtime logs in UTF-8, which is important
    because the project logs Arabic messages and emoji.
    Console output is also forced to UTF-8 to avoid CP1252 errors
    when running under Task Scheduler on Windows.
    """
    _force_utf8_streams()

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
