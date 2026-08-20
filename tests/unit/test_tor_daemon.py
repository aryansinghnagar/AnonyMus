"""
Unit test suite for core.tor_daemon TorControlPortClient.

Audit fix ANO-CODE-005 (C2): the previous stub returned a fake onion
containing the target_port as a substring (``anonymusnode8080v3.onion``).
The new stem-based implementation produces real v3-format onion addresses
(56 base32 chars + ``.onion``) — these never contain a decimal port
number, so the assertion ``"8080" in onion_addr`` was updated to check
the v3 format regex instead.
"""

from __future__ import annotations

import os
import re

import pytest
from core.tor_daemon import TorControlPortClient

# Audit fix ANO-CODE-005 (C2): force test-mode backend so the suite does
# not require a running Tor daemon. See core.tor_daemon._is_test_mode().
os.environ.setdefault("ANONYMUS_TOR_TEST_MODE", "1")

_V3_ONION_RE = re.compile(r"^[a-z2-7]{56}\.onion$")


@pytest.mark.asyncio
async def test_tor_control_port_authentication():
    client = TorControlPortClient()
    assert client.authenticated is False
    res = await client.authenticate()
    assert res is True
    assert client.authenticated is True


@pytest.mark.asyncio
async def test_add_and_remove_onion_service():
    client = TorControlPortClient()
    await client.authenticate()

    add_res = await client.add_onion_service(target_port=8080)
    assert add_res["success"] is True
    onion_addr = add_res["onion_address"]
    # Audit fix ANO-CODE-005 (C2): onion address is now a real v3 onion
    # (56 base32 chars + .onion), not a stub containing the port number.
    assert _V3_ONION_RE.match(
        onion_addr
    ), f"Expected v3 onion format (56 base32 chars + .onion); got {onion_addr!r}"

    assert onion_addr in client.list_active_onions()

    rem_res = await client.remove_onion_service(onion_addr)
    assert rem_res is True
    assert onion_addr not in client.list_active_onions()


@pytest.mark.asyncio
async def test_unauthenticated_tor_commands_raise_error():
    client = TorControlPortClient()
    with pytest.raises(PermissionError, match="not authenticated"):
        await client.add_onion_service(target_port=8000)
