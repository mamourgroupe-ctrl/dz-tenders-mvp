"""Idempotent seeding of taxonomy, plans and demonstration content."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.config import Settings
from webapp.enums import (
    AnnouncementStatus,
    AnnouncementType,
    PlanKind,
    SubcontractingStatus,
    UserRole,
)
from webapp.models import (
    Announcement,
    Issuer,
    Plan,
    Sector,
    SubcontractingOffer,
    User,
    Wilaya,
)
from webapp.search_index import index_announcement
from webapp.security import hash_password, normalize_phone, validate_password
from webapp.seed_data import ISSUERS, OFFERS, PLANS, SAMPLES, SECTORS, WILAYAS
from webapp.text import slugify
from webapp.timeutils import utcnow

logger = logging.getLogger(__name__)


@dataclass
class SeedSummary:
    """Counts written by :func:`seed_all`."""

    wilayas: int = 0
    sectors: int = 0
    issuers: int = 0
    plans: int = 0
    announcements: int = 0
    offers: int = 0
    admin_created: bool = False

    def as_dict(self) -> dict[str, object]:
        """Serialise for the CLI output."""
        return asdict(self)


def load_wilayas_override(path: str) -> list[tuple[str, str, str, str]]:
    """Load a client-supplied wilaya list from JSON.

    Expected format: a list of objects with ``code``, ``name_ar``, ``name_fr``
    and optional ``slug``. This is how the 69-entry list (open question O1) can
    be applied without a code change.

    Args:
        path: JSON file path.

    Returns:
        Normalised tuples ready for seeding.

    Raises:
        ValueError: The file is not a list, an entry is incomplete, or a code
            is duplicated.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("APP_WILAYAS_FILE must contain a JSON list")
    rows: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each wilaya entry must be an object")
        code = str(entry.get("code", "")).zfill(2)
        name_ar = str(entry.get("name_ar", "")).strip()
        name_fr = str(entry.get("name_fr", "")).strip()
        if not code.isdigit() or not name_ar or not name_fr:
            raise ValueError(f"Incomplete wilaya entry: {entry!r}")
        if code in seen:
            raise ValueError(f"Duplicate wilaya code: {code}")
        seen.add(code)
        slug = str(entry.get("slug") or slugify(name_fr, fallback=f"wilaya-{code}"))
        rows.append((code, slug, name_ar, name_fr))
    if not rows:
        raise ValueError("APP_WILAYAS_FILE is empty")
    return rows


def seed_wilayas(
    db: Session, rows: list[tuple[str, str, str, str]] | None = None
) -> int:
    """Insert or update wilayas; returns the number of active rows."""
    rows = rows or WILAYAS
    existing = {wilaya.code: wilaya for wilaya in db.scalars(select(Wilaya)).all()}
    for code, slug, name_ar, name_fr in rows:
        wilaya = existing.get(code)
        if wilaya is None:
            wilaya = Wilaya(
                code=code, slug=slug, name_ar=name_ar, name_fr=name_fr, is_active=True
            )
            db.add(wilaya)
        else:
            wilaya.slug = slug
            wilaya.name_ar = name_ar
            wilaya.name_fr = name_fr
            wilaya.is_active = True
    db.commit()
    return len(rows)


def seed_sectors(db: Session) -> int:
    """Insert or update the sector taxonomy."""
    existing = {sector.slug: sector for sector in db.scalars(select(Sector)).all()}
    for slug, name_ar, name_fr, sort_order in SECTORS:
        sector = existing.get(slug)
        if sector is None:
            db.add(
                Sector(
                    slug=slug,
                    name_ar=name_ar,
                    name_fr=name_fr,
                    sort_order=sort_order,
                    is_active=True,
                )
            )
        else:
            sector.name_ar = name_ar
            sector.name_fr = name_fr
            sector.sort_order = sort_order
            sector.is_active = True
    db.commit()
    return len(SECTORS)


def seed_issuers(db: Session) -> int:
    """Insert or update the issuer directory (linked to wilayas by code)."""
    wilayas = {wilaya.code: wilaya for wilaya in db.scalars(select(Wilaya)).all()}
    existing = {issuer.slug: issuer for issuer in db.scalars(select(Issuer)).all()}
    for slug, name_ar, name_fr, kind, wilaya_code in ISSUERS:
        issuer = existing.get(slug)
        if issuer is None:
            issuer = Issuer(slug=slug, name_ar=name_ar, name_fr=name_fr, is_active=True)
            db.add(issuer)
        issuer.name_ar = name_ar
        issuer.name_fr = name_fr
        issuer.kind = kind
        issuer.wilaya_id = wilayas[wilaya_code].id if wilaya_code in wilayas else None
        issuer.is_active = True
    db.commit()
    return len(ISSUERS)


