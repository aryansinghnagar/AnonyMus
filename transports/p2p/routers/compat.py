"""
Legacy Compatibility Router.
Routes deprecated /api/* and /login endpoints to FastAPI and WAL database operations.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import requests
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db.engine import get_session
from core.db.models import (
    User,
    Contact,
    Message,
    Group,
    GroupMember,
    GroupMessage,
    Profile,
    SupporterBadge,
)
from core.crypto import verify_supporter_badge, DEVELOPER_PUBLIC_KEY_B64
from core.logging_v3 import get_logger


from transports.p2p.routers import sync

logger = get_logger(__name__)
router = APIRouter(tags=["compatibility"])


# ── Helpers ────────────────────────────────────────────────────────────────────


def _verify_auth(request: Request) -> str:
    username = request.session.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    return username


def get_db_path() -> str:
    db_url = settings.database_url
    path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    return os.path.abspath(path)


# ── Schemas & Models ───────────────────────────────────────────────────────────


class LegacyLoginRequest(BaseModel):
    username: str
    password: str


class LegacyAddContactRequest(BaseModel):
    onion_address: str
    nickname: str


class LegacySendMessageRequest(BaseModel):
    recipient_onion: str
    ciphertext_b64: str = Field(alias="ciphertext")
    iv_b64: str = Field(alias="iv")
    sequence_number: int = Field(alias="seq")


class LegacyCreateGroupRequest(BaseModel):
    name: str
    founder_onion: str
    is_channel: int = 0
    member_onions: list[str] = []


class LegacySaveGroupMessageRequest(BaseModel):
    group_id: str
    sender_onion: str
    sender_nickname: str
    message: str  # This corresponds to ciphertext_b64 in our GroupMessage model
    timestamp: int


class LegacySaveSecretRequest(BaseModel):
    onion_address: str
    shared_secret: str
    peer_public_key: str
    dr_state: str | None = None
    peer_kem_public_key: str | None = None
    my_kem_private_key: str | None = None


class LegacyAcceptContactRequest(BaseModel):
    onion_address: str
    my_public_key: str
    shared_secret: str


class LegacyDeleteContactRequest(BaseModel):
    onion_address: str


class LegacySupporterBadgeRequest(BaseModel):
    onion_address: str
    signature: str


class LegacyCreateProfileRequest(BaseModel):
    display_name: str
    hidden: int = 0
    passphrase: str = ""


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/login")
async def legacy_login(
    body: LegacyLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = await session.scalar(
        select(User).where(User.username == body.username.lower())
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # bcrypt check
    is_valid = bcrypt.checkpw(
        body.password.encode("utf-8"), user.password_hash.encode("utf-8")
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    request.session["username"] = user.username
    request.session["active_profile_id"] = "default"
    return {"success": True}


@router.get("/api/contacts")
async def legacy_get_contacts(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    profile_id = request.session.get("active_profile_id", "default")
    contacts = await session.scalars(
        select(Contact).where(Contact.profile_id == profile_id)
    )

    res = []
    for c in contacts:
        res.append(
            {
                "onion_address": c.onion_address,
                "nickname": c.nickname,
                "status": c.status,
                "verified": c.verified,
                "send_receipts": 1 if c.send_receipts else 0,
                "preferred_file_relay": c.preferred_file_relay or "",
            }
        )
    return res


@router.post("/api/contacts/add")
async def legacy_add_contact(
    body: LegacyAddContactRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    username = _verify_auth(request)
    user = await session.scalar(select(User).where(User.username == username))
    profile_id = request.session.get("active_profile_id", "default")

    existing = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == body.onion_address.strip().lower(),
            Contact.profile_id == profile_id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Contact already exists")

    contact = Contact(
        owner_onion=user.onion_address,
        onion_address=body.onion_address.strip().lower(),
        nickname=body.nickname,
        status="pending_outgoing",
        verified=False,
        profile_id=profile_id,
    )
    session.add(contact)
    await session.commit()
    return {"success": True}


@router.post("/api/contacts/update_receipts")
async def legacy_update_receipts(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    data = await request.json()
    onion = data.get("onion_address", "").strip().lower()
    send_receipts = bool(data.get("send_receipts"))

    profile_id = request.session.get("active_profile_id", "default")
    contact = await session.scalar(
        select(Contact).where(
            Contact.onion_address == onion,
            Contact.profile_id == profile_id,
        )
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    contact.send_receipts = send_receipts
    await session.commit()
    return {"success": True}


@router.post("/api/messages/send")
async def legacy_send_message(
    body: LegacySendMessageRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    username = _verify_auth(request)
    user = await session.scalar(select(User).where(User.username == username))

    msg = Message(
        message_id=str(uuid.uuid4()),
        sender_onion=user.onion_address,
        recipient_onion=body.recipient_onion,
        ciphertext_b64=body.ciphertext_b64,
        iv_b64=body.iv_b64,
        sequence_number=body.sequence_number,
    )
    session.add(msg)
    await session.commit()
    return {"success": True, "message_id": msg.message_id}


@router.get("/api/messages")
async def legacy_get_messages(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    peer_onion = request.query_params.get("onion_address")
    if not peer_onion:
        raise HTTPException(status_code=400, detail="Missing onion_address")

    peer = peer_onion.strip().lower()
    messages = await session.scalars(
        select(Message)
        .where((Message.sender_onion == peer) | (Message.recipient_onion == peer))
        .order_by(Message.sent_at.asc())
    )

    res = []
    for m in messages:
        res.append(
            {
                "message_id": m.message_id,
                "sender": m.sender_onion,
                "recipient": m.recipient_onion,
                "ciphertext": m.ciphertext_b64,
                "iv": m.iv_b64,
                "seq": m.sequence_number,
                "timestamp": int(m.sent_at.timestamp() * 1000),
            }
        )
    return res


@router.get("/api/settings/preferred_relay")
async def legacy_get_preferred_relay(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    # Return preferred_file_relay setting (or default empty)
    username = request.session.get("username")
    user = await session.scalar(select(User).where(User.username == username))
    return {"preferred_file_relay": user.preferred_file_relay or ""}


@router.post("/api/settings/preferred_relay")
async def legacy_set_preferred_relay(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    data = await request.json()
    val = data.get("preferred_file_relay", "").strip()

    username = request.session.get("username")
    user = await session.scalar(select(User).where(User.username == username))
    user.preferred_file_relay = val
    await session.commit()
    return {"success": True}


@router.post("/api/sync/pair")
async def legacy_sync_pair(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    # Delegate directly to our FastAPI sync logic
    return await sync.sync_pair(request, session)


@router.post("/api/sync/push")
async def legacy_sync_push(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    data = await request.json()
    from transports.p2p.routers.sync import PushSyncRequest

    body = PushSyncRequest(ip=data.get("ip"), port=data.get("port"), k=data.get("k"))
    return await sync.sync_push(body, request, session)


@router.post("/api/groups/create")
async def legacy_create_group(
    body: LegacyCreateGroupRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    profile_id = request.session.get("active_profile_id", "default")
    group_id = str(uuid.uuid4())

    group = Group(
        group_id=group_id,
        name=body.name,
        founder_onion=body.founder_onion,
        is_channel=bool(body.is_channel),
        profile_id=profile_id,
    )
    session.add(group)
    await session.flush()

    # Add members
    all_members = {body.founder_onion} | set(body.member_onions)
    for onion in all_members:
        session.add(GroupMember(group_id=group_id, onion_address=onion))

    await session.commit()
    return {"success": True, "group_id": group_id}


@router.post("/api/groups/save_message")
async def legacy_save_group_message(
    body: LegacySaveGroupMessageRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)

    # Check if broadcast channel & requester is founder
    group = await session.scalar(select(Group).where(Group.group_id == body.group_id))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group.is_channel and group.founder_onion != body.sender_onion:
        raise HTTPException(status_code=403, detail="Forbidden")

    msg = GroupMessage(
        message_id=str(uuid.uuid4()),
        group_id=body.group_id,
        sender_onion=body.sender_onion,
        ciphertext_b64=body.message,
    )
    session.add(msg)
    await session.commit()
    return {"success": True}


@router.get("/api/profiles")
async def legacy_profiles_list(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    profiles = await session.scalars(select(Profile).where(Profile.hidden == False))  # noqa: E712
    return [
        {"profile_id": p.profile_id, "display_name": p.display_name, "hidden": 0}
        for p in profiles
    ]


@router.post("/api/profiles/create")
async def legacy_create_profile(
    body: LegacyCreateProfileRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)

    profile_id = str(uuid.uuid4())
    passphrase_hash = None
    if body.hidden and body.passphrase:
        salt = bcrypt.gensalt()
        passphrase_hash = bcrypt.hashpw(body.passphrase.encode("utf-8"), salt).decode(
            "utf-8"
        )

    profile = Profile(
        profile_id=profile_id,
        display_name=body.display_name,
        hidden=bool(body.hidden),
        passphrase_hash=passphrase_hash,
    )
    session.add(profile)
    await session.commit()
    return {"success": True, "profile_id": profile_id}


@router.post("/api/profiles/unlock")
async def legacy_unlock_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    data = await request.json()
    passphrase = data.get("passphrase", "")

    profiles = await session.scalars(select(Profile).where(Profile.hidden == True))  # noqa: E712
    matched = None
    for p in profiles:
        if p.passphrase_hash and bcrypt.checkpw(
            passphrase.encode("utf-8"), p.passphrase_hash.encode("utf-8")
        ):
            matched = p
            break

    if not matched:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    request.session["active_profile_id"] = matched.profile_id
    return {
        "success": True,
        "profile": {
            "profile_id": matched.profile_id,
            "display_name": matched.display_name,
            "hidden": 1,
        },
    }


@router.post("/api/profiles/switch")
async def legacy_switch_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    data = await request.json()
    profile_id = data.get("profile_id", "default")

    profile = await session.scalar(
        select(Profile).where(Profile.profile_id == profile_id)
    )
    if not profile or profile.hidden:
        raise HTTPException(status_code=403, detail="Unauthorized or profile not found")

    request.session["active_profile_id"] = profile_id
    return {"success": True, "profile_id": profile_id}


@router.get("/api/profiles/active")
async def legacy_active_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    profile_id = request.session.get("active_profile_id", "default")
    profile = await session.scalar(
        select(Profile).where(Profile.profile_id == profile_id)
    )
    if not profile:
        profile = Profile(
            profile_id="default", display_name="Default Profile", hidden=False
        )
        session.add(profile)
        await session.commit()

    return {
        "profile_id": profile.profile_id,
        "display_name": profile.display_name,
        "hidden": 1 if profile.hidden else 0,
    }


@router.post("/api/profile/supporter_badge")
async def legacy_supporter_badge(
    body: LegacySupporterBadgeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    onion_address = body.onion_address.strip().lower()
    signature = body.signature.strip()

    is_valid = verify_supporter_badge(onion_address, signature)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid supporter signature.")

    existing = await session.scalar(
        select(SupporterBadge).where(SupporterBadge.onion_address == onion_address)
    )
    if not existing:
        badge = SupporterBadge(
            onion_address=onion_address,
            badge_signature=signature,
            signed_by_key=DEVELOPER_PUBLIC_KEY_B64,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(badge)
    else:
        existing.badge_signature = signature
        existing.signed_by_key = DEVELOPER_PUBLIC_KEY_B64
        existing.timestamp = datetime.now(timezone.utc)

    await session.commit()
    return {"success": True}


@router.get("/api/profile/supporter_badge/status")
async def legacy_supporter_badge_status(
    onion_address: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    onion = onion_address.strip().lower()
    badge = await session.scalar(
        select(SupporterBadge).where(SupporterBadge.onion_address == onion)
    )
    if badge:
        return {"is_supporter": True, "badge_signature": badge.badge_signature}
    return {"is_supporter": False}


@router.get("/api/my_info")
async def legacy_my_info(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    username = _verify_auth(request)
    user = await session.scalar(select(User).where(User.username == username))
    return {
        "onion_address": user.onion_address if user else None,
        "local_username": username,
    }


@router.post("/api/contacts/save_secret")
async def legacy_save_secret(
    body: LegacySaveSecretRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _verify_auth(request)
    profile_id = request.session.get("active_profile_id", "default")
    contact = await session.scalar(
        select(Contact).where(
            Contact.onion_address == body.onion_address.strip().lower(),
            Contact.profile_id == profile_id,
        )
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    contact.shared_secret_b64 = body.shared_secret
    contact.public_key_b64 = body.peer_public_key
    if body.dr_state:
        contact.dr_state = body.dr_state
    if body.peer_kem_public_key:
        contact.peer_kem_public_key = body.peer_kem_public_key
    if body.my_kem_private_key:
        contact.my_kem_private_key = body.my_kem_private_key
    contact.status = "accepted"
    await session.commit()
    return {"success": True}


@router.post("/api/contacts/accept")
async def legacy_accept_contact(
    body: LegacyAcceptContactRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    username = _verify_auth(request)
    user = await session.scalar(select(User).where(User.username == username))
    profile_id = request.session.get("active_profile_id", "default")

    contact = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == body.onion_address.strip().lower(),
            Contact.profile_id == profile_id,
        )
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    contact.shared_secret_b64 = body.shared_secret
    contact.status = "accepted"
    await session.commit()

    # Notify peer over Tor
    payload = {
        "onion_address": user.onion_address,
        "public_key": body.my_public_key,
    }

    def do_post():
        proxies = {
            "http": f"socks5h://127.0.0.1:{settings.tor_socks_port}",
            "https": f"socks5h://127.0.0.1:{settings.tor_socks_port}",
        }
        try:
            requests.post(
                f"http://{body.onion_address.strip().lower()}/p2p/accept",
                json=payload,
                proxies=proxies,
                timeout=20,
            )
        except Exception as e:
            logger.error("legacy_accept_notification_failed", error=str(e))

    import asyncio

    asyncio.create_task(asyncio.to_thread(do_post))
    return {"success": True}


@router.post("/api/contacts/delete")
async def legacy_delete_contact(
    body: LegacyDeleteContactRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    username = _verify_auth(request)
    user = await session.scalar(select(User).where(User.username == username))
    profile_id = request.session.get("active_profile_id", "default")

    contact = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == body.onion_address.strip().lower(),
            Contact.profile_id == profile_id,
        )
    )
    if contact:
        await session.delete(contact)
        await session.commit()
    return {"success": True}
