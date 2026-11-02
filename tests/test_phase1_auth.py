"""Password, session, CSRF and rate-limit behaviour."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.conftest import TEST_PASSWORD, login, make_user, subscribe
from webapp.config import Settings
from webapp.models import User, UserSession
from webapp.security import (
    RateLimiter,
    create_session,
    delete_session,
    find_session,
    hash_password,
    needs_rehash,
    normalize_phone,
    token_hash,
    validate_password,
    verify_password,
)
from webapp.timeutils import utcnow


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0555123456", "+213555123456"),
        ("555123456", "+213555123456"),
        ("+213555123456", "+213555123456"),
        ("00213555123456", "+213555123456"),
        ("0555 12 34 56", "+213555123456"),
        ("031234567", "+21331234567"),
    ],
)
def test_normalize_phone_accepts_algerian_formats(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "123", "05551234567", "0000000000", "0555-12-34", "abc", "055512345"],
)
def test_normalize_phone_rejects_invalid(raw: str) -> None:
    assert normalize_phone(raw) is None


def test_password_hashing_and_validation() -> None:
    hashed = hash_password(TEST_PASSWORD)
    assert hashed.startswith("$argon2id$")
    assert verify_password(TEST_PASSWORD, hashed)
    assert not verify_password("wrong-password", hashed)
    assert not verify_password("anything", None)
    assert not needs_rehash(hashed)
    assert validate_password("short") is not None
    assert validate_password(" validPass1 ") is not None
    assert validate_password("validPass1") is None


def test_session_lifecycle_and_expiry(db) -> None:
    user = make_user(db, phone="0555111222")
    raw = create_session(db, user, ttl_hours=1)
    row = find_session(db, raw)
    assert row is not None
    assert row.token_hash == token_hash(raw)

    future = utcnow() + timedelta(hours=2)
    assert find_session(db, raw, now=future) is None
    assert (
        db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw)))
        is None
    )


def test_delete_session_revokes(db) -> None:
    user = make_user(db, phone="0555111223")
    raw = create_session(db, user, ttl_hours=1)
    delete_session(db, raw)
    assert find_session(db, raw) is None


def test_rate_limiter_fixed_window(db) -> None:
    limiter = RateLimiter(db)
    allowed = [
        limiter.hit("login_phone", "0555", limit=3, window_minutes=15) for _ in range(3)
    ]
    assert allowed == [True, True, True]
    assert limiter.hit("login_phone", "0555", limit=3, window_minutes=15) is False
    limiter.clear("login_phone", "0555")
    assert limiter.hit("login_phone", "0555", limit=3, window_minutes=15) is True


def test_safe_next_url_rejects_external_targets() -> None:
    from webapp.web.deps import safe_next_url

    assert safe_next_url("/annonces") == "/annonces"
    assert safe_next_url("//evil.example") == "/"
    assert safe_next_url("https://evil.example") == "/"
    assert safe_next_url("") == "/"
    assert safe_next_url(None) == "/"


def test_login_without_csrf_is_rejected(client, seeded) -> None:
    make_user(seeded, phone="0555111224")
    response = client.post(
        "/connexion",
        data={"phone": "0555111224", "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "dz_session" not in client.cookies


def test_login_with_csrf_succeeds(client, seeded) -> None:
    make_user(seeded, phone="0555111225")
    response = login(client, "0555111225")
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert client.cookies.get("dz_session")
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie
    assert "SameSite=lax" in set_cookie or "samesite=lax" in set_cookie

    reloaded = seeded.scalar(select(User).where(User.phone == "+213555111225"))
    assert reloaded.last_login_at is not None


def test_login_wrong_password_is_generic(client, seeded) -> None:
    make_user(seeded, phone="0555111226")
    response = login(client, "0555111226", password="WrongPass!2026")
    assert response.status_code == 200
    assert "رقم الهاتف أو كلمة المرور غير صحيحة" in response.text


def test_login_unknown_phone_is_generic(client, seeded) -> None:
    response = login(client, "0555999888", password="WrongPass!2026")
    assert response.status_code == 200
    assert "رقم الهاتف أو كلمة المرور غير صحيحة" in response.text


def test_login_rejects_cross_origin_post(client, seeded) -> None:
    make_user(seeded, phone="0555111227")
    client.get("/connexion")
    csrf = client.cookies.get("dz_csrf")
    response = client.post(
        "/connexion",
        data={"phone": "0555111227", "password": TEST_PASSWORD, "csrf_token": csrf},
        headers={"Origin": "https://evil.example"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_login_rate_limit(client, seeded) -> None:
    make_user(seeded, phone="0555111228")
    client.get("/connexion")
    csrf = client.cookies.get("dz_csrf")
    statuses = []
    for _ in range(6):
        response = client.post(
            "/connexion",
            data={
                "phone": "0555111228",
                "password": "WrongPass!2026",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        statuses.append(response.status_code)
    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429


def test_logout_revokes_access(client, seeded) -> None:
    user = make_user(seeded, phone="0555111229")
    subscribe(seeded, user, plan_code="gold", sector_slugs=("water",))
    assert login(client, "0555111229").status_code == 303

    detail = client.get("/annonces/1")
    assert detail.status_code == 200
    session_token = client.cookies.get("dz_session")
    assert session_token

    csrf = client.cookies.get("dz_csrf")
    response = client.post(
        "/deconnexion", data={"csrf_token": csrf}, follow_redirects=False
    )
    assert response.status_code == 303
    assert client.cookies.get("dz_session") is None
    assert "التفاصيل الكاملة للمشتركين" in client.get("/annonces/1").text


def test_open_redirect_is_blocked(client, seeded) -> None:
    make_user(seeded, phone="0555111230")
    client.get("/connexion")
    csrf = client.cookies.get("dz_csrf")
    response = client.post(
        "/connexion",
        data={
            "phone": "0555111230",
            "password": TEST_PASSWORD,
            "csrf_token": csrf,
            "next": "//evil.example/steal",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_production_settings_force_secure_cookies() -> None:
    assert Settings(app_env="production").secure_cookies is True
    assert Settings(app_env="development").secure_cookies is False
