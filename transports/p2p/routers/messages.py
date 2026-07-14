"""
Messages router — send messages, fetch history, delete.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import requests
import asyncio
import json
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


def _transmit_p2p_message_sync(
    recipient_onion: str, payload: dict, retries: int = 5
) -> None:
    proxies = {
        "http": f"socks5h://127.0.0.1:{settings.tor_socks_port}",
        "https": f"socks5h://127.0.0.1:{settings.tor_socks_port}",
    }
    url = f"http://{recipient_onion.strip().lower()}/p2p/message"

    import time

    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, proxies=proxies, timeout=20)
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
            time.sleep(2**attempt)

    logger.error(
        "p2p_message_transmission_failed_permanently", recipient=recipient_onion[:12]
    )


async def transmit_p2p_message(recipient_onion: str, payload: dict) -> None:
    await asyncio.to_thread(_transmit_p2p_message_sync, recipient_onion, payload)


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
    before: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[MessageResponse]:
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

    if before:
        before_msg = await session.scalar(
            select(Message).where(Message.message_id == before)
        )
        if before_msg:
            stmt = stmt.where(Message.sent_at < before_msg.sent_at)

    stmt = stmt.order_by(Message.sent_at.desc()).limit(limit)
    messages = await session.scalars(stmt)
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
