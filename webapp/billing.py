"""Subscriptions, manual payments and the maintenance jobs around them.

Flow implemented here:

1. a subscriber chooses a plan, a billing period, sectors and a payment method;
2. a **pending** subscription and a **pending** payment are created together;
3. the subscriber uploads a proof (bank transfer / postal account / cash
   receipt);
4. an administrator verifies the payment, which activates the subscription and
   starts the clock (one month or twelve);
5. a maintenance job expires ended subscriptions and emails renewal reminders
   once, seven days before the end by default.

Prices come from the seeded ``plans`` table and are still **placeholders**
(``is_price_placeholder``); this module never invents an amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from webapp.enums import (
    BillingPeriod,
    PaymentMethod,
    PaymentStatus,
    PlanKind,
    SubscriptionStatus,
)
from webapp.models import (
    AuditLog,
    Payment,
    Plan,
    Sector,
    Subscription,
    User,
)
from webapp.timeutils import format_date_ar, is_expiring_soon, subscription_end, utcnow
from webapp.uploads import StoredFile


class BillingError(Exception):
    """A billing rule violation with an Arabic message."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class BillingSummary:
    """Outcome of :func:`run_maintenance`."""

    expired: int = 0
    reminders_sent: int = 0
    reminders_failed: int = 0

    def as_dict(self) -> dict[str, int]:
        """Serialise for CLI output and logs."""
        return {
            "expired": self.expired,
            "reminders_sent": self.reminders_sent,
            "reminders_failed": self.reminders_failed,
        }


def plan_price(plan: Plan, period: BillingPeriod) -> int:
    """Price of a plan for one billing period."""
    if period == BillingPeriod.ANNUAL:
        return int(plan.price_annual_dzd or 0)
    return int(plan.price_monthly_dzd or 0)


def addon_price(db: Session) -> int:
    """Monthly price of one extra sector (the ``extra_sector`` add-on)."""
    addon = db.scalar(
        select(Plan).where(Plan.code == "extra_sector", Plan.kind == PlanKind.ADDON)
    )
    return int(addon.price_monthly_dzd) if addon else 0


def extra_sector_count(plan: Plan, selected: int) -> int:
    """How many selected sectors exceed the plan's included limit."""
    if plan.sector_limit is None:
        return 0
    return max(0, selected - plan.sector_limit)


def quote(db: Session, plan: Plan, period: BillingPeriod, sector_count: int) -> int:
    """Total amount for a plan selection, including extra-sector add-ons."""
    base = plan_price(plan, period)
    extras = extra_sector_count(plan, sector_count)
    if not extras:
        return base
    per_sector = addon_price(db)
    return (
        base
        + (per_sector * 12 if period == BillingPeriod.ANNUAL else per_sector) * extras
    )


def active_plans(db: Session) -> list[Plan]:
    """Subscription plans offered on the pricing and checkout pages."""
    return list(
        db.scalars(
            select(Plan)
            .where(
                Plan.is_active.is_(True),
                Plan.kind == PlanKind.SUBSCRIPTION,
                Plan.code != "free",
            )
            .order_by(Plan.sort_order)
        ).all()
    )


def get_plan(db: Session, code: str) -> Plan | None:
    """Fetch a purchasable plan by code."""
    return db.scalar(
        select(Plan).where(
            Plan.code == (code or "").strip(),
            Plan.is_active.is_(True),
            Plan.kind == PlanKind.SUBSCRIPTION,
        )
    )


def _sectors(db: Session, sector_ids: list[int]) -> list[Sector]:
    if not sector_ids:
        return []
    return list(
        db.scalars(
            select(Sector).where(Sector.id.in_(sector_ids), Sector.is_active.is_(True))
        ).all()
    )


