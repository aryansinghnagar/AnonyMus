"""
Nodes router — register and deregister onion service nodes on the relay.

The relay maintains a directory of active onion addresses that clients use
to bootstrap peer discovery.  All writes are authenticated via the node's
Ed25519 identity key (signed challenge token, verified server-side).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])

# Nodes that have not sent a heartbeat in this window are considered offline.
STALE_AFTER_MINUTES = 10


# ── Schemas ────────────────────────────────────────────────────────────────────


class NodeRegisterRequest(BaseModel):
    onion_address: str = Field(min_length=16, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)
    version: str = Field(default="3.0.0", max_length=32)


class NodeHeartbeatRequest(BaseModel):
    onion_address: str = Field(min_length=16, max_length=128)


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


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=NodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new onion node on the relay directory",
)
async def register_node(body: NodeRegisterRequest) -> NodeResponse:
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
    if onion_address not in _nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )
    del _nodes[onion_address]
    logger.info("node_deregistered", onion=onion_address[:12])
