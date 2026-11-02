"""CLI commands, Alembic migrations and index rebuilding."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import func, select, text

from tests.conftest import ADMIN_PASSWORD, TEST_PASSWORD
from webapp.cli import build_parser, main, upgrade_database
from webapp.config import Settings
from webapp.db import ensure_fts, make_engine, make_session_factory, session_scope
from webapp.models import Announcement, User
from webapp.search_index import rebuild_index
from webapp.security import verify_password


def _sqlite_tables(path: str) -> set[str]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


def _settings_for(tmp_path, monkeypatch, name: str = "cli") -> tuple[Settings, str]:
    db_file = tmp_path / f"{name}.db"
    url = f"sqlite+pysqlite:///{db_file}"
    monkeypatch.setenv("APP_DATABASE_URL", url)
    return Settings.from_env(), str(db_file)


def test_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_init_db_migrates_and_seeds(tmp_path, monkeypatch, capsys) -> None:
    settings, db_file = _settings_for(tmp_path, monkeypatch)
    assert main(["init-db", "--demo"]) == 0
    output = capsys.readouterr().out
    assert "Database ready" in output
    assert "'wilayas': 69" in output
    assert "'announcements': 24" in output

    tables = _sqlite_tables(db_file)
    assert {"announcements", "subscriptions", "payments", "alembic_version"} <= tables
    assert "announcement_fts" in tables

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as db:
        assert db.scalar(select(func.count(Announcement.id))) == 24
    engine.dispose()


def test_init_db_is_idempotent(tmp_path, monkeypatch, capsys) -> None:
    _settings_for(tmp_path, monkeypatch)
    assert main(["init-db", "--demo"]) == 0
    capsys.readouterr()
    assert main(["init-db", "--demo"]) == 0
    output = capsys.readouterr().out
    assert "'announcements': 0" in output
    assert "'offers': 0" in output


def test_seed_without_demo_keeps_content_empty(tmp_path, monkeypatch, capsys) -> None:
    settings, _db_file = _settings_for(tmp_path, monkeypatch)
    upgrade_database(settings)
    assert main(["seed"]) == 0
    _ = capsys.readouterr().out

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as db:
        assert db.scalar(select(func.count(Announcement.id))) == 0
    engine.dispose()


def test_create_user_and_reject_duplicates(tmp_path, monkeypatch, capsys) -> None:
    settings, _db_file = _settings_for(tmp_path, monkeypatch)
    upgrade_database(settings)

    code = main(
        [
            "create-user",
            "--phone",
            "0555123456",
            "--password",
            TEST_PASSWORD,
            "--company",
            "مؤسسة الاختبار",
            "--email",
            "test@example.dz",
        ]
    )
    assert code == 0
    assert "Created user #1" in capsys.readouterr().out

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as db:
        user = db.scalar(select(User).where(User.phone == "+213555123456"))
        assert user is not None
        assert user.role.value == "user"
        assert user.company_name == "مؤسسة الاختبار"
        assert user.email_verified_at is not None
        assert verify_password(TEST_PASSWORD, user.password_hash)
    engine.dispose()

    assert (
        main(["create-user", "--phone", "0555123456", "--password", TEST_PASSWORD]) == 1
    )
    assert "مستعمل بالفعل" in capsys.readouterr().err


def test_create_invalid_phone_and_weak_password(tmp_path, monkeypatch, capsys) -> None:
    settings, _db_file = _settings_for(tmp_path, monkeypatch)
    upgrade_database(settings)

    assert main(["create-user", "--phone", "123", "--password", TEST_PASSWORD]) == 1
    assert "غير صالح" in capsys.readouterr().err

    assert main(["create-user", "--phone", "0555987654", "--password", "weak"]) == 1
    assert "8" in capsys.readouterr().err


def test_create_admin(tmp_path, monkeypatch, capsys) -> None:
    settings, _db_file = _settings_for(tmp_path, monkeypatch)
    upgrade_database(settings)
    assert (
        main(
            [
                "create-user",
                "--phone",
                "0555000111",
                "--password",
                ADMIN_PASSWORD,
                "--role",
                "admin",
            ]
        )
        == 0
    )
    capsys.readouterr()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as db:
        user = db.scalar(select(User).where(User.phone == "+213555000111"))
        assert user.role.value == "admin"
    engine.dispose()


def test_reindex_rebuilds_fts(tmp_path, monkeypatch, capsys) -> None:
    settings, _db_file = _settings_for(tmp_path, monkeypatch)
    upgrade_database(settings)
    assert main(["init-db", "--demo"]) == 0
    capsys.readouterr()

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM announcement_fts"))
    with session_scope(factory) as db:
        assert db.execute(text("SELECT COUNT(*) FROM announcement_fts")).scalar() == 0

    assert main(["reindex"]) == 0
    assert "Reindexed 24 announcements" in capsys.readouterr().out
    with session_scope(factory) as db:
        assert db.execute(text("SELECT COUNT(*) FROM announcement_fts")).scalar() == 24
    engine.dispose()


def test_rebuild_index_is_idempotent(tmp_path) -> None:
    engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'reindex.db'}")
    from webapp.db import Base
    from webapp.seed import seed_all

    Base.metadata.create_all(engine)
    ensure_fts(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as db:
        seed_all(db, with_demo=True)
        first = rebuild_index(db)
        second = rebuild_index(db)
        assert first == 24
        assert second == 24
        assert db.execute(text("SELECT COUNT(*) FROM announcement_fts")).scalar() == 24
    engine.dispose()


def test_migration_creates_all_tables(tmp_path, monkeypatch) -> None:
    settings, db_file = _settings_for(tmp_path, monkeypatch, "migration")
    upgrade_database(settings)
    tables = _sqlite_tables(db_file)
    expected = {
        "announcements",
        "announcement_sectors",
        "attachments",
        "users",
        "subscriptions",
        "subscription_sectors",
        "payments",
        "alerts",
        "alert_deliveries",
        "alert_sectors",
        "alert_wilayas",
        "saved_announcements",
        "search_logs",
        "subcontracting_offers",
        "banners",
        "audit_logs",
        "one_time_tokens",
        "wilayas",
        "sectors",
        "issuers",
        "plans",
        "user_sessions",
        "rate_limit_events",
    }
    assert expected <= tables
    assert "announcement_fts" in tables
    assert "alembic_version" in tables


def test_upgrade_twice_is_a_noop(tmp_path, monkeypatch) -> None:
    settings, _db_file = _settings_for(tmp_path, monkeypatch, "twice")
    upgrade_database(settings)
    upgrade_database(settings)
