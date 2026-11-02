"""SQLAlchemy 2.0 models for the Algerian public-procurement platform.

Design rules:

* Money is stored as integer DZD (``*_dzd``), never floats.
* Timestamps are naive UTC (``webapp.timeutils.utcnow``); the UI converts to
  Africa/Algiers.
* Taxonomy tables are seeded data, not code constants, so the client can edit
  them without a deployment.
* The announcement table carries a normalised ``search_text`` so the Arabic
  search index and the LIKE fallback share one representation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webapp.db import Base
from webapp.enums import (
    AlertFrequency,
    AnnouncementStatus,
    AnnouncementType,
    BannerPlacement,
    BillingPeriod,
    PaymentMethod,
    PaymentStatus,
    PlanKind,
    SubcontractingStatus,
    SubscriptionStatus,
    TokenPurpose,
    UserRole,
)
from webapp.timeutils import utcnow


def enum_column(enum_cls: type, **kwargs: Any) -> SAEnum:
    """Store the *value* of a ``StrEnum`` in a portable VARCHAR column."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=40,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
        **kwargs,
    )


class TimestampMixin:
    """Created/updated timestamps in UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------
class Wilaya(TimestampMixin, Base):
    """An Algerian wilaya (58 official codes; optional client extension)."""

    __tablename__ = "wilayas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(120), nullable=False)
    name_fr: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    issuers: Mapped[list[Issuer]] = relationship(back_populates="wilaya")
    announcements: Mapped[list[Announcement]] = relationship(back_populates="wilaya")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Wilaya {self.code} {self.name_ar}>"


class Sector(TimestampMixin, Base):
    """Procurement sector used by filters and subscription plans."""

    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(120), nullable=False)
    name_fr: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Sector {self.slug}>"


class Issuer(TimestampMixin, Base):
    """Public body that launches an announcement."""

    __tablename__ = "issuers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_fr: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(60))
    wilaya_id: Mapped[int | None] = mapped_column(ForeignKey("wilayas.id"))
    website: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    wilaya: Mapped[Wilaya | None] = relationship(back_populates="issuers")
    announcements: Mapped[list[Announcement]] = relationship(back_populates="issuer")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Issuer {self.slug}>"


# ---------------------------------------------------------------------------
# Accounts and billing
# ---------------------------------------------------------------------------
class User(TimestampMixin, Base):
    """A subscriber or staff account (login is phone + password)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    company_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole), default=UserRole.USER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    locale: Mapped[str] = mapped_column(String(5), default="ar", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Payment.user_id",
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    saved_announcements: Mapped[list[SavedAnnouncement]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_staff(self) -> bool:
        """Whether the account can access the admin area."""
        return self.role in {UserRole.ADMIN, UserRole.EDITOR, UserRole.SUPPORT}

    @property
    def display_name(self) -> str:
        """Company name when available, phone otherwise."""
        return self.company_name or self.phone

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User {self.id} {self.phone}>"


class Plan(TimestampMixin, Base):
    """Subscription tier or add-on. Prices are integer DZD placeholders."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(120), nullable=False)
    name_fr: Mapped[str] = mapped_column(String(120), nullable=False)
    description_ar: Mapped[str] = mapped_column(Text, default="", nullable=False)
    kind: Mapped[PlanKind] = mapped_column(
        enum_column(PlanKind), default=PlanKind.SUBSCRIPTION, nullable=False
    )
    sector_limit: Mapped[int | None] = mapped_column(Integer)
    auctions_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_monthly_dzd: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_annual_dzd: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_price_placeholder: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def annual_discount_percent(self) -> int:
        """Discount of the annual price versus twelve monthly payments."""
        full_year = self.price_monthly_dzd * 12
        if full_year <= 0 or self.price_annual_dzd <= 0:
            return 0
        return round((1 - self.price_annual_dzd / full_year) * 100)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Plan {self.code}>"


class Subscription(TimestampMixin, Base):
    """A user's access window, optionally restricted to chosen sectors."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_column(SubscriptionStatus),
        default=SubscriptionStatus.PENDING,
        nullable=False,
        index=True,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    billing_period: Mapped[BillingPeriod] = mapped_column(
        enum_column(BillingPeriod), default=BillingPeriod.MONTHLY, nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    user: Mapped[User] = relationship(back_populates="subscriptions")
    plan: Mapped[Plan] = relationship()
    sectors: Mapped[list[Sector]] = relationship(secondary="subscription_sectors")

    def is_active_at(self, moment: datetime) -> bool:
        """Whether the subscription grants access at ``moment`` (UTC)."""
        if self.status != SubscriptionStatus.ACTIVE:
            return False
        if self.starts_at is not None and self.starts_at > moment:
            return False
        return self.ends_at is None or self.ends_at > moment

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Subscription {self.id} user={self.user_id} {self.status}>"


class SubscriptionSector(Base):
    """Selected sectors of a subscription (composite primary key)."""

    __tablename__ = "subscription_sectors"

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True
    )
    sector_id: Mapped[int] = mapped_column(
        ForeignKey("sectors.id", ondelete="CASCADE"), primary_key=True
    )


class Payment(TimestampMixin, Base):
    """A manual payment awaiting staff verification."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    billing_period: Mapped[BillingPeriod] = mapped_column(
        enum_column(BillingPeriod), default=BillingPeriod.MONTHLY, nullable=False
    )
    method: Mapped[PaymentMethod] = mapped_column(
        enum_column(PaymentMethod), nullable=False
    )
    amount_dzd: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="DZD", nullable=False)
    reference: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    proof_filename: Mapped[str | None] = mapped_column(String(255))
    proof_original_name: Mapped[str | None] = mapped_column(String(255))
    proof_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    user: Mapped[User] = relationship(back_populates="payments", foreign_keys=[user_id])
    plan: Mapped[Plan] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Payment {self.id} {self.status}>"


class UserSession(Base):
    """Server-side session; only the SHA-256 hash of the cookie token is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    user: Mapped[User] = relationship(back_populates="sessions")


class OneTimeToken(Base):
    """Email-verification and password-reset tokens (Phase 2)."""

    __tablename__ = "one_time_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[TokenPurpose] = mapped_column(
        enum_column(TokenPurpose), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )


class RateLimitEvent(Base):
    """Fixed-window rate-limit hits; keys are SHA-256 hashes (no raw phone/IP)."""

    __tablename__ = "rate_limit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket: Mapped[str] = mapped_column(String(40), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_rate_limit_bucket_key_time", "bucket", "key_hash", "created_at"),
    )


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------
class Announcement(TimestampMixin, Base):
    """A published or draft procurement announcement."""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str | None] = mapped_column(String(40), unique=True)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    type: Mapped[AnnouncementType] = mapped_column(
        enum_column(AnnouncementType), nullable=False, index=True
    )
    status: Mapped[AnnouncementStatus] = mapped_column(
        enum_column(AnnouncementStatus),
        default=AnnouncementStatus.DRAFT,
        nullable=False,
        index=True,
    )
    title_ar: Mapped[str] = mapped_column(String(300), nullable=False)
    title_fr: Mapped[str | None] = mapped_column(String(300))
    description_ar: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description_fr: Mapped[str | None] = mapped_column(Text)
    issuer_id: Mapped[int | None] = mapped_column(
        ForeignKey("issuers.id", ondelete="SET NULL"), index=True
    )
    issuer_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    wilaya_id: Mapped[int] = mapped_column(
        ForeignKey("wilayas.id"), nullable=False, index=True
    )
    reference: Mapped[str | None] = mapped_column(String(120), index=True)
    publish_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    publish_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    estimated_value_dzd: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(String(600))
    source_name: Mapped[str | None] = mapped_column(String(120))
    search_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_sample: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="SET NULL")
    )
    source_key: Mapped[str | None] = mapped_column(String(80), index=True)
    external_id: Mapped[str | None] = mapped_column(String(200))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)

    issuer: Mapped[Issuer | None] = relationship(back_populates="announcements")
    wilaya: Mapped[Wilaya] = relationship(back_populates="announcements")
    sectors: Mapped[list[Sector]] = relationship(
        secondary="announcement_sectors", lazy="selectin"
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_announcements_status_publish", "status", "publish_date"),
        Index("ix_announcements_type_status", "type", "status"),
        UniqueConstraint(
            "source_key", "external_id", name="uq_announcement_source_external"
        ),
    )

    @property
    def is_open(self) -> bool:
        """Whether the deadline has not passed (or no deadline is known)."""
        return self.deadline_at is None or self.deadline_at > utcnow()

    @property
    def primary_sector(self) -> Sector | None:
        """First sector for card display."""
        return self.sectors[0] if self.sectors else None

    @property
    def primary_sector_name(self) -> str:
        """Arabic name of the first sector, or an empty string."""
        sector = self.primary_sector
        return sector.name_ar if sector else ""

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Announcement {self.id} {self.type} {self.title_ar[:30]!r}>"


