"""PostgreSQL search: tsvector prefix matching (+ pg_trgm when available).

The suite runs against a throw-away PostgreSQL cluster. It is skipped when the
``pgserver`` wheel or the ``psycopg`` driver are not installed; CI runs the same
tests against a ``postgres:16`` service container (which ships ``pg_trgm``).
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import func, select, text

from webapp.db import make_engine, make_session_factory, session_scope
from webapp.enums import AnnouncementStatus, AnnouncementType
from webapp.models import Announcement, Issuer, Sector, Wilaya
from webapp.search import AnnouncementFilters, search_announcements
from webapp.search_index import index_announcement
from webapp.seed import seed_all
from webapp.text import slugify
from webapp.timeutils import today_algiers


@pytest.fixture(scope="module")
def postgres_url(tmp_path_factory):
    """Use ``TEST_POSTGRES_URL`` when provided, else a temporary pgserver cluster."""
    configured = os.getenv("TEST_POSTGRES_URL", "").strip()
    if configured:
        yield configured
        return

    pgserver = pytest.importorskip("pgserver")
    pytest.importorskip("psycopg")
    directory = tmp_path_factory.mktemp("postgres")
    server = pgserver.get_server(str(directory))
    url = server.get_uri().replace("postgresql://", "postgresql+psycopg://")
    try:
        yield url
    finally:
        server.cleanup()


@pytest.fixture(scope="module")
def pg_engine(postgres_url):
    """Migrate the throw-away database with the real Alembic chain."""
    config = AlembicConfig("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(config, "head")
    engine = make_engine(postgres_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_factory(pg_engine):
    """Seed reference data and demo announcements once."""
    factory = make_session_factory(pg_engine)
    with session_scope(factory) as db:
        seed_all(db, with_demo=True)
    return factory


@pytest.fixture
def pg(pg_factory):
    """A fresh session per test."""
    session = pg_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _add(
    db, *, title, description="", type=AnnouncementType.TENDER, sectors=("water",)
):
    wilaya = db.scalar(select(Wilaya).where(Wilaya.code == "25"))
    issuer = db.scalar(select(Issuer).where(Issuer.slug == "ade"))
    announcement = Announcement(
        ref=f"PG-{slugify(title)[:20]}-{db.scalar(select(func.count(Announcement.id)))}",
        slug=slugify(title, fallback="pg-test"),
        type=type,
        status=AnnouncementStatus.PUBLISHED,
        title_ar=title,
        description_ar=description,
        issuer_id=issuer.id,
        issuer_name=issuer.name_ar,
        wilaya_id=wilaya.id,
        publish_date=today_algiers() - timedelta(days=1),
        publish_year=today_algiers().year,
        is_sample=False,
        source_key="pg-test",
        external_id=title[:20],
    )
    announcement.sectors = [
        sector
        for slug in sectors
        if (sector := db.scalar(select(Sector).where(Sector.slug == slug)))
    ]
    db.add(announcement)
    db.flush()
    index_announcement(db, announcement)
    db.commit()
    return announcement


def _search(db, **kwargs):
    return search_announcements(
        db, AnnouncementFilters(**kwargs), per_page=kwargs.pop("per_page", 48)
    )


def test_schema_created_by_migrations(pg_engine) -> None:
    with pg_engine.connect() as conn:
        tables = set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname LIKE 'ix_announcements_search%'"
                )
            ).scalars()
        )
    assert {"announcements", "users", "payments", "contact_messages"} <= tables
    assert "ix_announcements_search_tsv" in indexes
    assert "announcement_fts" not in tables


def test_strategy_is_postgres(pg) -> None:
    result = _search(pg, q="انابيب")
    assert result.strategy == "postgres"
    assert result.used_fts is True
    assert result.total >= 1


def test_hamza_variants_match(pg) -> None:
    assert _search(pg, q="انابيب").total >= 1
    assert _search(pg, q="أنابيب").total >= 1


def test_ta_marbuta_variant(pg) -> None:
    _add(pg, title="إدارة المشاريع المائية", description="دراسة إدارة")
    assert any("إدارة" in item.title_ar for item in _search(pg, q="اداره").items)


def test_prefix_match(pg) -> None:
    result = _search(pg, q="خزان")
    assert result.total >= 1
    assert all("خزان" in item.title_ar for item in result.items)


def test_definite_article_variants(pg) -> None:
    _add(pg, title="صيانة شبكة المياه الصالحة للشرب", description="شبكة توزيع")
    assert _search(pg, q="مياه").total >= 1
    _add(pg, title="توريد مضخات", description="لمشروع مياه الشرب")
    assert _search(pg, q="المضخات").total >= 1


def test_type_and_wilaya_filters(pg) -> None:
    auctions = _search(pg, type=AnnouncementType.AUCTION)
    assert auctions.total >= 1
    assert all(item.type == AnnouncementType.AUCTION for item in auctions.items)

    oran = _search(pg, wilaya_code="31")
    assert oran.total >= 1
    assert all(item.wilaya.code == "31" for item in oran.items)


def test_pagination_and_drafts(pg) -> None:
    page = search_announcements(pg, AnnouncementFilters(page=2), per_page=5)
    assert page.page == 2
    assert page.total >= 6
    assert len(page.items) <= 5

    draft = _add(pg, title="مسودة سرية")
    draft.status = AnnouncementStatus.DRAFT
    pg.commit()
    assert _search(pg, q="مسودة سرية").total == 0


def test_similarity_extension_optional(pg) -> None:
    """With pg_trgm the fuzzy branch widens recall; otherwise skip."""
    available = bool(
        pg.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
    )
    if not available:
        pytest.skip("pg_trgm is not installed in this PostgreSQL build")
    _add(pg, title="اقتناء أنابيب بلاستيكية", description="توريد")
    result = _search(pg, q="انبيب")  # one-letter typo
    assert result.total >= 1


def test_count_matches_search(pg) -> None:
    result = _search(pg, q="مناقصة")
    count = pg.scalar(
        select(func.count(func.distinct(Announcement.id)))
        .select_from(Announcement)
        .where(
            Announcement.status.in_(
                (AnnouncementStatus.PUBLISHED, AnnouncementStatus.ARCHIVED)
            )
        )
    )
    assert 0 < result.total <= count
