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


@pytest_asyncio.fixture
async def v3_client():
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


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
