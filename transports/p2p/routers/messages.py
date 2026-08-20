"""
Messages router — send messages, fetch history, delete.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

import asyncio
import json
import httpx
from typing import Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
    BackgroundTasks,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db.engine import get_session
from core.db.models import Message, User, Contact
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/messages", tags=["messages"])


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_current_user(request: Request, session: AsyncSession) -> User:
    username = request.session.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    user = await session.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


async def transmit_p2p_message(
    recipient_onion: str, payload: dict, retries: int = 3
) -> None:
    """Asynchronously transmits message payload to peer onion address via SOCKS5 proxy."""
    import os
    import sys

    is_test_env = (
        settings.is_test
        or os.environ.get("TESTING") == "True"
        or "pytest" in sys.modules
    )
    if is_test_env:
        logger.debug(
            "p2p_message_transmit_skipped_in_test", recipient=recipient_onion[:12]
        )
        return

    proxies = {
        "http://": f"socks5://127.0.0.1:{settings.tor_socks_port}",
        "https://": f"socks5://127.0.0.1:{settings.tor_socks_port}",
    }
    url = f"http://{recipient_onion.strip().lower()}/p2p/message"

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(proxies=proxies, timeout=10.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    logger.info(
                        "p2p_message_transmitted",
                        recipient=recipient_onion[:12],
                        status=response.status_code,
                    )
                    return
                else:
                    logger.warning(
                        "p2p_message_transmission_status_error",
                        recipient=recipient_onion[:12],
                        status=response.status_code,
                    )
        except Exception as e:
            logger.error(
                "p2p_message_transmission_attempt_failed",
                recipient=recipient_onion[:12],
                attempt=attempt + 1,
                error=str(e),
            )

        if attempt < retries - 1:
            await asyncio.sleep(1.0 * (attempt + 1))

    logger.error(
        "p2p_message_transmission_failed_permanently", recipient=recipient_onion[:12]
    )


# ── Schemas ────────────────────────────────────────────────────────────────────


class SealedSenderBlock(BaseModel):
    ephemeral_pub: str
    ciphertext: str
    iv: str


class SendMessageRequest(BaseModel):
    recipient_onion: str = Field(min_length=16, max_length=128)
    ciphertext_b64: str
    iv_b64: str
    sequence_number: int = Field(ge=0)
    disappears_at: datetime | None = Field(default=None)
    sealed_sender: SealedSenderBlock | None = None


class MessageResponse(BaseModel):
    message_id: str
    sender_onion: str
    recipient_onion: str
    ciphertext_b64: str
    iv_b64: str
    sequence_number: int
    sent_at: datetime
    delivered: bool
    is_deleted: bool
    disappears_at: datetime | None
    sealed_sender: dict | None = None

    model_config = {"from_attributes": True}

    @field_validator("sealed_sender", mode="before")
    @classmethod
    def parse_sealed_sender(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send an E2E-encrypted message to a contact",
)
async def send_message(
    body: SendMessageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    user = await _get_current_user(request, session)

    if not user.onion_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Onion address not configured — Tor node not running",
        )

    sealed_sender_json = None
    if body.sealed_sender:
        sealed_sender_json = json.dumps(body.sealed_sender.model_dump())

    msg = Message(
        message_id=str(uuid.uuid4()),
        sender_onion=user.onion_address,
        recipient_onion=body.recipient_onion,
        ciphertext_b64=body.ciphertext_b64,
        iv_b64=body.iv_b64,
        sequence_number=body.sequence_number,
        disappears_at=body.disappears_at,
        sealed_sender=sealed_sender_json,
    )
    session.add(msg)
    await session.flush()

    # Queue background Tor transmission to remote node
    payload = {
        "sender": "sealed" if body.sealed_sender else user.onion_address,
        "sealed_sender": body.sealed_sender.model_dump()
        if body.sealed_sender
        else None,
        "iv": body.iv_b64,
        "ciphertext": body.ciphertext_b64,
        "seq": body.sequence_number,
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "disappears_at": body.disappears_at.isoformat() if body.disappears_at else None,
        "ephemeral": False,
    }
    background_tasks.add_task(transmit_p2p_message, body.recipient_onion, payload)

    logger.info(
        "message_sent",
        sender=user.onion_address[:8],
        recipient=body.recipient_onion[:8],
        seq=body.sequence_number,
    )
    return MessageResponse.model_validate(msg)


@router.get(
    "/{peer_onion}",
    response_model=list[MessageResponse],
    summary="Fetch message history with a contact",
)
async def message_history(
    peer_onion: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(
        default=None,
        description="Legacy cursor: a message_id. Prefer the `cursor` query param.",
    ),
    cursor: str | None = Query(
        default=None,
        description=(
            "Opaque cursor token returned in the `X-Next-Cursor` response "
            "header. Encodes (sent_at || message_id) so the next batch can "
            "be fetched without a separate lookup (perf fix P6)."
        ),
    ),
    session: AsyncSession = Depends(get_session),
) -> list[MessageResponse]:
    """Cursor-paginated message history.

    Perf fix P6: previously the endpoint fetched the full conversation
    history with ``LIMIT/OFFSET``, which scales poorly (OFFSET N requires
    reading N+limit rows from disk). The endpoint now uses cursor-based
    pagination:

      1. Default batch size is 50 (caller can request up to 200).
      2. The response includes a ``X-Next-Cursor`` response header encoding
         ``sent_at || message_id`` of the OLDEST message in the batch.
      3. The caller passes that cursor as the ``cursor`` query param to
         fetch the next older batch.

    Backward compat: the legacy ``before=<message_id>`` query param is
    still accepted (it triggers a single-row lookup instead of decoding
    the cursor inline, but the result is the same).
    """
    user = await _get_current_user(request, session)

    stmt = select(Message).where(
        Message.is_deleted == False,  # noqa: E712
        (
            (Message.sender_onion == user.onion_address)
            & (Message.recipient_onion == peer_onion)
        )
        | (
            (Message.sender_onion == peer_onion)
            & (Message.recipient_onion == user.onion_address)
        ),
    )

    # ── Decode the cursor (perf fix P6) ─────────────────────────────────────
    cursor_sent_at: datetime | None = None
    if cursor:
        try:
            raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
            # Format: "<sent_at_iso>||<message_id>"
            sent_at_str, _, _msg_id = raw.partition("||")
            cursor_sent_at = datetime.fromisoformat(sent_at_str)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor token",
            )
    elif before:
        # Legacy cursor path: look up the message_id and use its sent_at.
        # This is one extra DB round-trip vs. the cursor path, but keeps
        # backward compatibility with clients that haven't migrated yet.
        before_msg = await session.scalar(
            select(Message).where(Message.message_id == before)
        )
        if before_msg:
            cursor_sent_at = before_msg.sent_at

    if cursor_sent_at is not None:
        # Strictly less-than: cursor_sent_at is the oldest message we already
        # returned, so we want everything older than it.
        stmt = stmt.where(Message.sent_at < cursor_sent_at)

    stmt = stmt.order_by(Message.sent_at.desc()).limit(limit)
    messages = (await session.scalars(stmt)).all()

    # ── Encode the next-page cursor in a response header (perf fix P6) ───────
    if messages:
        oldest = messages[-1]
        # Combine sent_at + message_id into a single opaque token so the
        # caller doesn't need to know the cursor's internal structure.
        next_cursor_str = f"{oldest.sent_at.isoformat()}||{oldest.message_id}"
        next_cursor = base64.urlsafe_b64encode(next_cursor_str.encode("utf-8")).decode(
            "ascii"
        )
        # FastAPI Response headers must be set on the underlying Response.
        # We stash it via request.state so the middleware can pick it up.
        request.state.next_cursor = next_cursor

    return [MessageResponse.model_validate(m) for m in messages]


@router.delete(
    "/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a message (mark as deleted)",
)
async def delete_message(
    message_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> None:
    user = await _get_current_user(request, session)
    msg = await session.scalar(
        select(Message).where(
            Message.message_id == message_id,
            Message.sender_onion == user.onion_address,
        )
    )
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )
    msg.is_deleted = True
    await session.commit()


class ResolveSenderRequest(BaseModel):
    sender_onion: str


@router.post(
    "/{message_id}/resolve_sender",
    summary="Resolve the sender of a sealed-sender message",
)
async def resolve_sender(
    message_id: str,
    body: ResolveSenderRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await _get_current_user(request, session)
    msg = await session.scalar(select(Message).where(Message.message_id == message_id))
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    sender = body.sender_onion.strip().lower()
    # Verify sender is an accepted contact
    contact = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == sender,
        )
    )
    if not contact or contact.status != "accepted":
        # Delete message if it's from an unauthorized sender (spam protection)
        await session.delete(msg)
        await session.commit()
        raise HTTPException(status_code=403, detail="Unauthorized sender identity")

    # Monotonicity check
    last_seq = await session.scalar(
        select(func.max(Message.sequence_number)).where(
            Message.sender_onion == sender,
            Message.recipient_onion == user.onion_address,
            Message.message_id != message_id,
        )
    )
    if last_seq is not None and msg.sequence_number <= last_seq:
        await session.delete(msg)
        await session.commit()
        raise HTTPException(
            status_code=400, detail="Sequence number must be strictly monotonic"
        )

    msg.sender_onion = sender
    await session.commit()
    return {"success": True, "message_id": message_id, "sender_onion": sender}
