"""
Root conftest.py — shared pytest fixtures for all test suites.

Provides:
  - `anyio_backend`: forces asyncio backend for all async tests
  - `settings`: an isolated pydantic-settings Settings instance with test overrides
  - `test_engine`: an in-memory SQLite async engine (session-scoped)
  - `db_session`: a per-test transactional session that rolls back on teardown
  - `app`: the FastAPI v3 application with the DB overridden
  - `client`: an httpx AsyncClient backed by the ASGI app
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.db.engine import get_session
from core.db.models import Base

# ── Test constants ─────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
TEST_SECRET_KEY = "test-secret-key-not-for-production-at-all-32b"

# ── Force asyncio backend for pytest-asyncio ──────────────────────────────────

pytest_plugins = ("pytest_asyncio",)


# ── Database engine (session-scoped: one DB per test session) ─────────────────


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Per-test transactional session (rolls back after every test) ───────────────


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncSession:
    factory = async_sessionmaker(
        test_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session
        await session.rollback()


# ── FastAPI ASGI client with the DB overridden ────────────────────────────────


@pytest_asyncio.fixture
async def client(test_engine) -> AsyncClient:
    """Async HTTP client backed by the FastAPI ASGI app with in-memory SQLite."""
    # Import here to avoid top-level side effects during collection.
    from transports.p2p.app_v3 import create_app

    app = create_app()

    async def _override_session():
        factory = async_sessionmaker(
            test_engine,
            expire_on_commit=False,
            autoflush=False,
        )
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
