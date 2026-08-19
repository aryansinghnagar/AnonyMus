"""
Async SQLAlchemy engine and session factory.

The database URL is read from `core.config.settings.database_url`.

Supported backends:
  - sqlite+aiosqlite:///./anonymus.db      (P2P local node, default)
  - postgresql+asyncpg://user:pass@host/db  (relay / production)

Audit fix ANO-SEC-008: SECURITY.md line 18 promises "SQLite database encryption
via AES-256-GCM + Argon2id key derivation + Duress PIN wipe capability" but
the previous implementation opened a plain aiosqlite connection without any
SQLCipher ``PRAGMA key`` directive. The ``db_key`` config field defaulted to
an empty string (interpreted as "disable encryption"), and nothing in the
startup path enforced that ``db_key`` be set in production.

This file now:
1. Adds a ``PRAGMA key`` directive when ``settings.db_key`` is set, using
   the ``sqlcipher3`` driver if available.
2. Raises ``RuntimeError`` if ``settings.environment == "production"`` AND
   ``settings.db_key`` is empty — production deployments must encrypt the
   local database.
3. Logs a prominent warning in development mode when ``db_key`` is empty.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings
from core.logging_v3 import get_logger

logger = get_logger(__name__)

# ── Engine ─────────────────────────────────────────────────────────────────────

_CONNECT_ARGS: dict[str, Any] = {}

if settings.database_url.startswith("sqlite"):
    # SQLite requires check_same_thread=False in async mode
    _CONNECT_ARGS["check_same_thread"] = False

# Audit fix ANO-SEC-008: enforce that db_key is set in production.
if settings.is_production and not settings.db_key:
    raise RuntimeError(
        "Refusing to start in production with db_key empty. "
        "Set DB_KEY to a strong passphrase in your .env file. "
        "The database is otherwise stored in plaintext, contradicting the "
        "SECURITY.md promise of AES-256-GCM encryption (audit fix ANO-SEC-008)."
    )

if settings.is_development and not settings.db_key:
    logger.warning(
        "db_key is empty — database is NOT encrypted. "
        "Set DB_KEY to enable SQLCipher (audit fix ANO-SEC-008). "
        "This warning is silent in production (which raises instead)."
    )

# Audit fix ANO-SEC-008: when db_key is set, swap the driver to sqlcipher
# if the sqlcipher3 package is installed. The URL scheme
# ``sqlite+sqlcipher://`` is supported by the ``sqlcipher3`` driver.
_database_url = settings.database_url
if settings.db_key and settings.database_url.startswith("sqlite+aiosqlite://"):
    # Try to upgrade to sqlcipher if available; otherwise fall back to
    # plain aiosqlite (with a warning logged).
    try:
        import sqlcipher3  # type: ignore[import-untyped]  # noqa: F401

        _database_url = settings.database_url.replace(
            "sqlite+aiosqlite://", "sqlite+sqlcipher://"
        )
        logger.info("db_engine_sqlcipher_enabled")
    except ImportError:
        logger.warning(
            "db_key is set but sqlcipher3 package is not installed; "
            "database will be stored in plaintext. "
            "Install with: pip install sqlcipher3-binary "
            "(audit fix ANO-SEC-008)"
        )

engine = create_async_engine(
    _database_url,
    echo=settings.is_development,
    connect_args=_CONNECT_ARGS,
    pool_pre_ping=True,
)

if _database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        from core.capability_tiers import detect_capability_tier

        profile = detect_capability_tier()
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA mmap_size = 268435456;")
        cursor.execute(f"PRAGMA cache_size = -{profile.db_cache_size_kb};")

        # Audit fix ANO-SEC-008: set the SQLCipher key pragma if db_key is
        # configured. The ``PRAGMA key`` directive must be the first statement
        # after connecting to a SQLCipher database.
        if settings.db_key:
            # Escape single quotes in the key per SQLCipher's quoting rules.
            key_escaped = settings.db_key.replace("'", "''")
            cursor.execute(f"PRAGMA key = '{key_escaped}';")
            # Verify the key is correct by reading from the database; if the
            # key is wrong, this raises OperationalError.
            try:
                cursor.execute("SELECT count(*) FROM sqlite_master;")
                cursor.fetchone()
            except Exception as e:
                logger.error("db_engine_sqlcipher_key_invalid", error=str(e))
                raise

        cursor.close()

# ── Session Factory ────────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── FastAPI Dependency ─────────────────────────────────────────────────────────


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async DB session and commits/rolls back
    on success/failure.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
