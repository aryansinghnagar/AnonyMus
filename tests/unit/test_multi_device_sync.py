"""
Unit test suite for core.sync MultiDeviceSyncManager.
"""

from __future__ import annotations

import time
import pytest

from core.sync import MultiDeviceSyncManager, SyncEnvelope


def test_sync_manager_device_authorization():
    manager = MultiDeviceSyncManager(owner_onion="alice.onion", device_id="dev-1")
    assert manager.is_device_authorized("dev-1") is True
    assert manager.is_device_authorized("dev-2") is False

    manager.register_paired_device("dev-2")
    assert manager.is_device_authorized("dev-2") is True


def test_sync_envelope_pack_and_unpack():
    manager = MultiDeviceSyncManager(owner_onion="alice.onion", device_id="dev-1")
    env = manager.create_sync_envelope(
        payload_type="contact_sync",
        encrypted_payload_b64="cGF5bG9hZA==",
        nonce_b64="bm9uY2U=",
        sequence_id=101,
    )

    serialized = manager.serialize_envelope(env)
    reconstructed = manager.deserialize_envelope(serialized)

    assert reconstructed.device_id == "dev-1"
    assert reconstructed.owner_onion == "alice.onion"
    assert reconstructed.payload_type == "contact_sync"
    assert reconstructed.sequence_id == 101


def test_process_incoming_envelope_duplication_and_validation():
    manager = MultiDeviceSyncManager(owner_onion="alice.onion", device_id="dev-1")
    manager.register_paired_device("dev-2")

    env = SyncEnvelope(
        device_id="dev-2",
        owner_onion="alice.onion",
        payload_type="history_replay",
        encrypted_payload_b64="ZGF0YQ==",
        nonce_b64="bm9uY2U=",
        timestamp=time.time(),
        sequence_id=500,
    )

    res1 = manager.process_incoming_envelope(env)
    assert res1["status"] == "applied"
    assert res1["sequence_id"] == 500

    # Second processing should be flagged as duplicate
    res2 = manager.process_incoming_envelope(env)
    assert res2["status"] == "duplicate"


def test_unauthorized_device_envelope_rejection():
    manager = MultiDeviceSyncManager(owner_onion="alice.onion", device_id="dev-1")
    env = SyncEnvelope(
        device_id="rogue-dev",
        owner_onion="alice.onion",
        payload_type="contact_sync",
        encrypted_payload_b64="ZGF0YQ==",
        nonce_b64="bm9uY2U=",
        timestamp=time.time(),
        sequence_id=1,
    )

    with pytest.raises(ValueError, match="is not authorized for sync"):
        manager.process_incoming_envelope(env)
