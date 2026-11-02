"""Registration, phone OTP, email verification and password reset."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from webapp.models import OneTimeToken, User, UserSession
from webapp.security import verify_password
from webapp.timeutils import utcnow

PHONE = "0555777001"
EMAIL = "compte@example.dz"
PASSWORD = "StrongPass!2026"
OTP_RE = re.compile(r"\b(\d{6})\b")


def csrf(client) -> str:
    client.get("/inscription")
    return client.cookies.get("dz_csrf")


def sector_ids(db, *slugs: str) -> list[int]:
    from webapp.models import Sector

    return [db.scalar(select(Sector.id).where(Sector.slug == slug)) for slug in slugs]


def register(
    client,
    db,
    *,
    phone: str = PHONE,
    email: str = EMAIL,
    password: str = PASSWORD,
    sectors: tuple[str, ...] = ("water",),
):
    token = csrf(client)
    data = {
        "csrf_token": token,
        "company": "مؤسسة النور للأشغال",
        "phone": phone,
        "email": email,
        "password": password,
        "password_confirm": password,
        "terms": "on",
        "sectors": sector_ids(db, *sectors),
    }
    return client.post("/inscription", data=data, follow_redirects=False)


def last_otp(app) -> str:
    text = app.state.sms_provider.outbox[-1].text
    match = OTP_RE.search(text)
    assert match, f"no OTP in {text!r}"
    return match.group(1)


def verify(client, app, code: str | None = None):
    code = code or last_otp(app)
    return client.post(
        "/inscription/verifier",
        data={"csrf_token": client.cookies.get("dz_csrf"), "code": code},
        follow_redirects=False,
    )


def register_and_verify(client, app, db, **kwargs):
    response = register(client, db, **kwargs)
    assert response.status_code == 303, response.text
    response = verify(client, app)
    assert response.status_code == 303, response.text
    return db.scalar(select(User).where(User.phone == "+213" + PHONE[1:]))


def test_registration_form_renders(client, seeded) -> None:
    response = client.get("/inscription")
    assert response.status_code == 200
    assert "إنشاء حساب" in response.text
    assert "اسم المؤسسة" in response.text
    assert "القطاعات التي تهمكم" in response.text


def test_registration_creates_inactive_user(client, app, db, seeded) -> None:
    response = register(client, db)
    assert response.status_code == 303
    assert response.headers["location"] == "/inscription/verifier"

    user = db.scalar(select(User).where(User.phone == "+213555777001"))
    assert user is not None
    assert user.is_active is False
    assert user.phone_verified_at is None
    assert user.email == EMAIL
    assert [sector.slug for sector in user.sectors] == ["water"]
    assert verify_password(PASSWORD, user.password_hash)
    assert len(app.state.sms_provider.outbox) == 1
    assert app.state.sms_provider.outbox[0].phone == "+213555777001"


def test_otp_verifies_phone_and_sends_email(client, app, db, seeded) -> None:
    response = register(client, db)
    assert response.status_code == 303

    verified = verify(client, app)
    assert verified.status_code == 303
    assert verified.headers["location"] == "/tableau-de-bord"
    assert client.cookies.get("dz_session")

    user = db.scalar(select(User).where(User.phone == "+213555777001"))
    assert user.is_active is True
    assert user.phone_verified_at is not None
    assert app.state.email_provider.outbox
    message = app.state.email_provider.outbox[-1]
    assert message.kind == "verify_email"
    assert "/verifier-email?token=" in message.body


def test_email_verification_link(client, app, seeded) -> None:
    register(client, seeded)
    verify(client, app)
    body = app.state.email_provider.outbox[-1].body
    token = body.split("token=")[1].split()[0]

    response = client.get(f"/verifier-email?token={token}")
    assert response.status_code == 200
    assert "تم تأكيد البريد الإلكتروني" in response.text

    user = seeded.scalar(select(User).where(User.phone == "+213555777001"))
    assert user.email_verified_at is not None

    again = client.get(f"/verifier-email?token={token}")
    assert "استُعمل هذا الرابط" in again.text


def test_wrong_otp_counts_attempts(client, app, db, seeded) -> None:
    register(client, db)
    for attempt in range(1, 4):
        response = verify(client, app, code="000000")
        assert response.status_code == 400
        db.expire_all()
        token = db.scalar(
            select(OneTimeToken).where(OneTimeToken.purpose == "phone_otp")
        )
        assert token.attempts == attempt


def test_otp_locked_after_max_attempts(client, app, db, seeded) -> None:
    register(client, db)
    for _ in range(5):
        verify(client, app, code="000000")
    response = verify(client, app, code=last_otp(app))
    assert response.status_code == 400
    assert "تجاوزت عدد المحاولات" in response.text


def test_expired_otp_is_rejected(client, app, db, seeded) -> None:
    register(client, db)
    token = db.scalar(select(OneTimeToken).where(OneTimeToken.purpose == "phone_otp"))
    token.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()

    response = verify(client, app, code=last_otp(app))
    assert response.status_code == 400
    assert "انتهت صلاحية الرمز" in response.text


def test_resend_cooldown(client, app, db, seeded) -> None:
    register(client, db)
    response = client.post(
        "/inscription/renvoyer", data={"csrf_token": client.cookies.get("dz_csrf")}
    )
    assert response.status_code == 200
    assert "انتظر" in response.text
    assert len(app.state.sms_provider.outbox) == 1


def test_duplicate_phone_is_rejected(client, db, seeded) -> None:
    register(client, db)
    response = register(client, db, email="other@example.dz")
    assert response.status_code == 400
    assert "رقم الهاتف مستعمل" in response.text


def test_duplicate_email_is_rejected(client, db, seeded) -> None:
    register(client, db)
    response = register(client, db, phone="0555777002")
    assert response.status_code == 400
    assert "البريد الإلكتروني مستعمل" in response.text


@pytest.mark.parametrize(
    "override,expected",
    [
        ({"password": "weak", "password_confirm": "weak"}, "8 أحرف"),
        ({"password": PASSWORD, "password_confirm": "AnotherPass!1"}, "غير متطابقتين"),
        ({"email": "not-an-email"}, "البريد الإلكتروني غير صالح"),
        ({"company": "أ"}, "اسم المؤسسة"),
    ],
)
def test_registration_validation(client, db, seeded, override, expected) -> None:
    token = csrf(client)
    data = {
        "csrf_token": token,
        "company": "مؤسسة الاختبار",
        "phone": "0555777003",
        "email": "valid@example.dz",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
        "terms": "on",
        "sectors": sector_ids(db, "water"),
    }
    data.update(override)
    response = client.post("/inscription", data=data)
    assert response.status_code == 400
    assert expected in response.text


def test_registration_requires_terms(client, db, seeded) -> None:
    token = csrf(client)
    response = client.post(
        "/inscription",
        data={
            "csrf_token": token,
            "company": "مؤسسة الاختبار",
            "phone": "0555777004",
            "email": "terms@example.dz",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "sectors": sector_ids(db, "water"),
        },
    )
    assert response.status_code == 400
    assert "شروط الاستخدام" in response.text


def test_inactive_login_resumes_verification(client, db, seeded) -> None:
    register(client, db)
    response = client.post(
        "/connexion",
        data={
            "csrf_token": client.cookies.get("dz_csrf"),
            "phone": PHONE,
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/inscription/verifier"


def test_password_reset_flow(client, app, db, seeded) -> None:
    user = register_and_verify(client, app, db)
    assert db.scalar(select(UserSession).where(UserSession.user_id == user.id))

    # Ask for a reset code while still logged in on the device.
    reset_request = client.post(
        "/mot-de-passe-oublie",
        data={"csrf_token": csrf(client), "phone": PHONE},
        follow_redirects=False,
    )
    assert reset_request.status_code == 303
    assert reset_request.headers["location"] == "/reinitialiser"
    code = last_otp(app)

    new_password = "AnotherPass!2027"
    response = client.post(
        "/reinitialiser",
        data={
            "csrf_token": client.cookies.get("dz_csrf"),
            "code": code,
            "password": new_password,
            "password_confirm": new_password,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/connexion?reset=1"

    db.expire_all()
    user = db.scalar(select(User).where(User.phone == "+213555777001"))
    db.refresh(user)
    assert verify_password(new_password, user.password_hash)
    assert db.scalar(select(UserSession).where(UserSession.user_id == user.id)) is None

    # The old browser session no longer authenticates.
    dashboard = client.get("/tableau-de-bord", follow_redirects=False)
    assert dashboard.status_code == 303
    assert dashboard.headers["location"].startswith("/connexion?next=")


def test_password_reset_unknown_phone_does_not_leak(client, db, seeded) -> None:
    token = csrf(client)
    response = client.post(
        "/mot-de-passe-oublie",
        data={"csrf_token": token, "phone": "0555999888"},
    )
    assert response.status_code == 200
    assert "إن كان الرقم مسجلاً" in response.text


def test_dashboard_requires_login(client, seeded) -> None:
    response = client.get("/tableau-de-bord", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/connexion?next=")


def test_dashboard_renders_for_subscriber(client, app, db, seeded) -> None:
    register_and_verify(client, app, db)
    response = client.get("/tableau-de-bord")
    assert response.status_code == 200
    assert "لوحة التحكم" in response.text
    assert "القطاعات المفضلة" in response.text
    assert "تنبيهات الجديد" in response.text
    assert "سجل المدفوعات" in response.text


def test_alert_can_be_updated_and_unsubscribed(client, app, db, seeded) -> None:
    register_and_verify(client, app, db)
    response = client.post(
        "/tableau-de-bord/alertes",
        data={
            "csrf_token": client.cookies.get("dz_csrf"),
            "frequency": "weekly",
            "sectors": sector_ids(db, "water", "health"),
            "wilayas": [],
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    from webapp.models import Alert

    alert = db.scalar(select(Alert))
    assert alert.frequency == "weekly"
    assert {sector.slug for sector in alert.sectors} == {"water", "health"}

    unsubscribe = client.get(f"/desabonnement?token={alert.unsubscribe_token}")
    assert unsubscribe.status_code == 200
    assert "أُلغي تنبيهك" in unsubscribe.text
    db.refresh(alert)
    assert alert.is_active is False


def test_interests_can_be_replaced(client, app, db, seeded) -> None:
    register_and_verify(client, app, db)
    response = client.post(
        "/tableau-de-bord/secteurs",
        data={
            "csrf_token": client.cookies.get("dz_csrf"),
            "sectors": sector_ids(db, "health"),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    user = db.scalar(select(User).where(User.phone == "+213555777001"))
    db.refresh(user)
    assert [sector.slug for sector in user.sectors] == ["health"]
