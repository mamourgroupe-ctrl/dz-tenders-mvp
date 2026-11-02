"""Operational commands for the public platform.

Examples::

    python -m webapp.cli init-db --demo
    python -m webapp.cli seed --demo
    python -m webapp.cli create-user --phone 0555123456 --company "مؤسسة"
    python -m webapp.cli reindex
    python -m webapp.cli maintenance
    python -m webapp.cli serve --port 8000

``maintenance`` is the job the scheduler runs daily: it expires ended
subscriptions and sends the renewal reminder once per subscription. Phase 3
adds the announcement digest as a sibling command on the same schedule.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

from webapp import billing
from webapp.config import REPO_ROOT, Settings
from webapp.db import ensure_fts, make_engine, make_session_factory, session_scope
from webapp.enums import UserRole
from webapp.notifications import build_email_provider, renewal_email
from webapp.search_index import rebuild_index
from webapp.seed import create_user, load_wilayas_override, seed_all
from webapp.timeutils import days_until, format_date_ar, utcnow

logger = logging.getLogger("webapp.cli")


def _settings() -> Settings:
    return Settings.from_env()


def _alembic_config(settings: Settings) -> AlembicConfig:
    """Build an Alembic config bound to the resolved database URL."""
    config = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def upgrade_database(settings: Settings) -> None:
    """Run every pending migration."""
    db_file = settings.database_path()
    if db_file is not None:
        db_file.parent.mkdir(parents=True, exist_ok=True)
    alembic_command.upgrade(_alembic_config(settings), "head")


def _session(settings: Settings):
    engine = make_engine(settings.database_url)
    return engine, make_session_factory(engine)


def _wilayas_override(settings: Settings):
    if not settings.wilayas_file:
        return None
    return load_wilayas_override(settings.wilayas_file)


def cmd_init_db(args: argparse.Namespace) -> int:
    """Migrate the schema and seed reference data (idempotent)."""
    settings = _settings()
    upgrade_database(settings)
    engine, factory = _session(settings)
    ensure_fts(engine)
    with session_scope(factory) as db:
        summary = seed_all(
            db,
            with_demo=args.demo,
            settings=settings,
            wilayas_override=_wilayas_override(settings),
        )
    print(f"Database ready: {settings.database_url}")
    print(f"Seeded: {summary.as_dict()}")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    """Seed taxonomy/plans and, with ``--demo``, demonstration content."""
    settings = _settings()
    engine, factory = _session(settings)
    ensure_fts(engine)
    with session_scope(factory) as db:
        summary = seed_all(
            db,
            with_demo=args.demo,
            settings=settings,
            wilayas_override=_wilayas_override(settings),
        )
    print(f"Seeded: {summary.as_dict()}")
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    """Rebuild the FTS index and normalised search text."""
    settings = _settings()
    engine, factory = _session(settings)
    ensure_fts(engine)
    with session_scope(factory) as db:
        count = rebuild_index(db)
    print(f"Reindexed {count} announcements")
    return 0


def cmd_create_user(args: argparse.Namespace) -> int:
    """Create a user (or admin) with a validated phone and password."""
    settings = _settings()
    password = args.password or getpass.getpass("Password: ")
    _engine, factory = _session(settings)
    with session_scope(factory) as db:
        try:
            user = create_user(
                db,
                phone=args.phone,
                password=password,
                company_name=args.company,
                email=args.email,
                role=UserRole(args.role),
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    print(f"Created user #{user.id} ({user.phone}, role={user.role.value})")
    return 0


def cmd_maintenance(args: argparse.Namespace) -> int:
    """Expire ended subscriptions and send renewal reminders.

    Meant for a daily cron/worker tick; both operations are idempotent, so a
    re-run after a crash never duplicates an email (``reminder_sent_at``).
    """
    settings = _settings()
    days = args.days if args.days is not None else settings.renewal_reminder_days
    provider = build_email_provider(settings)

    def send(subscription) -> None:
        user = subscription.user
        message = renewal_email(
            settings,
            to=user.email or "",
            company_name=user.company_name,
            plan_name=subscription.plan.name_ar,
            days_left=max(days_until(subscription.ends_at, now=utcnow()) or 0, 0),
            ends_at=format_date_ar(subscription.ends_at),
        )
        provider.send(message)

    _engine, factory = _session(settings)
    with session_scope(factory) as db:
        summary = billing.run_maintenance(db, days=days, send=send)

    print(f"Maintenance: {summary.as_dict()}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the development server through Uvicorn."""
    import uvicorn

    uvicorn.run(
        "webapp.web.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m webapp.cli",
        description="DZ Tenders platform operations",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-db", help="run migrations and seed reference data")
    init.add_argument("--demo", action="store_true", help="also seed sample content")
    init.set_defaults(func=cmd_init_db)

    seed = sub.add_parser("seed", help="seed taxonomy, plans and optional demo data")
    seed.add_argument("--demo", action="store_true", help="seed demonstration content")
    seed.set_defaults(func=cmd_seed)

    reindex = sub.add_parser("reindex", help="rebuild the Arabic search index")
    reindex.set_defaults(func=cmd_reindex)

    user = sub.add_parser("create-user", help="create a subscriber or staff account")
    user.add_argument("--phone", required=True, help="Algerian phone number")
    user.add_argument("--password", help="password (prompted when omitted)")
    user.add_argument("--company", default="", help="company name")
    user.add_argument("--email", default=None, help="email address")
    user.add_argument(
        "--role",
        default=UserRole.USER.value,
        choices=[role.value for role in UserRole],
        help="account role",
    )
    user.set_defaults(func=cmd_create_user)

    maintenance = sub.add_parser(
        "maintenance", help="expire subscriptions and send renewal reminders"
    )
    maintenance.add_argument(
        "--days",
        type=int,
        default=None,
        help="reminder window in days (defaults to APP_RENEWAL_REMINDER_DAYS)",
    )
    maintenance.set_defaults(func=cmd_maintenance)

    serve = sub.add_parser("serve", help="run the web application locally")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns a process exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess
    raise SystemExit(main())