def create_subscription_request(
    db: Session,
    user: User,
    *,
    plan: Plan,
    period: BillingPeriod,
    sector_ids: list[int],
    method: PaymentMethod,
    reference: str = "",
    now: datetime | None = None,
) -> tuple[Subscription, Payment]:
    """Create a pending subscription and its pending payment.

    Raises:
        BillingError: Unknown sectors, sector limit exceeded without an add-on,
            or a missing transfer reference.
    """
    if plan.code == "free":
        raise BillingError("الصيغة المجانية لا تتطلب دفعاً.")

    sectors = _sectors(db, sector_ids)
    if len(sectors) != len(set(sector_ids)):
        raise BillingError("أحد القطاعات المختارة غير متوفر.")

    if plan.auctions_only:
        sectors = []  # auctions-only grants every sector for auctions
    elif plan.sector_limit is None:
        sectors = []  # Platinum and similar cover every sector
    elif not sectors:
        raise BillingError("اختر قطاعاً واحداً على الأقل.")

    if plan.sector_limit is not None and len(sectors) > plan.sector_limit:
        if addon_price(db) <= 0:
            raise BillingError("عدد القطاعات يتجاوز ما تشمله الصيغة المختارة.")
        if len(sectors) > 16:
            raise BillingError("عدد القطاعات المختارة يتجاوز العدد المتاح.")

    reference = (reference or "").strip()
    if (
        method in {PaymentMethod.BANK_TRANSFER, PaymentMethod.POSTAL_ACCOUNT}
        and not 3 <= len(reference) <= 120
    ):
        raise BillingError("أدخل مرجع التحويل أو رقم الوصل (3 إلى 120 حرفاً).")

    amount = quote(db, plan, period, len(sectors))
    if amount <= 0:
        raise BillingError("سعر هذه الصيغة غير محدد بعد. تواصل معنا.")

    moment = now or utcnow()
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.PENDING,
        billing_period=period,
        starts_at=None,
        ends_at=None,
        notes="بانتظار تأكيد الدفع",
    )
    subscription.sectors = sectors
    db.add(subscription)
    db.flush()

    payment = Payment(
        user_id=user.id,
        subscription_id=subscription.id,
        plan_id=plan.id,
        billing_period=period,
        method=method,
        amount_dzd=amount,
        reference=reference,
        status=PaymentStatus.PENDING,
        submitted_at=moment,
    )
    db.add(payment)
    db.commit()
    db.refresh(subscription)
    db.refresh(payment)
    return subscription, payment


def pending_payment(db: Session, user: User, payment_id: int) -> Payment | None:
    """Fetch one of the user's own pending payments."""
    return db.scalar(
        select(Payment)
        .options(selectinload(Payment.plan), selectinload(Payment.subscription))
        .where(
            Payment.id == payment_id,
            Payment.user_id == user.id,
            Payment.status == PaymentStatus.PENDING,
        )
    )


def attach_proof(db: Session, payment: Payment, stored: StoredFile) -> Payment:
    """Attach validated proof metadata to a pending payment."""
    if payment.status != PaymentStatus.PENDING:
        raise BillingError("لا يمكن تعديل وصل دفع تمت معالجته.")
    payment.proof_filename = stored.stored_name
    payment.proof_original_name = stored.original_name
    payment.proof_sha256 = stored.sha256
    payment.proof_content_type = stored.content_type
    payment.proof_size_bytes = stored.size_bytes
    db.commit()
    db.refresh(payment)
    return payment


