"""Manual payments, subscription activation, expiry and proof uploads."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from tests.conftest import login, make_user, subscribe
from webapp import billing
from webapp.access import build_announcement_view
from webapp.entitlements import resolve_entitlements
from webapp.enums import (
    BillingPeriod,
    PaymentMethod,
    PaymentStatus,
    SubscriptionStatus,
    UserRole,
)
from webapp.models import (
    Announcement,
    AuditLog,
    Payment,
    Plan,
    Sector,
    Subscription,
    User,
)
from webapp.timeutils import utcnow
from webapp.uploads import (
    StoredFile,
    UploadError,
    clean_original_name,
    resolve_stored,
    sniff_content_type,
    store_upload,
    validate_upload,
)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24


def plan(db, code: str) -> Plan:
    found = db.scalar(select(Plan).where(Plan.code == code))
    assert found is not None, f"unknown plan: {code}"
    return found


def sector_id(db, slug: str) -> int:
    found = db.scalar(select(Sector.id).where(Sector.slug == slug))
    assert found is not None, f"unknown sector: {slug}"
    return found


def water_announcement(db) -> Announcement:
    announcement = db.scalar(
        select(Announcement).where(Announcement.title_ar.contains("أنابيب PVC"))
    )
    assert announcement is not None
    return announcement


def csrf(client) -> str:
    client.get("/connexion")
    return client.cookies.get("dz_csrf")


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
def test_plan_price_follows_billing_period(seeded) -> None:
    gold = plan(seeded, "gold")
    assert billing.plan_price(gold, BillingPeriod.MONTHLY) == 8000
    assert billing.plan_price(gold, BillingPeriod.ANNUAL) == 80000


def test_quote_matches_plan_price_without_extra_sectors(seeded) -> None:
    gold = plan(seeded, "gold")
    assert billing.quote(seeded, gold, BillingPeriod.MONTHLY, 4) == 8000
    assert billing.quote(seeded, gold, BillingPeriod.ANNUAL, 6) == 80000


def test_quote_charges_addon_per_extra_sector(seeded) -> None:
    gold = plan(seeded, "gold")  # 6 sectors included, add-on 800/month
    assert billing.extra_sector_count(gold, 8) == 2
    assert billing.quote(seeded, gold, BillingPeriod.MONTHLY, 8) == 8000 + 2 * 800
    assert billing.quote(seeded, gold, BillingPeriod.ANNUAL, 8) == 80000 + 2 * 800 * 12


def test_platinum_covers_every_sector_without_addon(seeded) -> None:
    platinum = plan(seeded, "platinum")
    assert platinum.sector_limit is None
    assert billing.extra_sector_count(platinum, 16) == 0
    assert billing.quote(seeded, platinum, BillingPeriod.MONTHLY, 16) == 18000


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------
def test_sniff_content_type_reads_magic_bytes() -> None:
    assert sniff_content_type(PDF) == ("application/pdf", ".pdf")
    assert sniff_content_type(JPEG) == ("image/jpeg", ".jpg")
    assert sniff_content_type(PNG) == ("image/png", ".png")
    assert sniff_content_type(b"MZ\x90\x00") is None


def test_validate_upload_rejects_empty_file() -> None:
    with pytest.raises(UploadError, match="فارغ"):
        validate_upload(
            b"", original_name="x.pdf", declared_type="application/pdf", max_bytes=1000
        )


def test_validate_upload_rejects_oversized_file() -> None:
    with pytest.raises(UploadError, match="يتجاوز الحدّ"):
        validate_upload(
            PDF + b"0" * 100,
            original_name="x.pdf",
            declared_type="application/pdf",
            max_bytes=50,
        )


def test_validate_upload_rejects_unknown_magic() -> None:
    with pytest.raises(UploadError, match="PDF أو صورة"):
        validate_upload(
            b"MZ\x90\x00 not a proof",
            original_name="proof.pdf",
            declared_type="application/pdf",
            max_bytes=1000,
        )


def test_validate_upload_rejects_mismatched_declared_type() -> None:
    with pytest.raises(UploadError, match="لا يطابق"):
        validate_upload(
            PDF, original_name="x.pdf", declared_type="image/png", max_bytes=1000
        )


def test_validate_upload_rejects_unsupported_declared_type() -> None:
    with pytest.raises(UploadError, match="غير مدعوم"):
        validate_upload(
            PDF, original_name="x.pdf", declared_type="text/plain", max_bytes=1000
        )


def test_store_upload_writes_random_name_and_hash(settings) -> None:
    stored = store_upload(
        PNG,
        original_name="../../etc/passwd.png",
        declared_type="image/png",
        settings=settings,
    )
    assert stored.stored_name.startswith("payments/")
    assert ".." not in stored.stored_name
    assert stored.stored_name.endswith(".png")
    assert "/etc" not in stored.original_name
    assert stored.content_type == "image/png"
    assert stored.size_bytes == len(PNG)
    assert len(stored.sha256) == 64
    written = (Path(settings.upload_dir) / stored.stored_name).read_bytes()
    assert written == PNG


def test_clean_original_name_strips_separators_and_controls() -> None:
    assert clean_original_name("C:\\Users\\x\\وصل.pdf") == "C:_Users_x_وصل.pdf"
    assert clean_original_name("...") == "proof"


def test_resolve_stored_blocks_traversal(settings, tmp_path) -> None:
    (tmp_path / "secret.pdf").write_bytes(PDF)
    assert resolve_stored(settings, "../secret.pdf") is None
    assert resolve_stored(settings, "payments/missing.pdf") is None


# ---------------------------------------------------------------------------
# Subscription requests
# ---------------------------------------------------------------------------
def test_create_request_creates_pending_subscription_and_payment(seeded) -> None:
    user = make_user(seeded, phone="0555300001")
    gold = plan(seeded, "gold")

    subscription, payment = billing.create_subscription_request(
        seeded,
        user,
        plan=gold,
        period=BillingPeriod.MONTHLY,
        sector_ids=[sector_id(seeded, "water"), sector_id(seeded, "health")],
        method=PaymentMethod.CASH,
    )

    assert subscription.status == SubscriptionStatus.PENDING
    assert subscription.starts_at is None and subscription.ends_at is None
    assert [sector.slug for sector in subscription.sectors] == ["water", "health"]
    assert payment.status == PaymentStatus.PENDING
    assert payment.amount_dzd == 8000
    assert payment.subscription_id == subscription.id
    assert payment.currency == "DZD"


def test_create_request_requires_transfer_reference(seeded) -> None:
    user = make_user(seeded, phone="0555300002")
    with pytest.raises(billing.BillingError, match="مرجع التحويل"):
        billing.create_subscription_request(
            seeded,
            user,
            plan=plan(seeded, "gold"),
            period=BillingPeriod.MONTHLY,
            sector_ids=[sector_id(seeded, "water")],
            method=PaymentMethod.BANK_TRANSFER,
            reference="  ",
        )


def test_create_request_rejects_free_plan_and_unknown_sector(seeded) -> None:
    user = make_user(seeded, phone="0555300003")
    with pytest.raises(billing.BillingError, match="المجانية"):
        billing.create_subscription_request(
            seeded,
            user,
            plan=plan(seeded, "free"),
            period=BillingPeriod.MONTHLY,
            sector_ids=[],
            method=PaymentMethod.CASH,
        )
    with pytest.raises(billing.BillingError, match="غير متوفر"):
        billing.create_subscription_request(
            seeded,
            user,
            plan=plan(seeded, "gold"),
            period=BillingPeriod.MONTHLY,
            sector_ids=[999_999],
            method=PaymentMethod.CASH,
        )


def test_create_request_requires_sector_for_limited_plan(seeded) -> None:
    user = make_user(seeded, phone="0555300004")
    with pytest.raises(billing.BillingError, match="قطاعاً واحداً"):
        billing.create_subscription_request(
            seeded,
            user,
            plan=plan(seeded, "gold"),
            period=BillingPeriod.MONTHLY,
            sector_ids=[],
            method=PaymentMethod.CASH,
        )


def test_platinum_and_auctions_plans_store_no_sector_rows(seeded) -> None:
    user = make_user(seeded, phone="0555300005")
    subscription, _ = billing.create_subscription_request(
        seeded,
        user,
        plan=plan(seeded, "platinum"),
        period=BillingPeriod.ANNUAL,
        sector_ids=[sector_id(seeded, "water")],
        method=PaymentMethod.CASH,
    )
    assert subscription.sectors == []

    auctions, _ = billing.create_subscription_request(
        seeded,
        user,
        plan=plan(seeded, "auctions_only"),
        period=BillingPeriod.MONTHLY,
        sector_ids=[sector_id(seeded, "water")],
        method=PaymentMethod.CASH,
    )
    assert auctions.sectors == []


# ---------------------------------------------------------------------------
# Verification, rejection, expiry and reminders
# ---------------------------------------------------------------------------
def _pending_payment(db, user: User, *, with_proof: bool = True) -> Payment:
    _subscription, payment = billing.create_subscription_request(
        db,
        user,
        plan=plan(db, "gold"),
        period=BillingPeriod.MONTHLY,
        sector_ids=[sector_id(db, "water")],
        method=PaymentMethod.CASH,
    )
    if with_proof:
        billing.attach_proof(
            db,
            payment,
            StoredFile(
                stored_name="payments/proof.pdf",
                original_name="proof.pdf",
                content_type="application/pdf",
                size_bytes=len(PDF),
                sha256="0" * 64,
            ),
        )
    return payment


def test_verify_payment_requires_a_proof(seeded) -> None:
    admin = make_user(seeded, phone="0555300100", role=UserRole.ADMIN)
    user = make_user(seeded, phone="0555300101")
    payment = _pending_payment(seeded, user, with_proof=False)

    with pytest.raises(billing.BillingError, match="دون وصل"):
        billing.verify_payment(seeded, payment, admin=admin, approve=True)


def test_approving_payment_activates_and_cancels_other_subscriptions(seeded) -> None:
    admin = make_user(seeded, phone="0555300102", role=UserRole.ADMIN)
    user = make_user(seeded, phone="0555300103")
    previous = subscribe(seeded, user, plan_code="bronze", sector_slugs=("health",))
    payment = _pending_payment(seeded, user)

    now = utcnow()
    subscription = billing.verify_payment(
        seeded, payment, admin=admin, approve=True, notes="وصل مطابق", now=now
    )

    assert subscription is not None
    assert payment.status == PaymentStatus.VERIFIED
    assert payment.verified_by_id == admin.id
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.starts_at == now
    assert subscription.ends_at == now + timedelta(days=30)
    assert subscription.reminder_sent_at is None

    seeded.refresh(previous)
    assert previous.status == SubscriptionStatus.CANCELLED
    assert previous.cancelled_at == now

    action = seeded.scalar(select(AuditLog).where(AuditLog.action == "payment.verify"))
    assert action is not None and action.actor_user_id == admin.id


def test_annual_payment_activates_for_a_year(seeded) -> None:
    admin = make_user(seeded, phone="0555300104", role=UserRole.ADMIN)
    user = make_user(seeded, phone="0555300105")
    _subscription, payment = billing.create_subscription_request(
        seeded,
        user,
        plan=plan(seeded, "gold"),
        period=BillingPeriod.ANNUAL,
        sector_ids=[sector_id(seeded, "water")],
        method=PaymentMethod.CASH,
    )
    billing.attach_proof(
        seeded,
        payment,
        StoredFile("payments/a.pdf", "a.pdf", "application/pdf", 10, "0" * 64),
    )
    now = utcnow()
    subscription = billing.verify_payment(
        seeded, payment, admin=admin, approve=True, now=now
    )
    assert subscription is not None
    assert subscription.ends_at == now + timedelta(days=365)
    assert payment.amount_dzd == 80000


def test_rejecting_payment_cancels_the_pending_subscription(seeded) -> None:
    admin = make_user(seeded, phone="0555300106", role=UserRole.ADMIN)
    user = make_user(seeded, phone="0555300107")
    payment = _pending_payment(seeded, user)

    subscription = billing.verify_payment(
        seeded, payment, admin=admin, approve=False, notes="مرجع خاطئ"
    )
    assert payment.status == PaymentStatus.REJECTED
    assert (
        subscription is not None and subscription.status == SubscriptionStatus.CANCELLED
    )
    assert subscription.starts_at is None

    with pytest.raises(billing.BillingError, match="عولج مسبقاً"):
        billing.verify_payment(seeded, payment, admin=admin, approve=True)


def test_expire_subscriptions_is_idempotent(seeded) -> None:
    user = make_user(seeded, phone="0555300108")
    ended = subscribe(seeded, user, ends_days=-1)
    current = subscribe(seeded, user, plan_code="silver", ends_days=10)

    assert billing.expire_subscriptions(seeded) == 1
    assert billing.expire_subscriptions(seeded) == 0
    seeded.refresh(ended)
    seeded.refresh(current)
    assert ended.status == SubscriptionStatus.EXPIRED
    assert current.status == SubscriptionStatus.ACTIVE


def test_run_maintenance_reminds_once(seeded) -> None:
    user = make_user(seeded, phone="0555300109")
    user.email = "rappels@example.dz"
    seeded.commit()
    subscription = subscribe(seeded, user, ends_days=3)
    sent: list[Subscription] = []

    first = billing.run_maintenance(seeded, days=7, send=sent.append)
    second = billing.run_maintenance(seeded, days=7, send=sent.append)

    assert first.reminders_sent == 1
    assert second.reminders_sent == 0
    assert len(sent) == 1
    seeded.refresh(subscription)
    assert subscription.reminder_sent_at is not None


def test_run_maintenance_skips_subscriptions_outside_the_window(seeded) -> None:
    user = make_user(seeded, phone="0555300110")
    user.email = "loin@example.dz"
    seeded.commit()
    subscribe(seeded, user, ends_days=20)
    summary = billing.run_maintenance(seeded, days=7, send=lambda subscription: None)
    assert summary.reminders_sent == 0


def test_run_maintenance_retries_after_a_transport_failure(seeded) -> None:
    user = make_user(seeded, phone="0555300111")
    user.email = "echec@example.dz"
    seeded.commit()
    subscription = subscribe(seeded, user, ends_days=2)

    def boom(_subscription):
        raise RuntimeError("smtp down")

    failed = billing.run_maintenance(seeded, days=7, send=boom)
    assert failed.reminders_failed == 1
    assert failed.reminders_sent == 0
    seeded.refresh(subscription)
    assert subscription.reminder_sent_at is None

    retried = billing.run_maintenance(seeded, days=7, send=lambda subscription: None)
    assert retried.reminders_sent == 1


# ---------------------------------------------------------------------------
# Access rules after activation and after expiry
# ---------------------------------------------------------------------------
def test_activated_subscription_unlocks_covered_sector(seeded) -> None:
    user = make_user(seeded, phone="0555300200")
    subscribe(seeded, user, plan_code="gold", sector_slugs=("water",))

    entitlements = resolve_entitlements(seeded, user)
    assert entitlements.is_paid
    view = build_announcement_view(entitlements, water_announcement(seeded))
    assert view.unlocked
    assert view.issuer_name is not None


def test_expired_subscription_falls_back_to_free_plan(seeded) -> None:
    user = make_user(seeded, phone="0555300201")
    subscription = subscribe(seeded, user, ends_days=-1)

    entitlements = resolve_entitlements(seeded, user)
    assert not entitlements.is_paid
    view = build_announcement_view(entitlements, water_announcement(seeded))
    assert not view.unlocked
    assert view.reason_message

    billing.run_maintenance(seeded, send=lambda subscription: None)
    seeded.refresh(subscription)
    assert subscription.status == SubscriptionStatus.EXPIRED


# ---------------------------------------------------------------------------
# HTTP flow: checkout → proof → staff verification
# ---------------------------------------------------------------------------
def _sign_in(db, client, phone: str, **kwargs) -> User:
    user = make_user(db, phone=phone, **kwargs)
    response = login(client, phone)
    assert response.status_code == 303, response.text
    return user


def test_checkout_creates_payment_and_redirects(client, db, seeded) -> None:
    _sign_in(db, client, "0555300300")
    token = csrf(client)

    response = client.post(
        "/abonnement",
        data={
            "csrf_token": token,
            "plan": "gold",
            "period": "monthly",
            "sectors": [sector_id(db, "water")],
            "method": "cash",
            "reference": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/paiement/")

    payment = db.scalar(select(Payment).order_by(Payment.id.desc()))
    assert payment is not None
    assert payment.amount_dzd == 8000
    assert payment.method == PaymentMethod.CASH
    assert payment.status == PaymentStatus.PENDING


def test_checkout_rejects_an_unknown_method(client, db, seeded) -> None:
    _sign_in(db, client, "0555300301")
    response = client.post(
        "/abonnement",
        data={
            "csrf_token": csrf(client),
            "plan": "gold",
            "period": "monthly",
            "method": "bitcoin",
        },
        follow_redirects=True,
    )
    assert response.status_code == 400


def test_checkout_reports_missing_transfer_reference(client, db, seeded) -> None:
    _sign_in(db, client, "0555300302")
    response = client.post(
        "/abonnement",
        data={
            "csrf_token": csrf(client),
            "plan": "gold",
            "period": "monthly",
            "sectors": [sector_id(db, "water")],
            "method": "bank_transfer",
            "reference": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/abonnement?plan=gold&error=" in response.headers["location"]
    assert db.scalar(select(Payment)) is None


def test_proof_upload_rejects_a_non_pdf(client, db, seeded) -> None:
    _sign_in(db, client, "0555300303")
    client.post(
        "/abonnement",
        data={
            "csrf_token": csrf(client),
            "plan": "gold",
            "period": "monthly",
            "sectors": [sector_id(db, "water")],
            "method": "cash",
        },
        follow_redirects=False,
    )
    payment = db.scalar(select(Payment).order_by(Payment.id.desc()))

    response = client.post(
        f"/paiement/{payment.id}/preuve",
        data={"csrf_token": client.cookies.get("dz_csrf")},
        files={"proof": ("proof.pdf", b"MZ malware", "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    db.refresh(payment)
    assert payment.proof_filename is None


def test_proof_upload_stores_a_pdf(client, db, seeded) -> None:
    _sign_in(db, client, "0555300304")
    client.post(
        "/abonnement",
        data={
            "csrf_token": csrf(client),
            "plan": "gold",
            "period": "monthly",
            "sectors": [sector_id(db, "water")],
            "method": "cash",
        },
        follow_redirects=False,
    )
    payment = db.scalar(select(Payment).order_by(Payment.id.desc()))

    response = client.post(
        f"/paiement/{payment.id}/preuve",
        data={"csrf_token": client.cookies.get("dz_csrf")},
        files={"proof": ("وصل.pdf", PDF, "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("uploaded=1")

    db.refresh(payment)
    assert payment.proof_filename and payment.proof_filename.startswith("payments/")
    assert payment.proof_content_type == "application/pdf"
    assert payment.proof_size_bytes == len(PDF)
    assert payment.proof_original_name == "وصل.pdf"

    served = client.get(f"/paiement/{payment.id}/preuve")
    assert served.status_code == 200
    assert served.content == PDF


def test_proof_is_private_to_its_owner(client, db, seeded) -> None:
    _sign_in(db, client, "0555300305")
    client.post(
        "/abonnement",
        data={
            "csrf_token": csrf(client),
            "plan": "gold",
            "period": "monthly",
            "sectors": [sector_id(db, "water")],
            "method": "cash",
        },
        follow_redirects=False,
    )
    payment = db.scalar(select(Payment).order_by(Payment.id.desc()))
    client.post(
        f"/paiement/{payment.id}/preuve",
        data={"csrf_token": client.cookies.get("dz_csrf")},
        files={"proof": ("proof.pdf", PDF, "application/pdf")},
        follow_redirects=False,
    )

    client.cookies.clear()
    _sign_in(db, client, "0555300306")
    assert client.get(f"/paiement/{payment.id}/preuve").status_code == 404

    client.cookies.clear()
    make_user(db, phone="0555300307", role=UserRole.SUPPORT)
    login(client, "0555300307")
    assert client.get(f"/paiement/{payment.id}/preuve").status_code == 200


def test_staff_queue_is_forbidden_to_subscribers(client, db, seeded) -> None:
    _sign_in(db, client, "0555300308")
    assert client.get("/admin/paiements").status_code == 403
    response = client.post(
        "/admin/paiements/1/verifier",
        data={"csrf_token": csrf(client), "decision": "approve"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_end_to_end_checkout_verification_unlocks_details(client, db, seeded) -> None:
    user = _sign_in(db, client, "0555300309")
    client.post(
        "/abonnement",
        data={
            "csrf_token": csrf(client),
            "plan": "gold",
            "period": "monthly",
            "sectors": [sector_id(db, "water")],
            "method": "cash",
        },
        follow_redirects=False,
    )
    payment = db.scalar(select(Payment).order_by(Payment.id.desc()))
    client.post(
        f"/paiement/{payment.id}/preuve",
        data={"csrf_token": client.cookies.get("dz_csrf")},
        files={"proof": ("proof.pdf", PDF, "application/pdf")},
        follow_redirects=False,
    )

    # Staff reviews the queue.
    client.cookies.clear()
    admin = make_user(db, phone="0555300310", role=UserRole.ADMIN)
    login(client, "0555300310")
    queue = client.get("/admin/paiements")
    assert queue.status_code == 200
    assert user.company_name in queue.text

    verified = client.post(
        f"/admin/paiements/{payment.id}/verifier",
        data={"csrf_token": client.cookies.get("dz_csrf"), "decision": "approve"},
        follow_redirects=False,
    )
    assert verified.status_code == 303
    assert verified.headers["location"].startswith("/admin/paiements?notice=")

    db.expire_all()
    payment = db.get(Payment, payment.id)
    assert payment is not None and payment.status == PaymentStatus.VERIFIED
    assert payment.verified_by_id == admin.id
    subscription = db.get(Subscription, payment.subscription_id)
    assert subscription is not None and subscription.status == SubscriptionStatus.ACTIVE

    # Back as the subscriber, the detail page is unlocked.
    client.cookies.clear()
    login(client, "0555300309")
    announcement = water_announcement(db)
    detail = client.get(f"/annonces/{announcement.id}", follow_redirects=True)
    assert detail.status_code == 200
    assert announcement.title_ar in detail.text
    assert "الجزائرية للمياه" in detail.text

    dashboard = client.get("/tableau-de-bord")
    assert dashboard.status_code == 200
    assert "ذهبي" in dashboard.text
