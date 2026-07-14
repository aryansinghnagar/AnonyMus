"""
P2P router — handles incoming contact handshake, accept, message, and delete requests
sent directly from remote Tor nodes.
"""

from __future__ import annotations

import re
import uuid
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.db.models import Contact, Message, User
from core.logging_v3 import get_logger
from transports.p2p.socket_v3 import emit_socket

logger = get_logger(__name__)
router = APIRouter(prefix="/p2p", tags=["p2p"])

ONION_RE = re.compile(r"^[a-z2-7]{16,56}\.onion$")


# ── Helpers ────────────────────────────────────────────────────────────────────


def validate_onion(onion: str) -> str:
    onion = onion.strip().lower()
    if not ONION_RE.match(onion):
        raise HTTPException(status_code=400, detail="Invalid onion address")
    return onion


# ── Schemas ────────────────────────────────────────────────────────────────────


class HandshakeRequest(BaseModel):
    onion_address: str
    nickname: str = Field(max_length=64)
    public_key: str
    preferred_file_relay: str | None = None


class AcceptRequest(BaseModel):
    onion_address: str
    public_key: str
    preferred_file_relay: str | None = None


class SealedSenderBlock(BaseModel):
    ephemeral_pub: str
    ciphertext: str
    iv: str


class P2PMessageRequest(BaseModel):
    sender: str | None = None
    sealed_sender: SealedSenderBlock | None = None
    iv: str
    ciphertext: str
    seq: int = Field(ge=0)
    timestamp: int
    disappears_at: datetime | None = None
    ephemeral: bool = False


class P2PDeleteRequest(BaseModel):
    sender: str
    message_id: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/handshake", status_code=status.HTTP_200_OK)
async def p2p_handshake(
    body: HandshakeRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    onion = validate_onion(body.onion_address)

    # Get local node identity (the main user)
    user = await session.scalar(select(User).limit(1))
    if not user:
        raise HTTPException(status_code=500, detail="Local user node not configured")

    # Check if blocked
    existing = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == onion,
        )
    )
    if existing and existing.status == "blocked":
        raise HTTPException(status_code=403, detail="Blocked contact")

    if not existing:
        existing = Contact(
            owner_onion=user.onion_address,
            onion_address=onion,
            nickname=body.nickname,
            public_key_b64=body.public_key,
            status="pending_incoming",
            verified=False,
        )
        session.add(existing)
    else:
        existing.nickname = body.nickname
        existing.public_key_b64 = body.public_key
        existing.status = "pending_incoming"

    await session.commit()
    logger.info("p2p_handshake_received", onion=onion[:12], nickname=body.nickname)

    # Notify UI
    await emit_socket(
        "handshake_received",
        {
            "onion_address": onion,
            "nickname": body.nickname,
            "public_key": body.public_key,
        },
    )
    await emit_socket(
        "contact_status_change", {"onion_address": onion, "status": "pending_incoming"}
    )

    return {"status": "pending"}


@router.post("/accept", status_code=status.HTTP_200_OK)
async def p2p_accept(
    body: AcceptRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    onion = validate_onion(body.onion_address)

    # Get local node identity (the main user)
    user = await session.scalar(select(User).limit(1))
    if not user:
        raise HTTPException(status_code=500, detail="Local user node not configured")

    contact = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == onion,
        )
    )
    if not contact:
        raise HTTPException(
            status_code=404, detail="Handshake contact record not found"
        )

    contact.public_key_b64 = body.public_key
    contact.status = "accepted"
    await session.commit()

    logger.info("p2p_handshake_accepted_by_peer", onion=onion[:12])

    # Notify UI
    await emit_socket(
        "contact_status_change", {"onion_address": onion, "status": "accepted"}
    )

    return {"status": "accepted"}


@router.post("/message", status_code=status.HTTP_200_OK)
async def p2p_message(
    body: P2PMessageRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sender = validate_onion(body.sender) if body.sender else None

    # Get local node identity
    user = await session.scalar(select(User).limit(1))
    if not user:
        raise HTTPException(status_code=500, detail="Local user node not configured")

    # If sender is not resolved yet (sealed sender)
    if not sender and body.sealed_sender:
        sender = "sealed"
    elif not sender:
        raise HTTPException(status_code=400, detail="Missing sender or sealed_sender")

    # For sealed sender, we bypass immediate contact verification on receipt.
    # Contact validation is performed once the client resolves the sender identity.
    if sender != "sealed":
        contact = await session.scalar(
            select(Contact).where(
                Contact.owner_onion == user.onion_address,
                Contact.onion_address == sender,
            )
        )
        if not contact or contact.status != "accepted":
            raise HTTPException(
                status_code=403, detail="Unauthorized contact connection"
            )

        # Sequence monotonicity check
        last_seq = await session.scalar(
            select(func.max(Message.sequence_number)).where(
                Message.sender_onion == sender,
                Message.recipient_onion == user.onion_address,
            )
        )
        if last_seq is not None and body.seq <= last_seq:
            raise HTTPException(
                status_code=400, detail="Sequence number must be strictly monotonic"
            )

    # Save to local database (unless ephemeral/disappearing)
    sealed_sender_json = None
    if body.sealed_sender:
        sealed_sender_json = json.dumps(body.sealed_sender.model_dump())

    if not body.ephemeral:
        msg = Message(
            message_id=str(uuid.uuid4()),
            sender_onion=sender,
            recipient_onion=user.onion_address or "sealed_recipient",
            ciphertext_b64=body.ciphertext,
            iv_b64=body.iv,
            sequence_number=body.seq,
            sent_at=datetime.fromtimestamp(body.timestamp / 1000.0, timezone.utc),
            disappears_at=body.disappears_at,
            sealed_sender=sealed_sender_json,
        )
        session.add(msg)
        await session.commit()
        logger.info("p2p_message_received", sender=sender[:12], seq=body.seq)
    else:
        logger.info("p2p_ephemeral_message_received", sender=sender[:12])

    # Broadcast real-time message receipt event to the browser client
    message_data = {
        "message_id": str(uuid.uuid4()) if body.ephemeral else msg.message_id,
        "sender_onion": sender,
        "recipient_onion": user.onion_address,
        "ciphertext_b64": body.ciphertext,
        "iv_b64": body.iv,
        "sequence_number": body.seq,
        "sent_at": datetime.fromtimestamp(
            body.timestamp / 1000.0, timezone.utc
        ).isoformat(),
        "delivered": True,
        "is_deleted": False,
        "disappears_at": body.disappears_at.isoformat() if body.disappears_at else None,
        "sealed_sender": body.sealed_sender.model_dump()
        if body.sealed_sender
        else None,
    }
    await emit_socket(
        "message_received", {"sender_onion": sender, "message": message_data}
    )

    return {"status": "delivered"}


@router.post("/delete", status_code=status.HTTP_200_OK)
async def p2p_delete(
    body: P2PDeleteRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    sender = validate_onion(body.sender)

    # Mark as deleted locally
    msg = await session.scalar(
        select(Message).where(
            Message.message_id == body.message_id,
            Message.sender_onion == sender,
        )
    )
    if msg:
        msg.is_deleted = True
        await session.commit()
        logger.info(
            "p2p_message_delete_received", sender=sender[:12], msg_id=body.message_id
        )

        # Notify UI
        await emit_socket(
            "message_deleted", {"onion_address": sender, "message_id": body.message_id}
        )

    return {"status": "deleted"}
