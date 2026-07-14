"""
Contacts router — list, add, remove contacts.
"""

from __future__ import annotations

from datetime import datetime

import requests
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import settings
from core.db.engine import get_session
from core.db.models import Contact, User, PreKeyBundle
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/contacts", tags=["contacts"])


def _transmit_handshake_sync(peer_onion: str, payload: dict) -> None:
    proxies = {
        "http": f"socks5h://127.0.0.1:{settings.tor_socks_port}",
        "https": f"socks5h://127.0.0.1:{settings.tor_socks_port}",
    }
    url = f"http://{peer_onion.strip().lower()}/p2p/handshake"
    try:
        response = requests.post(url, json=payload, proxies=proxies, timeout=20)
        logger.info(
            "p2p_handshake_transmitted",
            peer=peer_onion[:12],
            status=response.status_code,
        )
    except Exception as e:
        logger.error(
            "p2p_handshake_transmission_failed", peer=peer_onion[:12], error=str(e)
        )


async def transmit_handshake(peer_onion: str, payload: dict) -> None:
    await asyncio.to_thread(_transmit_handshake_sync, peer_onion, payload)


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


class AddContactRequest(BaseModel):
    onion_address: str = Field(min_length=16, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)


class ContactResponse(BaseModel):
    id: int
    owner_onion: str
    onion_address: str
    nickname: str | None = None
    verified: bool
    added_at: datetime
    public_key_b64: str | None = None
    shared_secret_b64: str | None = None
    status: str

    model_config = {"from_attributes": True}


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=list[ContactResponse],
    summary="List all contacts for the current user",
)
async def list_contacts(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[ContactResponse]:
    user = await _get_current_user(request, session)
    profile_id = request.session.get("active_profile_id", "default")
    contacts = await session.scalars(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.profile_id == profile_id,
        )
    )
    return [ContactResponse.model_validate(c) for c in contacts]


@router.post(
    "/",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new contact",
)
async def add_contact(
    body: AddContactRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ContactResponse:
    user = await _get_current_user(request, session)
    profile_id = request.session.get("active_profile_id", "default")

    existing = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == body.onion_address,
            Contact.profile_id == profile_id,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Contact already exists"
        )

    # Load user's own identity key
    bundle = await session.scalar(
        select(PreKeyBundle).where(PreKeyBundle.onion_address == user.onion_address)
    )
    my_pub_key = bundle.identity_key if bundle else "bootstrap_key_placeholder"

    contact = Contact(
        owner_onion=user.onion_address,
        onion_address=body.onion_address,
        nickname=body.nickname,
        status="pending_outgoing",
        verified=False,
        profile_id=profile_id,
    )
    session.add(contact)
    await session.flush()

    # Queue background handshake POST over Tor
    payload = {
        "onion_address": user.onion_address,
        "nickname": user.username,
        "public_key": my_pub_key,
    }
    background_tasks.add_task(transmit_handshake, body.onion_address, payload)

    logger.info(
        "contact_added_and_handshake_queued",
        owner=user.username,
        peer=body.onion_address[:8],
    )
    return ContactResponse.model_validate(contact)


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a contact",
)
async def remove_contact(
    contact_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> None:
    user = await _get_current_user(request, session)
    result = await session.execute(
        delete(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.id == contact_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found"
        )
    logger.info("contact_removed", owner=user.username, contact_id=contact_id)