def verify_payment(
    db: Session,
    payment: Payment,
    *,
    admin: User,
    approve: bool,
    notes: str = "",
    now: datetime | None = None,
) -> Subscription | None:
    """Approve or reject a manual payment.

    Approving activates the linked subscription and cancels any other active
    subscription of the same user so entitlements stay unambiguous.
    """
    if payment.status != PaymentStatus.PENDING:
        raise BillingError("هذا الوصل عولج مسبقاً.")
    moment = now or utcnow()
    payment.verified_at = moment
    payment.verified_by_id = admin.id
    payment.admin_notes = (notes or "").strip()[:1000]

    subscription = db.get(Subscription, payment.subscription_id)
    if not approve:
        payment.status = PaymentStatus.REJECTED
        if subscription is not None:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = moment
        db.add(
            AuditLog(
                actor_user_id=admin.id,
                action="payment.reject",
                entity_type="payment",
                entity_id=str(payment.id),
                meta={"notes": payment.admin_notes},
            )
        )
        db.commit()
        return subscription

    if payment.proof_filename is None:
        raise BillingError("لا يمكن تأكيد دفع دون وصل مرفق.")

    payment.status = PaymentStatus.VERIFIED
    if subscription is None:
        subscription = Subscription(
            user_id=payment.user_id,
            plan_id=payment.plan_id,
            billing_period=payment.billing_period,
            status=SubscriptionStatus.ACTIVE,
            starts_at=moment,
            ends_at=subscription_end(
                moment, annual=payment.billing_period == BillingPeriod.ANNUAL
            ),
        )
        db.add(subscription)
    else:
        previous = db.scalars(
            select(Subscription).where(
                Subscription.user_id == payment.user_id,
                Subscription.id != subscription.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        ).all()
        for stale in previous:
            stale.status = SubscriptionStatus.CANCELLED
            stale.cancelled_at = moment
            stale.notes = "استُبدل باشتراك جديد"

        subscription.status = SubscriptionStatus.ACTIVE
        subscription.starts_at = moment
        subscription.ends_at = subscription_end(
            moment, annual=payment.billing_period == BillingPeriod.ANNUAL
        )
        subscription.cancelled_at = None
        subscription.reminder_sent_at = None

    db.add(
        AuditLog(
            actor_user_id=admin.id,
            action="payment.verify",
            entity_type="payment",
            entity_id=str(payment.id),
            meta={
                "amount_dzd": payment.amount_dzd,
                "subscription_id": payment.subscription_id,
            },
        )
    )
    db.commit()
    db.refresh(subscription)
    return subscription


def expire_subscriptions(db: Session, *, now: datetime | None = None) -> int:
    """Mark ended active subscriptions as expired (idempotent)."""
    moment = now or utcnow()
    rows = db.scalars(
        select(Subscription).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.ends_at.is_not(None),
            Subscription.ends_at <= moment,
        )
    ).all()
    for subscription in rows:
        subscription.status = SubscriptionStatus.EXPIRED
    if rows:
        db.commit()
    return len(rows)


def due_reminders(
    db: Session, *, days: int = 7, now: datetime | None = None
) -> list[Subscription]:
    """Active subscriptions ending soon that were not reminded yet."""
    moment = now or utcnow()
    return list(
        db.scalars(
            select(Subscription)
            .options(
                selectinload(Subscription.plan),
                selectinload(Subscription.user),
            )
            .join(User)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.reminder_sent_at.is_(None),
                Subscription.ends_at.is_not(None),
                Subscription.ends_at > moment,
                Subscription.ends_at <= moment + timedelta(days=days),
                User.email.is_not(None),
            )
            .order_by(Subscription.ends_at)
        ).all()
    )


def run_maintenance(
    db: Session,
    *,
    days: int = 7,
    now: datetime | None = None,
    send=None,
) -> BillingSummary:
    """Expire subscriptions and send renewal reminders at most once each.

    Args:
        db: Session.
        days: Reminder window in days.
        now: Clock injection.
        send: Callable receiving ``(subscription)`` and sending the email.
    """
    moment = now or utcnow()
    expired = expire_subscriptions(db, now=moment)
    sent = 0
    failed = 0

    candidates = [
        subscription
        for subscription in due_reminders(db, days=days, now=moment)
        if is_expiring_soon(subscription.ends_at, days=days, now=moment)
    ]
    for subscription in candidates:
        try:
            if send is not None:
                send(subscription)
        except Exception:  # pragma: no cover - transport failure path
            failed += 1
            continue
        subscription.reminder_sent_at = moment
        sent += 1
    if sent:
        db.commit()
    return BillingSummary(expired=expired, reminders_sent=sent, reminders_failed=failed)


def plan_amount_label(subscription: Subscription) -> str:
    """Human label of the amount and period for templates."""
    return "سنوي" if subscription.billing_period == BillingPeriod.ANNUAL else "شهري"


def reminder_body_dates(subscription: Subscription) -> str:
    """Format the subscription end date for the reminder email."""
    return format_date_ar(subscription.ends_at) if subscription.ends_at else "—"


__all__ = [
    "BillingError",
    "BillingSummary",
    "active_plans",
    "addon_price",
    "attach_proof",
    "create_subscription_request",
    "due_reminders",
    "expire_subscriptions",
    "extra_sector_count",
    "get_plan",
    "pending_payment",
    "plan_amount_label",
    "plan_price",
    "quote",
    "reminder_body_dates",
    "run_maintenance",
    "verify_payment",
]
