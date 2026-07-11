"""
Groups router — create groups, list members, send group messages.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.db.models import Group, GroupMember, GroupMessage, User
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/groups", tags=["groups"])


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


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    member_onions: list[str] = Field(default_factory=list)
    is_channel: bool = Field(default=False)


class GroupResponse(BaseModel):
    group_id: str
    name: str
    founder_onion: str
    is_channel: bool

    model_config = {"from_attributes": True}


class SendGroupMessageRequest(BaseModel):
    ciphertext_b64: str
    group_id: str


class GroupMessageResponse(BaseModel):
    message_id: str
    group_id: str
    sender_onion: str
    ciphertext_b64: str

    model_config = {"from_attributes": True}


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new group or broadcast channel",
)
async def create_group(
    body: CreateGroupRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    user = await _get_current_user(request, session)

    if not user.onion_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Onion address not configured",
        )

    group = Group(
        group_id=str(uuid.uuid4()),
        name=body.name,
        founder_onion=user.onion_address,
        is_channel=body.is_channel,
    )
    session.add(group)
    await session.flush()

    # Add the founder and all specified members
    all_members = {user.onion_address} | set(body.member_onions)
    for onion in all_members:
        session.add(GroupMember(group_id=group.group_id, onion_address=onion))

    logger.info(
        "group_created",
        group_id=group.group_id[:8],
        name=group.name,
        is_channel=group.is_channel,
    )
    return GroupResponse.model_validate(group)


@router.get(
    "/",
    response_model=list[GroupResponse],
    summary="List groups the current user belongs to",
)
async def list_groups(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[GroupResponse]:
    user = await _get_current_user(request, session)

    memberships = await session.scalars(
        select(GroupMember).where(GroupMember.onion_address == user.onion_address)
    )
    group_ids = [m.group_id for m in memberships]

    if not group_ids:
        return []

    groups = await session.scalars(select(Group).where(Group.group_id.in_(group_ids)))
    return [GroupResponse.model_validate(g) for g in groups]


@router.post(
    "/messages",
    response_model=GroupMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message to a group",
)
async def send_group_message(
    body: SendGroupMessageRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> GroupMessageResponse:
    user = await _get_current_user(request, session)

    group = await session.scalar(select(Group).where(Group.group_id == body.group_id))
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        )

    # Broadcast channels: only the founder can post
    if group.is_channel and group.founder_onion != user.onion_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the channel founder can post to a broadcast channel",
        )

    msg = GroupMessage(
        message_id=str(uuid.uuid4()),
        group_id=body.group_id,
        sender_onion=user.onion_address,
        ciphertext_b64=body.ciphertext_b64,
    )
    session.add(msg)
    await session.flush()

    logger.info(
        "group_message_sent", group=body.group_id[:8], sender=user.onion_address[:8]
    )
    return GroupMessageResponse.model_validate(msg)
