"""
Profiles router — list profiles, create decoy profiles, unlock and switch profiles.
"""

from __future__ import annotations

import uuid
import bcrypt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.db.models import Profile, User
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/profiles", tags=["profiles"])


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _verify_auth(request: Request, session: AsyncSession) -> None:
    username = request.session.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    # Check if user exists
    user = await session.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )


# ── Schemas ────────────────────────────────────────────────────────────────────


class ProfileResponse(BaseModel):
    profile_id: str
    display_name: str
    hidden: bool

    model_config = {"from_attributes": True}


class CreateProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    hidden: bool = False
    passphrase: str | None = Field(default=None, max_length=256)


class UnlockProfileRequest(BaseModel):
    passphrase: str = Field(min_length=1)


class SwitchProfileRequest(BaseModel):
    profile_id: str = Field(min_length=1)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get(
    "/", response_model=list[ProfileResponse], summary="List all non-hidden profiles"
)
async def list_profiles(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[ProfileResponse]:
    await _verify_auth(request, session)

    profiles = await session.scalars(select(Profile).where(Profile.hidden == False))  # noqa: E712
    return [ProfileResponse.model_validate(p) for p in profiles]


@router.post("/create", response_model=dict, summary="Create a new profile")
async def create_profile(
    body: CreateProfileRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _verify_auth(request, session)

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
        hidden=body.hidden,
        passphrase_hash=passphrase_hash,
    )
    session.add(profile)
    await session.commit()

    logger.info("profile_created", profile_id=profile_id, hidden=body.hidden)
    return {"success": True, "profile_id": profile_id}


@router.post("/unlock", response_model=dict, summary="Unlock a hidden decoy profile")
async def unlock_profile(
    body: UnlockProfileRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _verify_auth(request, session)

    # Fetch hidden profiles
    profiles = await session.scalars(select(Profile).where(Profile.hidden == True))  # noqa: E712

    matched_profile = None
    for p in profiles:
        if p.passphrase_hash:
            # Verify passphrase hash
            if bcrypt.checkpw(
                body.passphrase.encode("utf-8"), p.passphrase_hash.encode("utf-8")
            ):
                matched_profile = p
                break

    if not matched_profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    # Store in session
    request.session["active_profile_id"] = matched_profile.profile_id
    logger.info("profile_unlocked", profile_id=matched_profile.profile_id)
    return {
        "success": True,
        "profile": {
            "profile_id": matched_profile.profile_id,
            "display_name": matched_profile.display_name,
            "hidden": True,
        },
    }


@router.post("/switch", response_model=dict, summary="Switch active profile")
async def switch_profile(
    body: SwitchProfileRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _verify_auth(request, session)

    profile = await session.scalar(
        select(Profile).where(Profile.profile_id == body.profile_id)
    )

    # Hidden profiles cannot be switched to directly without unlock/passphrase verification
    if not profile or profile.hidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized or profile not found",
        )

    request.session["active_profile_id"] = body.profile_id
    logger.info("profile_switched", profile_id=body.profile_id)
    return {"success": True, "profile_id": body.profile_id}


@router.get("/active", response_model=ProfileResponse, summary="Get active profile")
async def active_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    await _verify_auth(request, session)

    profile_id = request.session.get("active_profile_id", "default")
    profile = await session.scalar(
        select(Profile).where(Profile.profile_id == profile_id)
    )
    if not profile:
        # Fallback to default profile if current profile not found
        profile = await session.scalar(
            select(Profile).where(Profile.profile_id == "default")
        )
        if not profile:
            # Create default profile on the fly if it is missing
            profile = Profile(
                profile_id="default", display_name="Default Profile", hidden=False
            )
            session.add(profile)
            await session.commit()

    return ProfileResponse.model_validate(profile)
