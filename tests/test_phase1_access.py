"""Plan-based access rules: free vs paid, sectors, auctions-only, expiry."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.conftest import make_user, subscribe
from webapp.access import (
    REASON_ANONYMOUS,
    REASON_AUCTIONS_ONLY,
    REASON_FREE_PLAN,
    REASON_STAFF,
    REASON_SUBSCRIBED,
    REASON_UNCOVERED_SECTOR,
    build_announcement_view,
    build_offer_view,
)
from webapp.entitlements import FREE_PLAN_CODE, resolve_entitlements
from webapp.enums import (
    AnnouncementType,
    SubcontractingStatus,
    SubscriptionStatus,
    UserRole,
)
from webapp.models import Announcement, SubcontractingOffer
from webapp.timeutils import utcnow


def _announcement(db, title_part: str) -> Announcement:
    return db.scalar(
        select(Announcement).where(Announcement.title_ar.contains(title_part))
    )


def test_anonymous_is_free_and_locked(seeded) -> None:
    db = seeded
    announcement = _announcement(db, "أنابيب PVC")
    entitlements = resolve_entitlements(db, None)
    view = build_announcement_view(entitlements, announcement)

    assert entitlements.plan_code == FREE_PLAN_CODE
    assert not entitlements.is_paid
    assert not view.unlocked
    assert view.reason == REASON_ANONYMOUS
    assert view.issuer_name is None
    assert view.deadline_at is None
    assert view.description_ar is None
    assert view.description_fr is None
    assert view.reference is None
    assert view.source_url is None
    assert view.estimated_value_dzd is None
    assert view.attachments == ()
    assert view.show_locked_notice


def test_free_plan_user_stays_locked(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000001")
    entitlements = resolve_entitlements(db, user)
    view = build_announcement_view(entitlements, _announcement(db, "أنابيب PVC"))

    assert entitlements.is_authenticated
    assert not entitlements.is_paid
    assert view.reason == REASON_FREE_PLAN
    assert view.issuer_name is None


def test_gold_water_subscription_unlocks_water_announcement(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000002")
    subscribe(db, user, plan_code="gold", sector_slugs=("water",))
    entitlements = resolve_entitlements(db, user)
    announcement = _announcement(db, "أنابيب PVC")
    view = build_announcement_view(entitlements, announcement)

    assert entitlements.is_paid
    assert entitlements.plan_code == "gold"
    assert view.unlocked
    assert view.reason == REASON_SUBSCRIBED
    assert view.issuer_name == "الجزائرية للمياه"
    assert view.deadline_at is not None
    assert view.description_ar
    assert view.reference
    assert view.estimated_value_dzd == 18_500_000


def test_uncovered_sector_is_locked(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000003")
    subscribe(db, user, plan_code="bronze", sector_slugs=("health",))
    entitlements = resolve_entitlements(db, user)
    view = build_announcement_view(entitlements, _announcement(db, "أنابيب PVC"))

    assert not view.unlocked
    assert view.reason == REASON_UNCOVERED_SECTOR
    assert view.issuer_name is None


def test_platinum_covers_every_sector(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000004")
    subscribe(db, user, plan_code="platinum", sector_slugs=())
    entitlements = resolve_entitlements(db, user)
    assert entitlements.all_sectors
    assert build_announcement_view(
        entitlements, _announcement(db, "تهيئة الطرق")
    ).unlocked
    assert build_announcement_view(
        entitlements, _announcement(db, "فسخ عقد صيانة")
    ).unlocked


def test_auctions_only_plan_limits_to_auctions(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000005")
    subscribe(db, user, plan_code="auctions_only", sector_slugs=())
    entitlements = resolve_entitlements(db, user)

    auction = db.scalar(
        select(Announcement).where(Announcement.type == AnnouncementType.AUCTION)
    )
    tender = db.scalar(
        select(Announcement).where(Announcement.type == AnnouncementType.TENDER)
    )
    assert build_announcement_view(entitlements, auction).unlocked
    locked = build_announcement_view(entitlements, tender)
    assert not locked.unlocked
    assert locked.reason == REASON_AUCTIONS_ONLY


def test_expired_subscription_falls_back_to_free(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000006")
    subscribe(
        db,
        user,
        plan_code="platinum",
        sector_slugs=(),
        starts_days=-40,
        ends_days=-1,
    )
    entitlements = resolve_entitlements(db, user)
    view = build_announcement_view(entitlements, _announcement(db, "أنابيب PVC"))

    assert entitlements.plan_code == FREE_PLAN_CODE
    assert not view.unlocked
    assert view.reason == REASON_FREE_PLAN


def test_pending_subscription_grants_nothing(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000007")
    subscribe(
        db,
        user,
        plan_code="platinum",
        sector_slugs=(),
        status=SubscriptionStatus.PENDING,
    )
    assert resolve_entitlements(db, user).plan_code == FREE_PLAN_CODE


def test_subscription_active_at_boundaries(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000008")
    subscription = subscribe(db, user, plan_code="gold", sector_slugs=("water",))

    now = utcnow()
    assert subscription.is_active_at(now)
    assert not subscription.is_active_at(subscription.ends_at + timedelta(seconds=1))
    assert not subscription.is_active_at(subscription.starts_at - timedelta(seconds=1))


def test_staff_sees_everything_without_subscription(seeded) -> None:
    db = seeded
    admin = make_user(db, phone="0555000009", role=UserRole.ADMIN)
    entitlements = resolve_entitlements(db, admin)
    view = build_announcement_view(entitlements, _announcement(db, "أنابيب PVC"))

    assert entitlements.is_staff
    assert view.unlocked
    assert view.reason == REASON_STAFF
    assert view.issuer_name == "الجزائرية للمياه"


def test_inactive_user_is_anonymous(seeded) -> None:
    db = seeded
    user = make_user(db, phone="0555000010")
    user.is_active = False
    db.commit()
    assert not resolve_entitlements(db, user).is_authenticated


def test_offer_contact_is_gated() -> None:
    from webapp.entitlements import ANONYMOUS, Entitlements

    offer = SubcontractingOffer(
        slug="test",
        title="عرض",
        description="",
        sector_id=1,
        wilaya_id=1,
        status=SubcontractingStatus.PUBLISHED,
    )
    assert not build_offer_view(ANONYMOUS, offer).show_contact
    free_user = Entitlements(
        is_authenticated=True, plan_code="free", sector_ids=frozenset()
    )
    assert not build_offer_view(free_user, offer).show_contact
    paid = Entitlements(
        is_authenticated=True,
        plan_code="gold",
        sector_ids=frozenset({1}),
        subscription_ends_at=utcnow(),
    )
    assert build_offer_view(paid, offer).show_contact
    staff = Entitlements(is_authenticated=True, is_staff=True, plan_code="staff")
    assert build_offer_view(staff, offer).show_contact


@pytest.mark.parametrize("days_ahead,expected", [(1, True), (10, False)])
def test_resolve_entitlements_uses_injected_clock(seeded, days_ahead, expected) -> None:
    db = seeded
    user = make_user(db, phone=f"05550003{days_ahead:02d}")
    subscribe(
        db, user, plan_code="gold", sector_slugs=("water",), starts_days=-1, ends_days=3
    )
    entitlements = resolve_entitlements(
        db, user, now=utcnow() + timedelta(days=days_ahead)
    )
    assert (entitlements.plan_code != FREE_PLAN_CODE) is expected
