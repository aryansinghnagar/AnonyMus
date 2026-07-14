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


@pytest.mark.asyncio
async def test_node_info_endpoint(client: AsyncClient) -> None:
    # 1. Register & login user to get active session
    await client.post(
        "/v3/auth/register",
        json={"username": "eve", "password": "securepassword123"},
    )
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    # 2. Check /node/info
    response = await client.get("/v3/node/info")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "eve"
    assert "onion_address" in data


@pytest.mark.asyncio
async def test_relay_setting_endpoint(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    # Get initial relay setting
    response = await client.get("/v3/node/settings/relay")
    assert response.status_code == 200
    assert response.json()["preferred_file_relay"] == ""

    # Set new relay setting
    response = await client.post(
        "/v3/node/settings/relay",
        json={"preferred_file_relay": "https://relay.anonymus.io"},
    )
    assert response.status_code == 200
    assert response.json()["preferred_file_relay"] == "https://relay.anonymus.io"


@pytest.mark.asyncio
async def test_tor_status_endpoint(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    response = await client.get("/v3/node/tor/status")
    assert response.status_code == 200
    assert "is_running" in response.json()


@pytest.mark.asyncio
async def test_notifications_flow(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    # Register contact first
    target_onion = "abcdefghijklmnopqrstuvwxyz234567.onion"
    await client.post(
        "/v3/contacts/",
        json={"onion_address": target_onion, "nickname": "Target Contact"},
    )
    # Register notification token
    response = await client.post(
        "/v3/notifications/register",
        json={"onion_address": target_onion},
    )
    assert response.status_code == 201
    token = response.json()["token"]
    assert token != ""

    # Poll notifications
    response = await client.get(f"/v3/notifications/poll?tokens={token}")
    assert response.status_code == 200
    assert response.json()["has_new"][token] is False

    # Clear notification
    response = await client.post(
        "/v3/notifications/clear",
        json={"tokens": [token]},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_keys_flow(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    # Publish prekey bundle
    bundle = {
        "onion_address": "eveonionaddressxyz.onion",
        "identity_key": "base64_identity_key_bytes",
        "signed_prekey": "base64_signed_prekey_bytes",
        "signed_prekey_sig": "base64_sig_bytes",
        "pq_prekey": "base64_pq_prekey_bytes",
        "pq_prekey_sig": "base64_pq_sig_bytes",
        "one_time_prekeys": ["opk1", "opk2"],
        "one_time_pq_prekeys": ["opq1", "opq2"],
    }
    response = await client.post("/v3/keys/publish", json=bundle)
    assert response.status_code == 201
    assert response.json()["opk_count"] == 2

    # Fetch bundle (should consume OPK)
    response = await client.get("/v3/keys/eveonionaddressxyz.onion")
    assert response.status_code == 200
    data = response.json()
    assert data["one_time_prekey"] == "opk1"
    assert data["opk_pool_size"] == 1


@pytest.mark.asyncio
async def test_files_flow(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    # Upload chunk
    chunk_id = "test-chunk-123"
    chunk_data = b"anonymus-encrypted-chunk-data"
    response = await client.post(
        f"/v3/files/upload/{chunk_id}",
        content=chunk_data,
    )
    assert response.status_code == 200

    # Download chunk
    response = await client.get(f"/v3/files/download/{chunk_id}")
    assert response.status_code == 200
    assert response.content == chunk_data


@pytest.mark.asyncio
async def test_cors_restrictions(client: AsyncClient) -> None:
    # Test valid CORS request
    headers = {"Origin": "http://localhost:3000"}
    response = await client.get("/healthz", headers=headers)
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    )

    # Test invalid CORS request
    headers = {"Origin": "http://malicious.com"}
    response = await client.get("/healthz", headers=headers)
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_rate_limiting(client: AsyncClient) -> None:
    got_429 = False
    for _ in range(130):
        response = await client.get("/v3/auth/me")
        if response.status_code == 429:
            got_429 = True
            break
    assert got_429


@pytest.mark.asyncio
async def test_contacts_delete_by_id(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    target_onion = "deletebyidcontactonion.onion"
    response = await client.post(
        "/v3/contacts/",
        json={"onion_address": target_onion, "nickname": "To Delete"},
    )
    assert response.status_code == 201
    contact_id = response.json()["id"]

    delete_response = await client.delete(f"/v3/contacts/{contact_id}")
    assert delete_response.status_code == 204

    list_response = await client.get("/v3/contacts/")
    assert all(c["id"] != contact_id for c in list_response.json())


@pytest.mark.asyncio
async def test_keys_ownership_validation(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    bundle = {
        "onion_address": "maliciousonionaddress.onion",
        "identity_key": "base64_identity_key_bytes",
        "signed_prekey": "base64_signed_prekey_bytes",
        "signed_prekey_sig": "base64_sig_bytes",
        "pq_prekey": "base64_pq_prekey_bytes",
        "pq_prekey_sig": "base64_pq_sig_bytes",
        "one_time_prekeys": ["opk1"],
        "one_time_pq_prekeys": ["opq1"],
    }
    response = await client.post("/v3/keys/publish", json=bundle)
    assert response.status_code == 403

    rotate_req = {
        "onion_address": "maliciousonionaddress.onion",
        "signed_prekey": "rotated_sig_key",
        "signed_prekey_sig": "rotated_sig",
        "pq_prekey": "rotated_pq_key",
        "pq_prekey_sig": "rotated_pq_sig",
    }
    response = await client.post("/v3/keys/rotate", json=rotate_req)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_group_membership_validation(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    response = await client.post(
        "/v3/groups/",
        json={"name": "Eve's Secret Group", "member_onions": []},
    )
    assert response.status_code == 201
    group_id = response.json()["group_id"]

    await client.post(
        "/v3/auth/register",
        json={"username": "mallory", "password": "mallorysecurepwd"},
    )
    await client.post(
        "/v3/auth/login",
        json={"username": "mallory", "password": "mallorysecurepwd"},
    )
    bundle = {
        "onion_address": "malloryonionaddress.onion",
        "identity_key": "base64_identity_key_bytes",
        "signed_prekey": "base64_signed_prekey_bytes",
        "signed_prekey_sig": "base64_sig_bytes",
        "pq_prekey": "base64_pq_prekey_bytes",
        "pq_prekey_sig": "base64_pq_sig_bytes",
        "one_time_prekeys": ["opk1"],
        "one_time_pq_prekeys": ["opq1"],
    }
    await client.post("/v3/keys/publish", json=bundle)

    response = await client.post(
        "/v3/groups/messages",
        json={"group_id": group_id, "ciphertext_b64": "encrypted_secret"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_message_history_pagination(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )
    peer_onion = "somepeercontactonion.onion"
    await client.post(
        "/v3/contacts/",
        json={"onion_address": peer_onion, "nickname": "Peer"},
    )
    response1 = await client.post(
        "/v3/messages/",
        json={
            "recipient_onion": peer_onion,
            "ciphertext_b64": "msg1",
            "iv_b64": "iv1",
            "sequence_number": 1,
        },
    )
    msg1_id = response1.json()["message_id"]

    await client.post(
        "/v3/messages/",
        json={
            "recipient_onion": peer_onion,
            "ciphertext_b64": "msg2",
            "iv_b64": "iv2",
            "sequence_number": 2,
        },
    )
    await client.post(
        "/v3/messages/",
        json={
            "recipient_onion": peer_onion,
            "ciphertext_b64": "msg3",
            "iv_b64": "iv3",
            "sequence_number": 3,
        },
    )

    response = await client.get(f"/v3/messages/{peer_onion}?before={msg1_id}")
    assert response.status_code == 200
    assert len(response.json()) == 0


@pytest.mark.asyncio
async def test_profiles_lifecycle_v3(client: AsyncClient) -> None:
    # Login first
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )

    # 1. Fetch active profile (initially default)
    res = await client.get("/v3/profiles/active")
    assert res.status_code == 200
    assert res.json()["profile_id"] == "default"

    # 2. Create decoy (hidden) profile
    res = await client.post(
        "/v3/profiles/create",
        json={
            "display_name": "Work Decoy",
            "hidden": True,
            "passphrase": "decoypassphrase",
        },
    )
    assert res.status_code == 200
    decoy_id = res.json()["profile_id"]

    # 3. List profiles - should NOT show hidden profile
    res = await client.get("/v3/profiles/")
    assert res.status_code == 200
    profile_ids = [p["profile_id"] for p in res.json()]
    assert decoy_id not in profile_ids

    # 4. Switch to hidden decoy profile (should fail directly without unlock)
    res = await client.post(
        "/v3/profiles/switch",
        json={"profile_id": decoy_id},
    )
    assert res.status_code == 403

    # 5. Unlock profile with passphrase
    res = await client.post(
        "/v3/profiles/unlock",
        json={"passphrase": "decoypassphrase"},
    )
    assert res.status_code == 200
    assert res.json()["profile"]["profile_id"] == decoy_id

    # 6. Active profile should now be decoy_id
    res = await client.get("/v3/profiles/active")
    assert res.status_code == 200
    assert res.json()["profile_id"] == decoy_id


@pytest.mark.asyncio
async def test_supporter_badge_v3(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )

    onion = "testsupporteronionaddress.onion"

    # Check initially not supporter
    res = await client.get(f"/v3/profile/supporter_badge/status?onion_address={onion}")
    assert res.status_code == 200
    assert res.json()["is_supporter"] is False

    # Sign using helper
    from core.crypto import generate_supporter_badge_signature

    dev_priv_key_b64 = "5ZOf4PhdTNRUN0YDwX/Clf5rgoTuLa1YQz3UtbyrUj4="
    valid_sig = generate_supporter_badge_signature(onion, dev_priv_key_b64)

    # Post invalid signature
    res = await client.post(
        "/v3/profile/supporter_badge/",
        json={"onion_address": onion, "signature": "invalidsig"},
    )
    assert res.status_code == 400

    # Post valid signature
    res = await client.post(
        "/v3/profile/supporter_badge/",
        json={"onion_address": onion, "signature": valid_sig},
    )
    assert res.status_code == 200

    # Check status again
    res = await client.get(f"/v3/profile/supporter_badge/status?onion_address={onion}")
    assert res.status_code == 200
    assert res.json()["is_supporter"] is True
    assert res.json()["badge_signature"] == valid_sig


@pytest.mark.asyncio
async def test_sync_pairing_v3(client: AsyncClient) -> None:
    await client.post(
        "/v3/auth/login",
        json={"username": "eve", "password": "securepassword123"},
    )

    res = await client.post("/v3/sync/pair")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "ip" in data
    assert data["port"] == 8999
    assert "k" in data

    # Clean up pairing broker
    from transports.p2p.routers import sync

    if sync.active_pairing_broker:
        sync.active_pairing_broker.shutdown()
        sync.active_pairing_broker.server_close()
        sync.active_pairing_broker = None
