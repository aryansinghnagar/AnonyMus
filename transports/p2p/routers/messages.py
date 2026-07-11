"""
Messages router — send messages, fetch history, delete.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.db.models import Message, User
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/messages", tags=["messages"])


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


# ── Schemas ────────────────────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    recipient_onion: str = Field(min_length=16, max_length=128)
    ciphertext_b64: str
    iv_b64: str
    sequence_number: int = Field(ge=0)
    disappears_in_seconds: int | None = Field(default=None, ge=0)


class MessageResponse(BaseModel):
    message_id: str
    sender_onion: str
    recipient_onion: str
    ciphertext_b64: str
    iv_b64: str
    sequence_number: int
    sent_at: datetime
    delivered: bool

    model_config = {"from_attributes": True}


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/send",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send an E2E-encrypted message to a contact",
)
async def send_message(
    body: SendMessageRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    user = await _get_current_user(request, session)

    if not user.onion_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Onion address not configured — Tor node not running",
        )

    disappears_at = None
    if body.disappears_in_seconds is not None:
        from datetime import timedelta

        disappears_at = datetime.now(timezone.utc) + timedelta(
            seconds=body.disappears_in_seconds
        )

    msg = Message(
        message_id=str(uuid.uuid4()),
        sender_onion=user.onion_address,
        recipient_onion=body.recipient_onion,
        ciphertext_b64=body.ciphertext_b64,
        iv_b64=body.iv_b64,
        sequence_number=body.sequence_number,
        disappears_at=disappears_at,
    )
    session.add(msg)
    await session.flush()

    logger.info(
        "message_sent",
        sender=user.onion_address[:8],
        recipient=body.recipient_onion[:8],
        seq=body.sequence_number,
    )
    return MessageResponse.model_validate(msg)


@router.get(
    "/history/{peer_onion}",
    response_model=list[MessageResponse],
    summary="Fetch message history with a contact",
)
async def message_history(
    peer_onion: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[MessageResponse]:
    user = await _get_current_user(request, session)

    stmt = (
        select(Message)
        .where(
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
        .order_by(Message.sent_at.desc())
        .limit(limit)
    )
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
