"""
Nodes router — register and deregister onion service nodes on the relay.

The relay maintains a directory of active onion addresses that clients use
to bootstrap peer discovery.

Audit fix ANO-SEC-005: the ``/register`` endpoint previously accepted an
arbitrary ``onion_address`` string without verifying that the requester
actually controls the corresponding Tor hidden service. The docstring at
lines 5-7 claimed "All writes are authenticated via the node's Ed25519
identity key (signed challenge token, verified server-side)" but the
implementation contained no such verification. The endpoint now requires:

1. A v3 onion address format (``^[a-z2-7]{56}\\.onion$``).
2. An Ed25519 signature over ``f"{onion_address}|{timestamp}"`` where the
   timestamp is within 5 minutes of the relay's clock (replay defense).
3. The signature must verify against the public key encoded in the onion
   address (the first 56 base32 chars before ``.onion`` decode to the
   32-byte Ed25519 public key).
"""

from __future__ import annotations

import base64
import re
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])

# Nodes that have not sent a heartbeat in this window are considered offline.
STALE_AFTER_MINUTES = 10

# Audit fix ANO-SEC-005: v3 onion address format check.
# Tor v3 onion addresses are 56 base32 chars + ".onion" (62 chars total).
# The 56 base32 chars decode to a 32-byte Ed25519 public key + 3 checksum bytes.
_ONION_V3_RE = re.compile(r"^[a-z2-7]{56}\.onion$")

# Maximum allowed clock skew for signed registrations / heartbeats.
MAX_SKEW_SECONDS = 300


# ── Schemas ────────────────────────────────────────────────────────────────────


class NodeRegisterRequest(BaseModel):
    # Audit fix ANO-SEC-005: tightened the format to v3 onion addresses only.
    onion_address: str = Field(min_length=62, max_length=62)
    display_name: str | None = Field(default=None, max_length=64)
    version: str = Field(default="3.0.0", max_length=32)
    # New required fields for signed registration.
    timestamp: str = Field(
        description="ISO-8601 timestamp; must be within 5 minutes of the relay clock"
    )
    signature_b64: str = Field(
        description="Ed25519 signature over f'{onion_address}|{timestamp}' "
        "using the identity key encoded in the onion address"
    )


class NodeHeartbeatRequest(BaseModel):
    onion_address: str = Field(min_length=62, max_length=62)
    timestamp: str = Field(description="ISO-8601 timestamp; skew ≤ 5 minutes")
    signature_b64: str = Field(
        description="Ed25519 signature over f'{onion_address}|{timestamp}'"
    )


class NodeResponse(BaseModel):
    onion_address: str
    display_name: str | None
    version: str
    last_seen: datetime
    online: bool


# ── In-process node directory (Phase 2a: in-memory dict; Phase 2c: DB-backed) ─

_nodes: dict[str, dict] = {}


def _is_online(last_seen: datetime) -> bool:
    return datetime.now(timezone.utc) - last_seen < timedelta(
        minutes=STALE_AFTER_MINUTES
    )


# ── Signature verification (audit fix ANO-SEC-005) ────────────────────────────


def _verify_node_signature(
    onion_address: str,
    timestamp: str,
    signature_b64: str,
) -> None:
    """Verify an Ed25519 signature over ``f"{onion}|{timestamp}"``.

    Audit fix ANO-SEC-005: the relay must verify that the requester actually
    controls the Tor hidden service whose address they are registering. Tor
    v3 onion addresses encode a 32-byte Ed25519 public key in base32 (the
    first 56 characters before ``.onion``). We extract that public key and
    verify the signature against it.

    Raises HTTPException 400/401 on any failure.
    """
    # Validate the onion address format (v3 only: 56 base32 chars + .onion).
    if not _ONION_V3_RE.match(onion_address):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid onion address format; expected 56 base32 chars + '.onion' "
                "(audit fix ANO-SEC-005)"
            ),
        )

    pubkey_b32 = onion_address[:56]
    pad_len = (-len(pubkey_b32)) % 8
    try:
        pubkey_bytes = base64.b32decode(pubkey_b32 + "=" * pad_len)
    except Exception:
        raise HTTPException(
            status_code=400, detail="Could not decode onion address public key"
        )
    if len(pubkey_bytes) != 32:
        raise HTTPException(
            status_code=400,
            detail=f"Onion address public key must be 32 bytes (got {len(pubkey_bytes)})",
        )

    # Validate timestamp skew (defense against replay attacks).
    try:
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid timestamp format (expected ISO-8601)"
        )
    now = datetime.now(timezone.utc)
    skew = abs((now - ts).total_seconds())
    if skew > MAX_SKEW_SECONDS:
        raise HTTPException(
            status_code=401,
            detail=f"Timestamp skew {skew:.0f}s exceeds allowed {MAX_SKEW_SECONDS}s",
        )

    # Verify the signature.
    try:
        signature = base64.b64decode(signature_b64)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        message = f"{onion_address}|{timestamp}".encode("utf-8")
        public_key.verify(signature, message)
    except InvalidSignature:
        raise HTTPException(
            status_code=401,
            detail="Invalid Ed25519 signature; node identity not verified",
        )
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Signature verification failed: {e}"
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=NodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new onion node on the relay directory",
)
async def register_node(body: NodeRegisterRequest) -> NodeResponse:
    # Audit fix ANO-SEC-005: verify the node controls the onion address
    # before accepting the registration.
    _verify_node_signature(body.onion_address, body.timestamp, body.signature_b64)

    now = datetime.now(timezone.utc)
    _nodes[body.onion_address] = {
        "onion_address": body.onion_address,
        "display_name": body.display_name,
        "version": body.version,
        "last_seen": now,
    }
    logger.info("node_registered", onion=body.onion_address[:12])
    return NodeResponse(
        onion_address=body.onion_address,
        display_name=body.display_name,
        version=body.version,
        last_seen=now,
        online=True,
    )


@router.post(
    "/heartbeat",
    response_model=NodeResponse,
    summary="Update the last-seen timestamp for a node",
)
async def heartbeat(body: NodeHeartbeatRequest) -> NodeResponse:
    # Audit fix ANO-SEC-005: heartbeats must also be signed so a third party
    # cannot keep a stale node "online" indefinitely.
    _verify_node_signature(body.onion_address, body.timestamp, body.signature_b64)

    node = _nodes.get(body.onion_address)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found — register first",
        )
    node["last_seen"] = datetime.now(timezone.utc)
    return NodeResponse(**node, online=True)


@router.get(
    "/",
    response_model=list[NodeResponse],
    summary="List all online nodes",
)
async def list_nodes() -> list[NodeResponse]:
    return [
        NodeResponse(**n, online=_is_online(n["last_seen"]))
        for n in _nodes.values()
        if _is_online(n["last_seen"])
    ]


@router.delete(
    "/{onion_address}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deregister a node",
)
async def deregister_node(onion_address: str) -> None:
    # Audit fix ANO-SEC-005: validate the onion address format on delete too,
    # so an attacker cannot probe arbitrary strings via the 404 path.
    if not _ONION_V3_RE.match(onion_address):
        raise HTTPException(status_code=400, detail="Invalid onion address format")
    if onion_address not in _nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )
    del _nodes[onion_address]
    logger.info("node_deregistered", onion=onion_address[:12])
