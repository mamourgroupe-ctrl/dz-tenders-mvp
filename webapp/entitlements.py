"""Resolve what a visitor/subscriber may see, from the database.

The result is a plain immutable object; templates and routes never query
subscription state themselves, so access rules have exactly one home and can be
unit-tested without HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from webapp.enums import SubscriptionStatus, UserRole
from webapp.models import Subscription, User
from webapp.timeutils import utcnow

FREE_PLAN_CODE = "free"


@dataclass(frozen=True)
class Entitlements:
    """Effective access rights at a given moment.

    Attributes:
        is_authenticated: Whether a valid session resolved to a user.
        is_staff: Admin/editor/support accounts see everything.
        plan_code: Active plan code, ``free`` when none is active.
        plan_name_ar: Human-readable plan name.
        sector_ids: Covered sectors; ``None`` means every sector.
        auctions_only: Plan restricted to auction announcements.
        subscription_ends_at: End of the current paid period, if any.
        user_id: Account id (None for anonymous visitors).
    """

    is_authenticated: bool = False
    is_staff: bool = False
    plan_code: str = FREE_PLAN_CODE
    plan_name_ar: str = "مجاني"
    sector_ids: frozenset[int] | None = frozenset()
    auctions_only: bool = False
    subscription_ends_at: datetime | None = None
    user_id: int | None = None

    @property
    def is_paid(self) -> bool:
        """Whether an active non-free plan grants full announcement details."""
        return self.plan_code not in {FREE_PLAN_CODE, "staff", ""}

    @property
    def all_sectors(self) -> bool:
        """Whether the plan covers every sector."""
        return self.sector_ids is None

    def covers_sector(self, sector_ids: list[int]) -> bool:
        """Whether at least one of the announcement sectors is covered."""
        if self.is_staff or self.all_sectors:
            return True
        if not sector_ids:
            return self.is_paid
        return bool(self.sector_ids and set(sector_ids) & self.sector_ids)


ANONYMOUS = Entitlements()


def resolve_entitlements(
    db: Session, user: User | None, *, now: datetime | None = None
) -> Entitlements:
    """Compute the effective entitlements of ``user``.

    Args:
        db: Session used for the subscription lookup.
        user: Authenticated user or ``None``.
        now: Clock injection for deterministic expiry tests.

    Returns:
        Free entitlements for anonymous/expired accounts, otherwise the active
        plan plus its sector set.
    """
    if user is None or not user.is_active:
        return ANONYMOUS

    moment = now or utcnow()

    if user.role in {UserRole.ADMIN, UserRole.EDITOR, UserRole.SUPPORT}:
        return Entitlements(
            is_authenticated=True,
            is_staff=True,
            plan_code="staff",
            plan_name_ar="فريق الإدارة",
            sector_ids=None,
            user_id=user.id,
        )

    subscription = db.scalar(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .options(selectinload(Subscription.plan), selectinload(Subscription.sectors))
        .order_by(Subscription.ends_at.desc().nullslast(), Subscription.id.desc())
    )

    if subscription is None or not subscription.is_active_at(moment):
        return Entitlements(
            is_authenticated=True,
            plan_code=FREE_PLAN_CODE,
            plan_name_ar="مجاني",
            sector_ids=frozenset(),
            user_id=user.id,
        )

    sectors = frozenset(sector.id for sector in subscription.sectors)
    all_sectors = subscription.plan.sector_limit is None
    return Entitlements(
        is_authenticated=True,
        plan_code=subscription.plan.code,
        plan_name_ar=subscription.plan.name_ar,
        sector_ids=None if all_sectors else sectors,
        auctions_only=subscription.plan.auctions_only,
        subscription_ends_at=subscription.ends_at,
        user_id=user.id,
    )


__all__ = ["ANONYMOUS", "Entitlements", "FREE_PLAN_CODE", "resolve_entitlements"]
