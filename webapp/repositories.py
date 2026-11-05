"""Read-side queries for public pages and the future admin KPIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from webapp.enums import (
    AnnouncementStatus,
    AnnouncementType,
    BannerPlacement,
    SubcontractingStatus,
)
from webapp.models import (
    Announcement,
    Banner,
    Issuer,
    Plan,
    SavedAnnouncement,
    SearchLog,
    Sector,
    SubcontractingOffer,
    Subscription,
    Wilaya,
)
from webapp.search import PUBLIC_STATUSES
from webapp.text import normalize_search, truncate_words
from webapp.timeutils import utcnow


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------
def active_wilayas(db: Session) -> list[Wilaya]:
    """All active wilayas ordered by their official code."""
    return list(
        db.scalars(
            select(Wilaya).where(Wilaya.is_active.is_(True)).order_by(Wilaya.code)
        )
    )


def active_sectors(db: Session) -> list[Sector]:
    """All active sectors in display order."""
    return list(
        db.scalars(
            select(Sector)
            .where(Sector.is_active.is_(True))
            .order_by(Sector.sort_order, Sector.id)
        )
    )


def active_issuers(db: Session) -> list[Issuer]:
    """Active issuers at most 200, for filter dropdowns."""
    return list(
        db.scalars(
            select(Issuer)
            .where(Issuer.is_active.is_(True))
            .order_by(Issuer.name_ar)
            .limit(200)
        )
    )


def wilaya_by_code(db: Session, code: str) -> Wilaya | None:
    """Look up a wilaya by its two-digit code."""
    return db.scalar(select(Wilaya).where(Wilaya.code == code))


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------
def archive_years(db: Session) -> list[tuple[int, int]]:
    """Return ``[(year, count)]`` for publicly visible announcements."""
    rows = db.execute(
        select(Announcement.publish_year, func.count(Announcement.id))
        .where(Announcement.status.in_(PUBLIC_STATUSES))
        .group_by(Announcement.publish_year)
        .order_by(Announcement.publish_year.desc())
    ).all()
    return [(int(year), int(count)) for year, count in rows]


def type_counts(db: Session) -> list[tuple[AnnouncementType, int]]:
    """Count public announcements per type, in enum order."""
    counts: dict[AnnouncementType, int] = {}
    for kind, total in db.execute(
        select(Announcement.type, func.count(Announcement.id))
        .where(Announcement.status.in_(PUBLIC_STATUSES))
        .group_by(Announcement.type)
    ).all():
        counts[kind] = int(total)
    return [(kind, counts[kind]) for kind in AnnouncementType if counts.get(kind)]


def top_wilayas(db: Session, limit: int = 8) -> list[tuple[Wilaya, int]]:
    """Most active wilayas by public announcement count."""
    rows = db.execute(
        select(Wilaya, func.count(Announcement.id).label("total"))
        .join(Announcement, Announcement.wilaya_id == Wilaya.id)
        .where(Announcement.status.in_(PUBLIC_STATUSES))
        .group_by(Wilaya.id)
        .order_by(func.count(Announcement.id).desc(), Wilaya.code)
        .limit(limit)
    ).all()
    return [(wilaya, int(total)) for wilaya, total in rows]


def home_stats(db: Session) -> dict[str, int]:
    """Aggregate counters displayed on the home page."""
    now = utcnow()
    week_ago = now - timedelta(days=7)
    public = Announcement.status.in_(PUBLIC_STATUSES)

    total = int(db.scalar(select(func.count(Announcement.id)).where(public)) or 0)
    open_deadlines = int(
        db.scalar(
            select(func.count(Announcement.id)).where(
                public,
                (Announcement.deadline_at.is_(None)) | (Announcement.deadline_at > now),
            )
        )
        or 0
    )
    new_week = int(
        db.scalar(
            select(func.count(Announcement.id)).where(
                public, Announcement.publish_date >= week_ago.date()
            )
        )
        or 0
    )
    wilayas = int(
        db.scalar(
            select(func.count(func.distinct(Announcement.wilaya_id))).where(public)
        )
        or 0
    )
    sectors = int(
        db.scalar(
            select(func.count(func.distinct(Sector.id)))
            .select_from(Sector)
            .where(Sector.is_active.is_(True))
        )
        or 0
    )
    return {
        "total": total,
        "open_deadlines": open_deadlines,
        "new_week": new_week,
        "wilayas": wilayas,
        "sectors": sectors,
    }


def increment_view_count(db: Session, announcement_id: int) -> None:
    """Increment the view counter without loading the row."""
    db.execute(
        update(Announcement)
        .where(Announcement.id == announcement_id)
        .values(view_count=Announcement.view_count + 1)
    )
    db.commit()


def similar_announcements(
    db: Session, announcement: Announcement, limit: int = 3
) -> list[Announcement]:
    """Latest other announcements sharing at least one sector."""
    sector_ids = [sector.id for sector in announcement.sectors]
    stmt = (
        select(Announcement)
        .where(
            Announcement.status == AnnouncementStatus.PUBLISHED,
            Announcement.id != announcement.id,
        )
        .options(
            selectinload(Announcement.sectors),
            selectinload(Announcement.issuer),
            selectinload(Announcement.wilaya),
            selectinload(Announcement.attachments),
        )
        .order_by(Announcement.publish_date.desc())
        .limit(limit)
    )
    if sector_ids:
        stmt = stmt.where(Announcement.sectors.any(Sector.id.in_(sector_ids)))
    else:
        stmt = stmt.where(Announcement.wilaya_id == announcement.wilaya_id)
    return list(db.scalars(stmt).unique().all())


# ---------------------------------------------------------------------------
# Plans, offers, banners, search logs
# ---------------------------------------------------------------------------
def active_plans(db: Session) -> list[Plan]:
    """Visible plans ordered for a pricing page."""
    return list(
        db.scalars(
            select(Plan)
            .where(Plan.is_active.is_(True))
            .order_by(Plan.sort_order, Plan.id)
        )
    )


@dataclass
class OfferPage:
    """Paginated subcontracting offers."""

    items: list[SubcontractingOffer] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 12
    pages: int = 1

    @property
    def has_next(self) -> bool:
        """Whether a next page exists."""
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        """Whether a previous page exists."""
        return self.page > 1

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


def list_offers(
    db: Session,
    *,
    page: int = 1,
    per_page: int = 12,
    sector_slug: str = "",
    wilaya_code: str = "",
) -> OfferPage:
    """Published subcontracting offers, newest first."""
    per_page = max(1, min(48, per_page))
    stmt = select(SubcontractingOffer).where(
        SubcontractingOffer.status == SubcontractingStatus.PUBLISHED
    )
    count_stmt = select(func.count(SubcontractingOffer.id)).where(
        SubcontractingOffer.status == SubcontractingStatus.PUBLISHED
    )
    if sector_slug:
        stmt = stmt.where(SubcontractingOffer.sector.has(Sector.slug == sector_slug))
        count_stmt = count_stmt.where(
            SubcontractingOffer.sector.has(Sector.slug == sector_slug)
        )
    if wilaya_code:
        stmt = stmt.where(SubcontractingOffer.wilaya.has(Wilaya.code == wilaya_code))
        count_stmt = count_stmt.where(
            SubcontractingOffer.wilaya.has(Wilaya.code == wilaya_code)
        )

    total = int(db.scalar(count_stmt) or 0)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    items = list(
        db.scalars(
            stmt.options(
                selectinload(SubcontractingOffer.sector),
                selectinload(SubcontractingOffer.wilaya),
            )
            .order_by(
                SubcontractingOffer.published_at.desc().nullslast(),
                SubcontractingOffer.id.desc(),
            )
            .limit(per_page)
            .offset((page - 1) * per_page)
        ).all()
    )
    return OfferPage(
        items=items, total=total, page=page, per_page=per_page, pages=pages
    )


def published_offer(db: Session, offer_id: int) -> SubcontractingOffer | None:
    """Fetch one published offer with taxonomy loaded."""
    return db.scalar(
        select(SubcontractingOffer)
        .where(
            SubcontractingOffer.id == offer_id,
            SubcontractingOffer.status == SubcontractingStatus.PUBLISHED,
        )
        .options(
            selectinload(SubcontractingOffer.sector),
            selectinload(SubcontractingOffer.wilaya),
        )
    )


def active_banners(
    db: Session, placement: BannerPlacement, limit: int = 1
) -> list[Banner]:
    """Banners active at the current moment for one placement."""
    now = utcnow()
    return list(
        db.scalars(
            select(Banner)
            .where(
                Banner.is_active.is_(True),
                Banner.placement == placement,
                (Banner.starts_at.is_(None)) | (Banner.starts_at <= now),
                (Banner.ends_at.is_(None)) | (Banner.ends_at >= now),
            )
            .order_by(Banner.sort_order, Banner.id)
            .limit(limit)
        )
    )


def record_search(db: Session, term: str, result_count: int) -> None:
    """Store a normalised search term for the KPI dashboard."""
    clean = truncate_words(term, 200, suffix="")
    if not clean:
        return
    db.add(
        SearchLog(
            term=clean,
            term_normalized=normalize_search(clean)[:200],
            result_count=result_count,
        )
    )
    db.commit()


def top_searches(db: Session, limit: int = 10) -> list[tuple[str, int]]:
    """Most frequent normalised searches (admin KPIs)."""
    rows = db.execute(
        select(SearchLog.term_normalized, func.count(SearchLog.id))
        .where(SearchLog.term_normalized != "")
        .group_by(SearchLog.term_normalized)
        .order_by(func.count(SearchLog.id).desc())
        .limit(limit)
    ).all()
    return [(term, int(count)) for term, count in rows]


# ---------------------------------------------------------------------------
# Account-side helpers (Phase 2 surfaces, used by Phase 1 login state)
# ---------------------------------------------------------------------------
def active_subscription(
    db: Session, user_id: int, *, now: datetime | None = None
) -> Subscription | None:
    """The current subscription of a user, if any."""
    return db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .options(selectinload(Subscription.plan), selectinload(Subscription.sectors))
        .order_by(Subscription.ends_at.desc().nullslast(), Subscription.id.desc())
    )


def saved_announcement_ids(db: Session, user_id: int) -> set[int]:
    """Ids bookmarked by a user."""
    rows = db.scalars(
        select(SavedAnnouncement.announcement_id).where(
            SavedAnnouncement.user_id == user_id
        )
    ).all()
    return set(rows)


def toggle_saved(db: Session, user_id: int, announcement_id: int) -> bool:
    """Add or remove a bookmark; returns the new saved state."""
    existing = db.scalar(
        select(SavedAnnouncement).where(
            SavedAnnouncement.user_id == user_id,
            SavedAnnouncement.announcement_id == announcement_id,
        )
    )
    if existing:
        db.execute(
            delete(SavedAnnouncement).where(
                SavedAnnouncement.user_id == user_id,
                SavedAnnouncement.announcement_id == announcement_id,
            )
        )
        db.commit()
        return False
    db.add(SavedAnnouncement(user_id=user_id, announcement_id=announcement_id))
    db.commit()
    return True


def count_by_year(db: Session, year: int) -> int:
    """Number of public announcements published in a calendar year."""
    return int(
        db.scalar(
            select(func.count(Announcement.id)).where(
                Announcement.publish_year == year,
                Announcement.status.in_(PUBLIC_STATUSES),
            )
        )
        or 0
    )


def date_bounds_for_year(year: int) -> tuple[date, date]:
    """Inclusive publication-date bounds of a year."""
    return date(year, 1, 1), date(year, 12, 31)


__all__ = [
    "OfferPage",
    "active_banners",
    "active_issuers",
    "active_plans",
    "active_sectors",
    "active_subscription",
    "active_wilayas",
    "archive_years",
    "count_by_year",
    "date_bounds_for_year",
    "home_stats",
    "increment_view_count",
    "list_offers",
    "published_offer",
    "record_search",
    "saved_announcement_ids",
    "similar_announcements",
    "toggle_saved",
    "top_searches",
    "top_wilayas",
    "type_counts",
    "wilaya_by_code",
]
