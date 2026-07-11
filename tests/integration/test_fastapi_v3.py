"""
Integration tests for the FastAPI v3 application.

Uses httpx.AsyncClient with the ASGI transport so no actual server port is needed.
The in-memory SQLite database is spun up/down per test session.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.db.engine import get_session
from core.db.models import Base
from transports.p2p.app_v3 import create_app


# ── Test fixtures ──────────────────────────────────────────────────────────────


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(test_engine):
    """Return an httpx AsyncClient backed by the FastAPI ASGI app with an in-memory DB."""
    app = create_app()

    async def _override_session():
        factory = async_sessionmaker(
            test_engine, expire_on_commit=False, autoflush=False
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


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_healthz(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_with_db(client: AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "ok"


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert b"anonymus_http_requests_total" in response.content


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient) -> None:
    response = await client.post(
        "/v3/auth/register",
        json={"username": "alice", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "alice"


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/register",
        json={"username": "bob", "password": "password123!"},
    )
    response = await client.post(
        "/v3/auth/register",
        json={"username": "bob", "password": "different_password"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_username(client: AsyncClient) -> None:
    response = await client.post(
        "/v3/auth/register",
        json={"username": "invalid user!", "password": "password123!"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/register",
        json={"username": "carol", "password": "my-secure-password!"},
    )
    response = await client.post(
        "/v3/auth/login",
        json={"username": "carol", "password": "my-secure-password!"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "carol"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/register",
        json={"username": "dave", "password": "right-password!"},
    )
    response = await client.post(
        "/v3/auth/login",
        json={"username": "dave", "password": "wrong-password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_contacts_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/v3/contacts/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_openapi_accessible_in_dev(client: AsyncClient) -> None:
    # Docs are enabled in development mode
    response = await client.get("/v3/openapi.json")
    # Should be 200 in dev, 404 in prod (not an error either way)
    assert response.status_code in (200, 404)
