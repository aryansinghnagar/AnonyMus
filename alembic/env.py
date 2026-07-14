"""
Alembic migration environment for AnonyMus v3.

Configured for async SQLAlchemy (aiosqlite / asyncpg) with autogenerate
support from the core.db.models ORM models.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import our ORM Base so autogenerate can detect schema changes
from core.db.models import Base

# ── Alembic config object ──────────────────────────────────────────────────────
config = context.config

# Wire up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata drives --autogenerate
target_metadata = Base.metadata


# ── Offline mode ───────────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (used for SQL diff generation)."""
    from core.config import settings

    url = config.get_main_option("sqlalchemy.url")
    if not url or "driver://user" in url:
        url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online (async) mode ────────────────────────────────────────────────────────


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from core.config import settings

    configuration = config.get_section(config.config_ini_section) or {}
    # Allow alembic.ini override; fall back to settings.database_url
    url = configuration.get("sqlalchemy.url")
    if not url or "driver://user" in url:
        configuration["sqlalchemy.url"] = settings.database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Entry point ────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
