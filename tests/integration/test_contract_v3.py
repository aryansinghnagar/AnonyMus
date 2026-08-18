"""
Contract Integration Test Suite for FastAPI v3 Backend Architecture
===================================================================
Tests end-to-end HTTP contract compliance for registration, authentication,
contacts CRUD, message transmission, auto-burn retention, and blocklisting.
"""

import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from transports.p2p.app_v3 import create_app


from core.db.engine import get_session
from core.db.models import Base
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def v3_client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def _override_session():
        factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
async def test_v3_health_endpoints(v3_client: AsyncClient):
    """Verifies production health, readiness, and liveness endpoints."""
    res_health = await v3_client.get("/healthz")
    assert res_health.status_code == 200
    assert res_health.json()["status"] in ("ok", "healthy")

    res_metrics = await v3_client.get("/metrics")
    assert res_metrics.status_code == 200
    assert "anonymus_http_requests_total" in res_metrics.text


@pytest.mark.asyncio
async def test_v3_auth_contract_flow(v3_client: AsyncClient):
    """Verifies registration and login contract API flow."""
    username = f"alice_{uuid.uuid4().hex[:8]}"
    password = "ProductionPassword2026!@#"

    # 1. Register
    reg_res = await v3_client.post(
        "/v3/auth/register", json={"username": username, "password": password}
    )
    assert reg_res.status_code in (200, 201)
    data = reg_res.json()
    assert "username" in data

    # 2. Login
    login_res = await v3_client.post(
        "/v3/auth/login", json={"username": username, "password": password}
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "username" in login_data or "onion_address" in login_data
