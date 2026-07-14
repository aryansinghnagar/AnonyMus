"""
Supporter router — handles supporter badge verification and lookup.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.crypto import verify_supporter_badge, DEVELOPER_PUBLIC_KEY_B64
from core.db.engine import get_session
from core.db.models import SupporterBadge, User
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/profile/supporter_badge", tags=["supporter"])


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _verify_auth(request: Request, session: AsyncSession) -> None:
    username = request.session.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    user = await session.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )


# ── Schemas ────────────────────────────────────────────────────────────────────


class SupporterBadgeRequest(BaseModel):
    onion_address: str = Field(min_length=16, max_length=128)
    signature: str = Field(min_length=1)


class SupporterStatusResponse(BaseModel):
    is_supporter: bool
    badge_signature: str | None = None


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/", response_model=dict, summary="Verify and save a supporter badge")
async def verify_badge(
    body: SupporterBadgeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _verify_auth(request, session)

    onion_address = body.onion_address.strip().lower()
    signature = body.signature.strip()

    is_valid = verify_supporter_badge(onion_address, signature)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid supporter signature.",
        )

    # Save to database
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
    logger.info("supporter_badge_verified_and_saved", onion=onion_address[:12])
    return {"success": True}


@router.get(
    "/status",
    response_model=SupporterStatusResponse,
    summary="Get supporter status of onion address",
)
async def get_badge_status(
    onion_address: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> SupporterStatusResponse:
    await _verify_auth(request, session)

    onion = onion_address.strip().lower()
    badge = await session.scalar(
        select(SupporterBadge).where(SupporterBadge.onion_address == onion)
    )
    if badge:
        return SupporterStatusResponse(
            is_supporter=True, badge_signature=badge.badge_signature
        )
    return SupporterStatusResponse(is_supporter=False)
