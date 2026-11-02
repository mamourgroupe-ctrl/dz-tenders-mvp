"""Alembic environment wired to the product database URL.

URL precedence: ``APP_DATABASE_URL`` → ``-x db_url=…`` → ``alembic.ini``.
SQLite runs in batch mode so future ALTERs stay portable.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from webapp import models  # noqa: F401  (registers every table on Base.metadata)
from webapp.config import Settings
from webapp.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = Settings.from_env(load_env_file=False)
url = (
    os.getenv("APP_DATABASE_URL")
    or config.get_main_option("sqlalchemy.url")
    or settings.database_url
)

if url.startswith("sqlite+pysqlite:///") and not url.startswith("sqlite+pysqlite:////"):
    # Resolve the relative SQLite path against the repository root, exactly like
    # the application does, so CLI and container migrations target one file.
    relative = url.removeprefix("sqlite+pysqlite:///")
    if relative != ":memory:":
        absolute = (Path(__file__).resolve().parent.parent / relative).resolve()
        url = f"sqlite+pysqlite:///{absolute}"

config.set_main_option("sqlalchemy.url", url)
target_metadata = Base.metadata


def include_object(obj, name: str, type_: str, reflected: bool, compare_to) -> bool:
    """Keep the FTS5 virtual table and its shadow tables out of autogenerate."""
    is_fts = type_ == "table" and (
        name == "announcement_fts" or str(name).startswith("announcement_fts_")
    )
    return not is_fts


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live connection."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
