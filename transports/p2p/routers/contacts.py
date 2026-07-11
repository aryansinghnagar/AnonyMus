"""
Contacts router — list, add, remove contacts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.db.models import Contact, User
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/contacts", tags=["contacts"])


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
    onion_address: str
    nickname: str | None
    verified: bool

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
    contacts = await session.scalars(
        select(Contact).where(Contact.owner_onion == user.onion_address)
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
    session: AsyncSession = Depends(get_session),
) -> ContactResponse:
    user = await _get_current_user(request, session)

    existing = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == body.onion_address,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Contact already exists"
        )

    contact = Contact(
        owner_onion=user.onion_address,
        onion_address=body.onion_address,
        nickname=body.nickname,
    )
    session.add(contact)
    await session.flush()
    logger.info("contact_added", owner=user.username, peer=body.onion_address[:8])
    return ContactResponse.model_validate(contact)


@router.delete(
    "/{onion_address}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a contact",
)
async def remove_contact(
    onion_address: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> None:
    user = await _get_current_user(request, session)
    result = await session.execute(
        delete(Contact).where(
            Contact.owner_onion == user.onion_address,
            Contact.onion_address == onion_address,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found"
        )
    logger.info("contact_removed", owner=user.username, peer=onion_address[:8])
