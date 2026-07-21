"""
Unit test suite for core.tor_daemon TorControlPortClient.
"""

from __future__ import annotations

import pytest
from core.tor_daemon import TorControlPortClient


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
    assert onion_addr.endswith(".onion")
    assert "8080" in onion_addr

    assert onion_addr in client.list_active_onions()

    rem_res = await client.remove_onion_service(onion_addr)
    assert rem_res is True
    assert onion_addr not in client.list_active_onions()


@pytest.mark.asyncio
async def test_unauthenticated_tor_commands_raise_error():
    client = TorControlPortClient()
    with pytest.raises(PermissionError, match="not authenticated"):
        await client.add_onion_service(target_port=8000)
