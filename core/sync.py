"""
Multi-Device State Synchronization System (RFC 0002)
===================================================
Manages state replication, session synchronization, and contact blocklist
updates across paired user devices using encrypted sync envelopes.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.capability_tiers import detect_capability_tier


@dataclass
class SyncEnvelope:
    device_id: str
    owner_onion: str
    payload_type: str  # "contact_sync" | "history_replay" | "prekey_rotation"
    encrypted_payload_b64: str
    nonce_b64: str
    timestamp: float
    sequence_id: int


class MultiDeviceSyncManager:
    """
    Handles queuing, validation, and de-duplication of multi-device sync envelopes.
    """

    def __init__(self, owner_onion: str, device_id: str) -> None:
        self.owner_onion = owner_onion
        self.device_id = device_id
        self._synced_devices: set[str] = set()
        self._processed_sequence_ids: set[int] = set()
        self._capability_profile = detect_capability_tier()

    def register_paired_device(self, paired_device_id: str) -> None:
        """Register a secondary paired device ID authorized for sync."""
        self._synced_devices.add(paired_device_id)

    def is_device_authorized(self, device_id: str) -> bool:
        """Verify if a device is authorized to sync state."""
        return device_id == self.device_id or device_id in self._synced_devices

    def create_sync_envelope(
        self,
        payload_type: str,
        encrypted_payload_b64: str,
        nonce_b64: str,
        sequence_id: int,
    ) -> SyncEnvelope:
        """Pack an encrypted sync payload into an authenticated SyncEnvelope."""
        return SyncEnvelope(
            device_id=self.device_id,
            owner_onion=self.owner_onion,
            payload_type=payload_type,
            encrypted_payload_b64=encrypted_payload_b64,
            nonce_b64=nonce_b64,
            timestamp=time.time(),
            sequence_id=sequence_id,
        )

    def process_incoming_envelope(self, envelope: SyncEnvelope) -> dict[str, Any]:
        """
        Validates timestamp freshness, sequence duplication, and device authorization.
        """
        if not self.is_device_authorized(envelope.device_id):
            raise ValueError(f"Device {envelope.device_id} is not authorized for sync")

        if envelope.sequence_id in self._processed_sequence_ids:
            return {"status": "duplicate", "sequence_id": envelope.sequence_id}

        # Validate timestamp freshness (max 300 seconds skew allowed)
        if abs(time.time() - envelope.timestamp) > 300.0:
            raise ValueError("Sync envelope timestamp out of acceptable bounds")

        # Cap processed sequence IDs pool according to hardware tier
        if (
            len(self._processed_sequence_ids)
            >= self._capability_profile.max_in_memory_messages
        ):
            self._processed_sequence_ids.clear()

        self._processed_sequence_ids.add(envelope.sequence_id)
        return {
            "status": "applied",
            "type": envelope.payload_type,
            "sequence_id": envelope.sequence_id,
        }

    def serialize_envelope(self, envelope: SyncEnvelope) -> str:
        """JSON-serialize an envelope for transport."""
        return json.dumps(asdict(envelope))

    def deserialize_envelope(self, raw_json: str) -> SyncEnvelope:
        """Parse and reconstruct a SyncEnvelope from JSON."""
        data = json.loads(raw_json)
        return SyncEnvelope(**data)
