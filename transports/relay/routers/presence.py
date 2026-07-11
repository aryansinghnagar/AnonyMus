"""
Presence router — publish and subscribe to peer presence (online/typing/offline).

Presence events are fan-out via Server-Sent Events (SSE) so the web client
can show real-time status without a WebSocket connection.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/presence", tags=["presence"])

# ── In-process presence state ─────────────────────────────────────────────────

# onion_address → last status
_presence: dict[str, dict] = {}

# onion_address → set of asyncio Queues (one per SSE subscriber)
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


# ── Schemas ───────────────────────────────────────────────────────────────────


class PresenceUpdateRequest(BaseModel):
    onion_address: str = Field(min_length=16, max_length=128)
    status: str = Field(pattern="^(online|offline|typing)$")


class PresenceResponse(BaseModel):
    onion_address: str
    status: str
    updated_at: datetime


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/update",
    response_model=PresenceResponse,
    summary="Publish a presence update for a node",
)
async def update_presence(body: PresenceUpdateRequest) -> PresenceResponse:
    now = datetime.now(timezone.utc)
    record = {
        "onion_address": body.onion_address,
        "status": body.status,
        "updated_at": now,
    }
    _presence[body.onion_address] = record

    # Fan-out to all SSE subscribers for this address
    event = f"data: {body.status}\n\n"
    dead: set[asyncio.Queue] = set()
    for q in _subscribers.get(body.onion_address, set()):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.add(q)
    _subscribers[body.onion_address] -= dead

    logger.info("presence_updated", onion=body.onion_address[:12], status=body.status)
    return PresenceResponse(**record)


@router.get(
    "/{onion_address}",
    response_model=PresenceResponse,
    summary="Get the current presence status of a node",
)
async def get_presence(onion_address: str) -> PresenceResponse:
    from fastapi import HTTPException, status as http_status

    record = _presence.get(onion_address)
    if not record:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Presence record not found",
        )
    return PresenceResponse(**record)


@router.get(
    "/{onion_address}/stream",
    summary="SSE stream: receive real-time presence updates for a node",
)
async def stream_presence(onion_address: str, request: Request) -> StreamingResponse:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
    _subscribers[onion_address].add(queue)

    async def _event_generator() -> AsyncIterator[str]:
        try:
            # Send current status immediately as the first event
            record = _presence.get(onion_address)
            if record:
                yield f"data: {record['status']}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield event
                except asyncio.TimeoutError:
                    # Send a keepalive comment
                    yield ": keepalive\n\n"
        finally:
            _subscribers[onion_address].discard(queue)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering for SSE
        },
    )