class AnnouncementSector(Base):
    """Many-to-many announcement ↔ sector with a primary flag."""

    __tablename__ = "announcement_sectors"

    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True
    )
    sector_id: Mapped[int] = mapped_column(
        ForeignKey("sectors.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Attachment(Base):
    """A PDF/image attached to an announcement (upload checks in Phase 2/4)."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    announcement: Mapped[Announcement] = relationship(back_populates="attachments")


# ---------------------------------------------------------------------------
# User features
# ---------------------------------------------------------------------------
class SavedAnnouncement(Base):
    """A bookmark in the subscriber dashboard."""

    __tablename__ = "saved_announcements"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="saved_announcements")
    announcement: Mapped[Announcement] = relationship()


class Alert(TimestampMixin, Base):
    """Per-user digest preference (Phase 3 executes it)."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    frequency: Mapped[AlertFrequency] = mapped_column(
        enum_column(AlertFrequency), default=AlertFrequency.DAILY, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    unsubscribe_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )

    user: Mapped[User] = relationship()
    sectors: Mapped[list[Sector]] = relationship(
        secondary="alert_sectors", lazy="selectin"
    )
    wilayas: Mapped[list[Wilaya]] = relationship(
        secondary="alert_wilayas", lazy="selectin"
    )


class AlertSector(Base):
    """Sectors watched by an alert."""

    __tablename__ = "alert_sectors"

    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True
    )
    sector_id: Mapped[int] = mapped_column(
        ForeignKey("sectors.id", ondelete="CASCADE"), primary_key=True
    )


