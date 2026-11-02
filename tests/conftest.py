"""Shared fixtures for the Phase 1 platform tests.

Legacy tests do not use these fixtures; they only import the project modules.
Every fixture writes to a temporary SQLite file, never to ``storage/``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.config import Settings
from webapp.db import Base, ensure_fts, make_engine, make_session_factory
from webapp.enums import BillingPeriod, SubscriptionStatus, UserRole
from webapp.models import Plan as PlanModel
from webapp.models import Sector, Subscription, User
from webapp.security import hash_password, normalize_phone
from webapp.seed import seed_all
from webapp.timeutils import utcnow
from webapp.web.main import create_app

TEST_PASSWORD = "TestPass!2026"
ADMIN_PASSWORD = "AdminPass!2026"


@pytest.fixture
def database_url(tmp_path) -> str:
    """SQLAlchemy URL of a fresh database file."""
    return f"sqlite+pysqlite:///{tmp_path / 'platform.db'}"


@pytest.fixture
def engine(database_url):
    """Engine with the product schema and FTS5 table created."""
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    ensure_fts(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    """Session factory bound to the test engine."""
    return make_session_factory(engine)


@pytest.fixture
def db(session_factory) -> Iterator[Session]:
    """A session for test setup and assertions."""
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def seeded(db: Session) -> Session:
    """Reference taxonomy + 24 sample announcements + 5 offers."""
    seed_all(db, with_demo=True)
    return db


@pytest.fixture
def settings(database_url, tmp_path) -> Settings:
    """App settings bound to the temporary database and upload directory."""
    return Settings(
        app_env="test",
        upload_dir=str(tmp_path / "uploads"),
        email_backend="console",
        sms_backend="console",
        database_url=database_url,
        base_url="http://testserver",
        cookie_secure=False,
        page_size=12,
        session_ttl_hours=8,
        login_rate_limit=5,
        ip_rate_limit=10,
        rate_limit_window_minutes=15,
        contact_email="contact@example.dz",
        contact_phone="+213 555 00 00 00",
    )


@pytest.fixture
def app(settings):
    """FastAPI app under test."""
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    """HTTP client that surfaces server exceptions in tests."""
    with TestClient(app) as test_client:
        yield test_client


def make_user(
    db: Session,
    *,
    phone: str = "0555123456",
    password: str = TEST_PASSWORD,
    role: UserRole = UserRole.USER,
    company_name: str = "مؤسسة الاختبار",
) -> User:
    """Create a user directly (bypasses the Phase 2 registration UI)."""
    normalized = normalize_phone(phone)
    assert normalized is not None, f"invalid test phone: {phone}"
    existing = db.scalar(select(User).where(User.phone == normalized))
    if existing is not None:
        return existing
    user = User(
        phone=normalized,
        company_name=company_name,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def subscribe(
    db: Session,
    user: User,
    *,
    plan_code: str = "gold",
    sector_slugs: tuple[str, ...] = ("water",),
    starts_days: int = -1,
    ends_days: int = 30,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
) -> Subscription:
    """Attach an active subscription to ``user``."""
    plan = db.scalar(select(PlanModel).where(PlanModel.code == plan_code))
    assert plan is not None, f"unknown plan: {plan_code}"
    sectors = [
        db.scalar(select(Sector).where(Sector.slug == slug)) for slug in sector_slugs
    ]
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=status,
        billing_period=BillingPeriod.MONTHLY,
        starts_at=utcnow() + timedelta(days=starts_days),
        ends_at=utcnow() + timedelta(days=ends_days),
        sectors=[sector for sector in sectors if sector is not None],
    )
    db.add(subscription)
    db.commit()
    return subscription


def login(client: TestClient, phone: str, password: str = TEST_PASSWORD):
    """Log in through the real form (CSRF cookie + hidden token)."""
    client.get("/connexion")
    csrf = client.cookies.get("dz_csrf")
    return client.post(
        "/connexion",
        data={"phone": phone, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )


@pytest.fixture
def login_user(client):
    """Fixture wrapper around :func:`login`."""

    def _login(phone: str, password: str = TEST_PASSWORD):
        return login(client, phone, password)

    return _login


__all__ = ["ADMIN_PASSWORD", "TEST_PASSWORD", "login", "make_user", "subscribe"]
