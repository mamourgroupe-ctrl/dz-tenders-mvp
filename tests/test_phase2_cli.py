"""Operational maintenance command (expiry + renewal reminders)."""

from __future__ import annotations

from sqlalchemy import select

from tests.conftest import TEST_PASSWORD, subscribe
from webapp.cli import main, upgrade_database
from webapp.config import Settings
from webapp.db import make_engine, make_session_factory, session_scope
from webapp.models import User
from webapp.seed import create_user


def _settings_for(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'maintenance.db'}"
    monkeypatch.setenv("APP_DATABASE_URL", url)
    return Settings.from_env()


def _seed_user(db, phone: str, email: str) -> User:
    return create_user(
        db,
        phone=phone,
        password=TEST_PASSWORD,
        company_name="مؤسسة الصيانة",
        email=email,
    )


def test_maintenance_expires_and_reminds_once(tmp_path, monkeypatch, capsys) -> None:
    settings = _settings_for(tmp_path, monkeypatch)
    upgrade_database(settings)
    assert main(["seed"]) == 0
    capsys.readouterr()

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as db:
        ending = _seed_user(db, "0555400001", "ending@example.dz")
        late = _seed_user(db, "0555400002", "late@example.dz")
        ending_sub = subscribe(db, ending, ends_days=3)
        late_sub = subscribe(db, late, ends_days=-2)

    assert main(["maintenance"]) == 0
    output = capsys.readouterr().out
    assert "'expired': 1" in output
    assert "'reminders_sent': 1" in output

    with session_scope(factory) as db:
        ending_sub = db.get(type(ending_sub), ending_sub.id)
        late_sub = db.get(type(late_sub), late_sub.id)
        assert ending_sub is not None and ending_sub.reminder_sent_at is not None
        assert late_sub is not None and late_sub.status.value == "expired"

    # A second tick is a no-op: no duplicate emails, nothing left to expire.
    assert main(["maintenance"]) == 0
    output = capsys.readouterr().out
    assert "'expired': 0" in output
    assert "'reminders_sent': 0" in output
    engine.dispose()


def test_maintenance_ignores_users_without_email(tmp_path, monkeypatch, capsys) -> None:
    settings = _settings_for(tmp_path, monkeypatch)
    upgrade_database(settings)
    assert main(["seed"]) == 0
    capsys.readouterr()

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as db:
        user = _seed_user(db, "0555400003", "kept@example.dz")
        user.email = None
        subscribe(db, user, ends_days=2)

    assert main(["maintenance"]) == 0
    output = capsys.readouterr().out
    assert "'reminders_sent': 0" in output

    with session_scope(factory) as db:
        user = db.scalar(select(User).where(User.phone == "+213555400003"))
        assert user is not None
    engine.dispose()
