import logging

from logging_config import setup_logging


def test_setup_logging_writes_to_file(tmp_path):
    log_file = tmp_path / "app.log"

    setup_logging(log_level="INFO", log_file=str(log_file))

    logger = logging.getLogger("test_logger")
    logger.info("hello logging")

    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_file.exists()
    assert "hello logging" in log_file.read_text(encoding="utf-8")
