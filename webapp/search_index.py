"""Maintain the FTS5 mirror of announcements.

The index is written by the application (not by SQL triggers) so the exact same
:func:`webapp.text.normalize_search` runs at index and query time. Indexing is
idempotent: one row per announcement, keyed by its primary key as FTS rowid.
"""

from __future__ import annotations

import contextlib
import logging

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from webapp.db import FTS_TABLE
from webapp.models import Announcement
from webapp.text import normalize_search

logger = logging.getLogger(__name__)


def _fts_backend(db: Session) -> bool:
    """Whether the session's database uses the SQLite FTS5 mirror.

    PostgreSQL uses ``tsvector`` over ``search_text`` directly, so touching
    ``announcement_fts`` there would abort the transaction.
    """
    bind = db.get_bind()
    return bind.dialect.name == "sqlite"


def _taxonomy_text(announcement: Announcement) -> tuple[str, str, str, str]:
    """Return ``(title, body, issuer, wilaya)`` normalised for indexing."""
    sector_names = " ".join(
        f"{sector.name_ar} {sector.name_fr}" for sector in announcement.sectors
    )
    wilaya_names = (
        f"{announcement.wilaya.name_ar} {announcement.wilaya.name_fr}"
        if announcement.wilaya
        else ""
    )
    issuer_ar = announcement.issuer.name_ar if announcement.issuer else ""
    issuer_fr = announcement.issuer.name_fr if announcement.issuer else ""
    issuer = announcement.issuer_name or issuer_ar or ""

    title = " ".join(
        part for part in (announcement.title_ar, announcement.title_fr or "") if part
    )
    body = " ".join(
        part
        for part in (
            announcement.description_ar or "",
            announcement.description_fr or "",
            sector_names,
            announcement.reference or "",
            announcement.source_name or "",
        )
        if part
    )
    issuer_text = " ".join(part for part in (issuer, issuer_ar, issuer_fr) if part)
    return (
        normalize_search(title),
        normalize_search(f"{body} {wilaya_names}"),
        normalize_search(issuer_text),
        normalize_search(wilaya_names),
    )


def build_search_text(announcement: Announcement) -> str:
    """Normalised concatenation used by the LIKE fallback."""
    title, body, issuer, wilaya = _taxonomy_text(announcement)
    return normalize_search(" ".join((title, body, issuer, wilaya)))


def index_announcement(db: Session, announcement: Announcement) -> bool:
    """Update ``search_text`` and the FTS row of one announcement.

    Returns:
        True when the FTS row was written; False when the backend lacks FTS5
        (the normalised ``search_text`` is still updated).
    """
    announcement.search_text = build_search_text(announcement)
    db.add(announcement)
    if announcement.id is None:
        db.flush()

    if not _fts_backend(db):
        return False

    try:
        db.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE rowid = :rowid"),
            {"rowid": announcement.id},
        )
        title, body, issuer, _wilaya = _taxonomy_text(announcement)
        db.execute(
            text(
                f"INSERT INTO {FTS_TABLE}(rowid, title, body, issuer) "
                "VALUES (:rowid, :title, :body, :issuer)"
            ),
            {"rowid": announcement.id, "title": title, "body": body, "issuer": issuer},
        )
        return True
    except SQLAlchemyError:
        logger.info("FTS table unavailable; %s stays LIKE-searchable", announcement.id)
        return False


def remove_from_index(db: Session, announcement_id: int) -> None:
    """Delete the FTS row of an announcement (no-op without FTS)."""
    if not _fts_backend(db):
        return
    try:
        db.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE rowid = :rowid"),
            {"rowid": announcement_id},
        )
    except SQLAlchemyError:
        return


def rebuild_index(db: Session) -> int:
    """Rebuild ``search_text`` and the FTS table from source rows.

    Args:
        db: Session with announcements loaded.

    Returns:
        Number of announcements indexed.
    """
    if _fts_backend(db):
        with contextlib.suppress(SQLAlchemyError):
            db.execute(text(f"DELETE FROM {FTS_TABLE}"))
    announcements = list(db.scalars(select(Announcement)).all())
    for announcement in announcements:
        index_announcement(db, announcement)
    db.commit()
    return len(announcements)


__all__ = [
    "build_search_text",
    "index_announcement",
    "rebuild_index",
    "remove_from_index",
]