class AlertWilaya(Base):
    """Wilayas watched by an alert."""

    __tablename__ = "alert_wilayas"

    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True
    )
    wilaya_id: Mapped[int] = mapped_column(
        ForeignKey("wilayas.id", ondelete="CASCADE"), primary_key=True
    )


class AlertDelivery(Base):
    """Idempotency log: one row per (alert, announcement) ever delivered."""

    __tablename__ = "alert_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="sent", nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    error: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("alert_id", "announcement_id", name="uq_alert_delivery"),
    )


# ---------------------------------------------------------------------------
# Community and operations
# ---------------------------------------------------------------------------
class SubcontractingOffer(TimestampMixin, Base):
    """A subcontracting offer submitted for moderation."""

    __tablename__ = "subcontracting_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"), nullable=False)
    wilaya_id: Mapped[int] = mapped_column(ForeignKey("wilayas.id"), nullable=False)
    issuer_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    contact_email: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[SubcontractingStatus] = mapped_column(
        enum_column(SubcontractingStatus),
        default=SubcontractingStatus.PENDING,
        nullable=False,
        index=True,
    )
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    moderated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)

    sector: Mapped[Sector] = relationship()
    wilaya: Mapped[Wilaya] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<SubcontractingOffer {self.id} {self.title[:30]!r}>"


class Banner(TimestampMixin, Base):
    """An advertising banner slot."""

    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(300))
    target_url: Mapped[str] = mapped_column(String(600), nullable=False)
    placement: Mapped[BannerPlacement] = mapped_column(
        enum_column(BannerPlacement),
        default=BannerPlacement.HOME_MIDDLE,
        nullable=False,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SearchLog(Base):
    """Normalised search terms, used by the Phase 4 KPI dashboard."""

    __tablename__ = "search_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    term_normalized: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True
    )
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )


class AuditLog(Base):
    """Append-only trail for staff actions (Phase 4 writes it)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(60))
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )


__all__ = [
    "Alert",
    "AlertDelivery",
    "AlertSector",
    "AlertWilaya",
    "Announcement",
    "AnnouncementSector",
    "Attachment",
    "AuditLog",
    "Banner",
    "Issuer",
    "OneTimeToken",
    "Payment",
    "Plan",
    "RateLimitEvent",
    "SavedAnnouncement",
    "SearchLog",
    "Sector",
    "SubcontractingOffer",
    "Subscription",
    "SubscriptionSector",
    "User",
    "UserSession",
    "Wilaya",
]
