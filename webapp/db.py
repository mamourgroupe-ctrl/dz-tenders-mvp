"""Database engine, declarative base and FTS5 bootstrap helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

#: Virtual table backing Arabic-aware full-text search. ``rowid`` is the
#: announcement primary key, so junction and rank are trivial.
FTS_TABLE = "announcement_fts"
FTS_DDL = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
    title,
    body,
    issuer,
    tokenize = 'unicode61 remove_diacritics 2'
)
"""


class Base(DeclarativeBase):
    """Declarative base for every product table."""


def make_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create an engine with SQLite-safe settings.

    Args:
        database_url: SQLAlchemy URL (SQLite file, in-memory or PostgreSQL).
        echo: Log SQL statements (development only).

    Returns:
        A configured engine. SQLite connections enforce foreign keys.
    """
    kwargs: dict[str, object] = {"echo": echo, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **kwargs)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(
            dbapi_connection, _record
        ) -> None:  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory with stable identity-map behaviour."""
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit on success, roll back on failure, always close."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def fts_available(engine: Engine) -> bool:
    """Return whether the SQLite connection supports FTS5."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
            )
            conn.execute(text("DROP TABLE IF EXISTS _fts_probe"))
            conn.commit()
        return True
    except OperationalError:
        return False


def ensure_fts(engine: Engine) -> bool:
    """Create the FTS virtual table when the backend supports it.

    Args:
        engine: Target engine.

    Returns:
        True when the virtual table exists afterwards, False when the backend
        lacks FTS5 (search then falls back to a ``LIKE`` scan).
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        logger.info("FTS5 skipped: backend %s has no FTS5 support", engine.url)
        return False
    try:
        with engine.begin() as conn:
            conn.execute(text(FTS_DDL))
        return True
    except OperationalError as exc:  # pragma: no cover - depends on SQLite build
        logger.warning("FTS5 unavailable, falling back to LIKE search: %s", exc)
        return False


__all__ = [
    "Base",
    "FTS_DDL",
    "FTS_TABLE",
    "ensure_fts",
    "fts_available",
    "make_engine",
    "make_session_factory",
    "schema_ready",
    "session_scope",
]


def schema_ready(engine: Engine) -> bool:
    """Whether the product schema has been migrated (announcements exists)."""
    from sqlalchemy import inspect

    try:
        return inspect(engine).has_table("announcements")
    except Exception:  # pragma: no cover - defensive
        return False
