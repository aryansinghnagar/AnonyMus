"""
Async SQLAlchemy engine and session factory.

The database URL is read from `core.config.settings.database_url`.

Supported backends:
  - sqlite+aiosqlite:///./anonymus.db      (P2P local node, default)
  - postgresql+asyncpg://user:pass@host/db  (relay / production)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings

# ── Engine ─────────────────────────────────────────────────────────────────────

_CONNECT_ARGS: dict[str, Any] = {}

if settings.database_url.startswith("sqlite"):
    # SQLite requires check_same_thread=False in async mode
    _CONNECT_ARGS["check_same_thread"] = False

engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,
    connect_args=_CONNECT_ARGS,
    pool_pre_ping=True,
)

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

    Usage::

        @router.get("/users/{user_id}")
        async def get_user(
            user_id: int,
            session: AsyncSession = Depends(get_session),
        ):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
