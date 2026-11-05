"""Arabic-aware announcement search.

SQLite FTS5 is the primary engine when available (``ANN_FTS``); otherwise the
same normalised query runs against ``announcements.search_text`` with a literal
``LIKE``. Both paths share the same filters, sorting and pagination so tests can
assert identical result sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Select,
    String,
    Table,
    func,
    select,
    text,
)
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import ColumnElement

from webapp.db import FTS_TABLE
from webapp.enums import AnnouncementStatus, AnnouncementType
from webapp.models import Announcement, Issuer, Sector
from webapp.text import build_fts_query, escape_like, normalize_search

#: Statuses visible on the public site.
PUBLIC_STATUSES = (AnnouncementStatus.PUBLISHED, AnnouncementStatus.ARCHIVED)

#: Accepted ``sort`` values and their Arabic labels.
SORT_OPTIONS: dict[str, str] = {
    "relevance": "الأكثر صلة",
    "recent": "الأحدث نشراً",
    "deadline": "الأقرب أجلاً",
    "oldest": "الأقدم نشراً",
}

DEFAULT_PER_PAGE = 12
MAX_PER_PAGE = 48

#: Lightweight table object for joining the FTS5 virtual table; it is not
#: part of ``Base.metadata`` and is created by ``ensure_fts``.
FTS_REFLECT = Table(
    FTS_TABLE,
    MetaData(),
    Column("rowid", Integer, primary_key=True),
    Column("title", String),
    Column("body", String),
    Column("issuer", String),
)


@dataclass(frozen=True)
class AnnouncementFilters:
    """Validated search filters for the public listing.

    An empty string means "no filter". ``page`` is 1-based; ``per_page`` is
    clamped by :func:`search_announcements`.
    """

    q: str = ""
    type: AnnouncementType | None = None
    wilaya_code: str = ""
    sector_slug: str = ""
    issuer_slug: str = ""
    date_from: date | None = None
    date_to: date | None = None
    include_samples: bool = True
    sort: str = "relevance"
    page: int = 1
    per_page: int = DEFAULT_PER_PAGE
    statuses: tuple[AnnouncementStatus, ...] = PUBLIC_STATUSES


@dataclass
class SearchResult:
    """One page of matching announcements plus pagination metadata."""

    items: list[Announcement] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = DEFAULT_PER_PAGE
    pages: int = 1
    used_fts: bool = False
    normalized_query: str = ""

    @property
    def has_previous(self) -> bool:
        """Whether a previous page exists."""
        return self.page > 1

    @property
    def has_next(self) -> bool:
        """Whether a next page exists."""
        return self.page < self.pages

    @property
    def page_numbers(self) -> list[int | None]:
        """Compact page list with ``None`` as an ellipsis marker."""
        if self.pages <= 7:
            return list(range(1, self.pages + 1))
        candidates = {1, self.pages, self.page - 1, self.page, self.page + 1}
        if self.page <= 3:
            candidates.update({2, 3, 4})
        if self.page >= self.pages - 2:
            candidates.update({self.pages - 3, self.pages - 2, self.pages - 1})
        numbers = sorted(number for number in candidates if 1 <= number <= self.pages)
        output: list[int | None] = []
        previous = 0
        for number in numbers:
            if previous and number - previous > 1:
                output.append(None)
            output.append(number)
            previous = number
        return output


def _fts_available(db: Session) -> bool:
    """Detect the FTS virtual table once per session/connection."""
    cached = getattr(db, "_dz_fts_available", None)
    if cached is not None:
        return bool(cached)
    bind = db.bind
    url = getattr(bind, "url", None)
    if url is None or not url.get_backend_name().startswith("sqlite"):
        available = False
    else:
        try:
            row = db.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
                ),
                {"name": FTS_TABLE},
            ).first()
            available = row is not None
        except Exception:  # pragma: no cover - defensive
            available = False
    db._dz_fts_available = available  # type: ignore[attr-defined]
    return available


def _eager_options() -> tuple:
    return (
        selectinload(Announcement.sectors),
        selectinload(Announcement.issuer),
        selectinload(Announcement.wilaya),
        selectinload(Announcement.attachments),
    )


def _base_select() -> Select:
    return select(Announcement).options(*_eager_options())


def _apply_filters(stmt: Select, filters: AnnouncementFilters) -> Select:
    if filters.statuses:
        stmt = stmt.where(Announcement.status.in_(filters.statuses))
    if not filters.include_samples:
        stmt = stmt.where(Announcement.is_sample.is_(False))
    if filters.type is not None:
        stmt = stmt.where(Announcement.type == filters.type)
    if filters.wilaya_code:
        from webapp.models import Wilaya

        stmt = stmt.where(Announcement.wilaya.has(Wilaya.code == filters.wilaya_code))
    if filters.sector_slug:
        stmt = stmt.where(Announcement.sectors.any(Sector.slug == filters.sector_slug))
    if filters.issuer_slug:
        stmt = stmt.where(Announcement.issuer.has(Issuer.slug == filters.issuer_slug))
    if filters.date_from is not None:
        stmt = stmt.where(Announcement.publish_date >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(Announcement.publish_date <= filters.date_to)
    return stmt


def _like_condition(normalized: str) -> ColumnElement[bool]:
    pattern = f"%{escape_like(normalized)}%"
    return Announcement.search_text.like(pattern, escape="\\")


def _join_fts(stmt: Select, fts_query: str) -> Select:
    """Join the FTS5 virtual table and bind a safe MATCH expression."""
    return (
        stmt.join(FTS_REFLECT, FTS_REFLECT.c.rowid == Announcement.id)
        .where(text(f"{FTS_TABLE} MATCH :fts_query"))
        .params(fts_query=fts_query)
    )


def _order_clause(sort: str, *, ranked: bool):
    if sort == "relevance" and ranked:
        return [text(f"bm25({FTS_TABLE}) ASC")]
    if sort == "oldest":
        return [Announcement.publish_date.asc(), Announcement.id.asc()]
    if sort == "deadline":
        return [
            Announcement.deadline_at.is_(None).asc(),
            Announcement.deadline_at.asc(),
            Announcement.publish_date.desc(),
        ]
    if sort == "deadline_desc":
        return [
            Announcement.deadline_at.is_(None).asc(),
            Announcement.deadline_at.desc(),
            Announcement.publish_date.desc(),
        ]
    return [Announcement.publish_date.desc(), Announcement.id.desc()]


def search_announcements(
    db: Session,
    filters: AnnouncementFilters,
    *,
    per_page: int = DEFAULT_PER_PAGE,
) -> SearchResult:
    """Run a filtered, paginated, ranked search.

    Args:
        db: Session.
        filters: Validated filters (``page`` is 1-based).
        per_page: Page size; clamped to ``1..MAX_PER_PAGE``.

    Returns:
        A :class:`SearchResult` with eager-loaded relationships.
    """
    per_page = max(1, min(MAX_PER_PAGE, per_page))
    normalized = normalize_search(filters.q)
    page = max(1, int(filters.page or 1))

    stmt = _base_select()
    count_stmt = select(func.count(func.distinct(Announcement.id)))

    if normalized:
        fts_query = build_fts_query(filters.q)
        use_fts = bool(filters.q) and _fts_available(db)
        if use_fts and fts_query:
            stmt = _join_fts(stmt, fts_query)
            count_stmt = _join_fts(count_stmt, fts_query)
            ranked = True
        else:
            use_fts = False
            condition = _like_condition(normalized)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
            ranked = False
    else:
        use_fts = False
        ranked = False

    stmt = _apply_filters(stmt, filters)
    count_stmt = _apply_filters(count_stmt, filters)

    total = int(db.scalar(count_stmt) or 0)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)

    stmt = stmt.order_by(*_order_clause(filters.sort, ranked=ranked))
    stmt = stmt.limit(per_page).offset((page - 1) * per_page)
    items = list(db.scalars(stmt).unique().all())

    return SearchResult(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        used_fts=use_fts,
        normalized_query=normalized,
    )


def published_announcement(
    db: Session, announcement_id: int, *, include_archived: bool = True
) -> Announcement | None:
    """Fetch one publicly visible announcement with all relationships."""
    statuses = PUBLIC_STATUSES if include_archived else (AnnouncementStatus.PUBLISHED,)
    return db.scalar(
        _base_select().where(
            Announcement.id == announcement_id, Announcement.status.in_(statuses)
        )
    )


def latest_announcements(
    db: Session,
    limit: int = 6,
    *,
    exclude_id: int | None = None,
    sector_id: int | None = None,
    include_samples: bool = True,
) -> list[Announcement]:
    """Most recent published announcements, optionally for one sector."""
    stmt = (
        _base_select()
        .where(Announcement.status == AnnouncementStatus.PUBLISHED)
        .order_by(Announcement.publish_date.desc(), Announcement.id.desc())
        .limit(limit)
    )
    if exclude_id is not None:
        stmt = stmt.where(Announcement.id != exclude_id)
    if sector_id is not None:
        stmt = stmt.where(Announcement.sectors.any(Sector.id == sector_id))
    if not include_samples:
        stmt = stmt.where(Announcement.is_sample.is_(False))
    return list(db.scalars(stmt).unique().all())


def count_public(db: Session) -> int:
    """Number of published/archived announcements."""
    return int(
        db.scalar(
            select(func.count(Announcement.id)).where(
                Announcement.status.in_(PUBLIC_STATUSES)
            )
        )
        or 0
    )


__all__ = [
    "AnnouncementFilters",
    "DEFAULT_PER_PAGE",
    "MAX_PER_PAGE",
    "PUBLIC_STATUSES",
    "SORT_OPTIONS",
    "SearchResult",
    "count_public",
    "latest_announcements",
    "published_announcement",
    "search_announcements",
]
