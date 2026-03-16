"""Alembic environment configuration.

Reads DATABASE_URL from tender_backend settings and runs migrations
using raw SQL (no SQLAlchemy ORM models).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_database_url() -> str:
    """Resolve database URL from env or settings, converting to SQLAlchemy format."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        from tender_backend.core.config import get_settings
        url = get_settings().database_url or ""
    # Alembic/SQLAlchemy needs the +psycopg driver suffix
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    context.configure(
        url=_get_database_url(),
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    engine = create_engine(_get_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