def seed_plans(db: Session) -> int:
    """Insert or update subscription plans and the extra-sector add-on."""
    existing = {plan.code: plan for plan in db.scalars(select(Plan)).all()}
    for (
        code,
        name_ar,
        name_fr,
        kind,
        limit,
        auctions_only,
        monthly,
        annual,
        order,
    ) in PLANS:
        plan = existing.get(code)
        if plan is None:
            plan = Plan(code=code)
            db.add(plan)
        plan.name_ar = name_ar
        plan.name_fr = name_fr
        plan.kind = PlanKind(kind)
        plan.sector_limit = limit
        plan.auctions_only = auctions_only
        plan.price_monthly_dzd = monthly
        plan.price_annual_dzd = annual
        plan.is_price_placeholder = monthly > 0
        plan.sort_order = order
        plan.is_active = True
        plan.description_ar = plan.description_ar or ""
    db.commit()
    return len(PLANS)


def _sample_description(entry: dict) -> str:
    return str(entry.get("description_ar", "")).strip()


def seed_sample_announcements(db: Session) -> int:
    """Create the 24 demonstration announcements if they are absent.

    Idempotency key: ``(source_key='seed', external_id='sample-NN')``.
    Existing rows are left untouched so an editor's changes are never
    overwritten by a re-seed.
    """
    sectors = {sector.slug: sector for sector in db.scalars(select(Sector)).all()}
    wilayas = {wilaya.code: wilaya for wilaya in db.scalars(select(Wilaya)).all()}
    issuers = {issuer.slug: issuer for issuer in db.scalars(select(Issuer)).all()}
    existing = {
        announcement.external_id
        for announcement in db.scalars(
            select(Announcement).where(Announcement.source_key == "seed")
        ).all()
    }

    today = utcnow().date()
    created = 0
    for index, entry in enumerate(SAMPLES, start=1):
        external_id = f"sample-{index:02d}"
        if external_id in existing:
            continue
        publish_date = today - timedelta(days=int(entry["publish_days_ago"]))
        deadline = None
        if entry.get("deadline_in_days") is not None:
            deadline = datetime.combine(
                today + timedelta(days=int(entry["deadline_in_days"])), time(12, 0)
            )
        sector_objects = [sectors[slug] for slug in entry["sectors"] if slug in sectors]
        if not sector_objects:
            raise ValueError(f"Sample {external_id} references an unknown sector")
        if entry["wilaya"] not in wilayas:
            raise ValueError(f"Sample {external_id} references an unknown wilaya")
        issuer = issuers.get(entry["issuer"])

        announcement = Announcement(
            ref=f"DEMO-{publish_date.year}-{index:03d}",
            slug=slugify(entry["title_ar"], fallback=f"annonce-{index}"),
            type=AnnouncementType(entry["type"]),
            status=AnnouncementStatus.PUBLISHED,
            title_ar=entry["title_ar"],
            title_fr=entry.get("title_fr"),
            description_ar=_sample_description(entry),
            issuer_id=issuer.id if issuer else None,
            issuer_name=issuer.name_ar if issuer else "",
            wilaya_id=wilayas[entry["wilaya"]].id,
            reference=f"RÉF-DEMO-{publish_date.year}-{index:03d}",
            publish_date=publish_date,
            publish_year=publish_date.year,
            deadline_at=deadline,
            estimated_value_dzd=entry.get("value"),
            source_url=f"https://example.dz/annonces/demo-{index:02d}",
            source_name="بيانات تجريبية",
            is_sample=True,
            confidence=1.0,
            source_key="seed",
            external_id=external_id,
            published_at=datetime.combine(publish_date, time(9, 0)),
        )
        announcement.sectors = sector_objects
        db.add(announcement)
        db.flush()
        index_announcement(db, announcement)
        created += 1
    db.commit()
    return created


def seed_sample_offers(db: Session) -> int:
    """Create demonstration subcontracting offers when absent."""
    sectors = {sector.slug: sector for sector in db.scalars(select(Sector)).all()}
    wilayas = {wilaya.code: wilaya for wilaya in db.scalars(select(Wilaya)).all()}
    existing = {
        offer.title
        for offer in db.scalars(
            select(SubcontractingOffer).where(
                SubcontractingOffer.status.in_(
                    [SubcontractingStatus.PUBLISHED, SubcontractingStatus.PENDING]
                )
            )
        ).all()
    }
    created = 0
    now = utcnow()
    for entry in OFFERS:
        if entry["title"] in existing:
            continue
        status = SubcontractingStatus(entry["status"])
        offer = SubcontractingOffer(
            slug=slugify(entry["title"], fallback=f"offre-{created + 1}"),
            title=entry["title"],
            description=entry["description"],
            sector_id=sectors[entry["sector"]].id,
            wilaya_id=wilayas[entry["wilaya"]].id,
            issuer_name=entry["issuer_name"],
            contact_name=entry["contact_name"],
            contact_phone=entry["phone"],
            contact_email=entry["email"],
            deadline=(now + timedelta(days=int(entry["deadline_in_days"]))).date(),
            status=status,
            published_at=(
                now - timedelta(days=int(entry["days_ago"]))
                if status == SubcontractingStatus.PUBLISHED
                else None
            ),
        )
        db.add(offer)
        created += 1
    db.commit()
    return created


def seed_admin(db: Session, settings: Settings) -> bool:
    """Create the bootstrap admin when credentials are provided via env.

    No default password exists: without ``APP_ADMIN_PHONE`` and
    ``APP_ADMIN_PASSWORD`` nothing is created and a warning is logged.
    """
    if not settings.admin_phone or not settings.admin_password:
        logger.info("No bootstrap admin configured (APP_ADMIN_PHONE/PASSWORD empty)")
        return False
    phone = normalize_phone(settings.admin_phone)
    if phone is None:
        raise ValueError("APP_ADMIN_PHONE is not a valid Algerian phone number")
    password_error = validate_password(settings.admin_password)
    if password_error:
        raise ValueError(f"APP_ADMIN_PASSWORD rejected: {password_error}")
    existing = db.scalar(select(User).where(User.phone == phone))
    if existing is not None:
        return False
    db.add(
        User(
            phone=phone,
            email=settings.admin_email or None,
            company_name="إدارة المنصة",
            password_hash=hash_password(settings.admin_password),
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    db.commit()
    return True


def create_user(
    db: Session,
    *,
    phone: str,
    password: str,
    company_name: str = "",
    email: str | None = None,
    role: UserRole = UserRole.USER,
) -> User:
    """Create a user with validation; used by the CLI and tests.

    Raises:
        ValueError: Invalid phone, weak password or duplicate account.
    """
    normalized = normalize_phone(phone)
    if normalized is None:
        raise ValueError("رقم الهاتف غير صالح.")
    if validate_password(password):
        raise ValueError(validate_password(password) or "")
    if db.scalar(select(User).where(User.phone == normalized)) is not None:
        raise ValueError("رقم الهاتف مستعمل بالفعل.")
    user = User(
        phone=normalized,
        email=email,
        company_name=company_name,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        email_verified_at=utcnow() if email else None,
    )
    db.add(user)
    db.commit()
    return user


def seed_all(
    db: Session,
    *,
    with_demo: bool = True,
    settings: Settings | None = None,
    wilayas_override: list[tuple[str, str, str, str]] | None = None,
) -> SeedSummary:
    """Seed reference data (and optionally demo content) idempotently.

    Args:
        db: Session bound to the product database.
        with_demo: Also create the 24 sample announcements and offers. Use
            ``False`` in production.
        settings: When provided, an admin is created if its env credentials
            are present.
        wilayas_override: Alternative wilaya list (client's 69 entries).

    Returns:
        Counts of seeded entities.
    """
    summary = SeedSummary()
    summary.wilayas = seed_wilayas(db, wilayas_override)
    summary.sectors = seed_sectors(db)
    summary.issuers = seed_issuers(db)
    summary.plans = seed_plans(db)
    if settings is not None:
        summary.admin_created = seed_admin(db, settings)
    if with_demo:
        summary.announcements = seed_sample_announcements(db)
        summary.offers = seed_sample_offers(db)
    logger.info("Seed complete: %s", summary.as_dict())
    return summary


__all__ = [
    "SeedSummary",
    "create_user",
    "load_wilayas_override",
    "seed_admin",
    "seed_all",
    "seed_issuers",
    "seed_plans",
    "seed_sample_announcements",
    "seed_sample_offers",
    "seed_sectors",
    "seed_wilayas",
]
