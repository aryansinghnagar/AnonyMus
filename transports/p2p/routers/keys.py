"""
Keys router — pre-key bundle publish, rotate, and fetch.

This router bridges the Python backend to the anonymus-core Rust crate for
all key-agreement operations. In Phase 5 the relay stores these bundles
in the encrypted SQLite DB.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.db.models import PreKeyBundle, User
from core.logging_v3 import get_logger
from transports.p2p.routers.auth import get_current_user, UserOut

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/keys", tags=["keys"])

ONION_RE = re.compile(r"^[a-z2-7]{16,56}\.onion$")


# ── Schemas ────────────────────────────────────────────────────────────────────


class PreKeyBundlePublish(BaseModel):
    """All fields are base64url-encoded bytes from the anonymus-core WASM/PyO3 output."""

    onion_address: str = Field(min_length=16, max_length=128)
    identity_key: str = Field(description="Ed25519 identity key (base64url, 32 bytes)")
    signed_prekey: str = Field(
        description="X25519 signed pre-key (base64url, 32 bytes)"
    )
    signed_prekey_sig: str = Field(
        description="Ed25519 signature over signed_prekey (base64url, 64 bytes)"
    )
    pq_prekey: str = Field(
        description="ML-KEM-768 encapsulation key (base64url, 1184 bytes)"
    )
    pq_prekey_sig: str = Field(
        description="Ed25519 signature over pq_prekey (base64url, 64 bytes)"
    )
    one_time_prekeys: list[str] = Field(
        description="Pool of one-time X25519 pre-keys (base64url, each 32 bytes)",
        max_length=100,
    )
    one_time_pq_prekeys: list[str] = Field(
        description="Pool of one-time ML-KEM-768 keys (base64url, each 1184 bytes)",
        max_length=100,
    )


class PreKeyBundleResponse(BaseModel):
    onion_address: str
    identity_key: str
    signed_prekey: str
    signed_prekey_sig: str
    pq_prekey: str
    pq_prekey_sig: str
    one_time_prekey: str | None
    one_time_pq_prekey: str | None
    published_at: datetime
    opk_pool_size: int


class RotateSignedPreKeyRequest(BaseModel):
    onion_address: str = Field(min_length=16, max_length=128)
    signed_prekey: str
    signed_prekey_sig: str
    pq_prekey: str
    pq_prekey_sig: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/publish",
    status_code=status.HTTP_201_CREATED,
    summary="Publish my pre-key bundle to the relay",
)
async def publish_bundle(
    body: PreKeyBundlePublish,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    onion = body.onion_address.strip().lower()
    if not ONION_RE.match(onion):
        raise HTTPException(status_code=400, detail="Invalid onion address")

    # Caller-to-onion ownership validation
    if current_user.onion_address:
        if onion != current_user.onion_address.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot publish pre-key bundle for a different onion address",
            )
    else:
        # Bootstrap: set the onion address for this user in the DB
        current_user.onion_address = onion
        session.add(current_user)

    # Fetch existing bundle or create new
    bundle = await session.scalar(
        select(PreKeyBundle).where(PreKeyBundle.onion_address == onion)
    )
    if not bundle:
        bundle = PreKeyBundle(onion_address=onion)
        session.add(bundle)

    bundle.identity_key = body.identity_key
    bundle.signed_prekey = body.signed_prekey
    bundle.signed_prekey_sig = body.signed_prekey_sig
    bundle.pq_prekey = body.pq_prekey
    bundle.pq_prekey_sig = body.pq_prekey_sig
    bundle.one_time_prekeys = body.one_time_prekeys
    bundle.one_time_pq_prekeys = body.one_time_pq_prekeys
    bundle.published_at = datetime.now(timezone.utc)

    await session.commit()
    logger.info(
        "bundle_published", onion=onion[:12], opk_count=len(body.one_time_prekeys)
    )
    return {"success": True, "opk_count": len(body.one_time_prekeys)}


@router.post(
    "/rotate",
    summary="Rotate the signed pre-key (call weekly)",
)
async def rotate_signed_prekey(
    body: RotateSignedPreKeyRequest,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    onion = body.onion_address.strip().lower()
    if not ONION_RE.match(onion):
        raise HTTPException(status_code=400, detail="Invalid onion address")

    # Caller-to-onion ownership validation
    if current_user.onion_address:
        if onion != current_user.onion_address.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot rotate pre-key bundle for a different onion address",
            )

    bundle = await session.scalar(
        select(PreKeyBundle).where(PreKeyBundle.onion_address == onion)
    )
    if not bundle:
        raise HTTPException(
            status_code=404,
            detail="No bundle published for this address. Call /publish first.",
        )

    bundle.signed_prekey = body.signed_prekey
    bundle.signed_prekey_sig = body.signed_prekey_sig
    bundle.pq_prekey = body.pq_prekey
    bundle.pq_prekey_sig = body.pq_prekey_sig

    await session.commit()
    logger.info("signed_prekey_rotated", onion=onion[:12])
    return {"success": True}


@router.get(
    "/me",
    response_model=PreKeyBundleResponse,
    summary="Get my own current pre-key bundle (without consuming OPKs)",
)
async def get_my_bundle(
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PreKeyBundleResponse:
    # Find user's onion address
    user = await session.scalar(
        select(User).where(User.username == current_user.username)
    )
    if not user or not user.onion_address:
        raise HTTPException(
            status_code=404, detail="No onion address configured for user"
        )

    bundle = await session.scalar(
        select(PreKeyBundle).where(PreKeyBundle.onion_address == user.onion_address)
    )
    if not bundle:
        raise HTTPException(status_code=404, detail="No bundle published yet")

    return PreKeyBundleResponse(
        onion_address=bundle.onion_address,
        identity_key=bundle.identity_key,
        signed_prekey=bundle.signed_prekey,
        signed_prekey_sig=bundle.signed_prekey_sig,
        pq_prekey=bundle.pq_prekey,
        pq_prekey_sig=bundle.pq_prekey_sig,
        one_time_prekey=bundle.one_time_prekeys[0] if bundle.one_time_prekeys else None,
        one_time_pq_prekey=bundle.one_time_pq_prekeys[0]
        if bundle.one_time_pq_prekeys
        else None,
        published_at=bundle.published_at,
        opk_pool_size=len(bundle.one_time_prekeys),
    )


@router.get(
    "/{onion_address}",
    response_model=PreKeyBundleResponse,
    summary="Fetch a peer's pre-key bundle (consumes one OPK atomically)",
)
async def fetch_bundle(
    onion_address: str = Path(min_length=16, max_length=128),
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PreKeyBundleResponse:
    onion = onion_address.strip().lower()
    if not ONION_RE.match(onion):
        raise HTTPException(status_code=400, detail="Invalid onion address")

    bundle = await session.scalar(
        select(PreKeyBundle).where(PreKeyBundle.onion_address == onion)
    )
    if not bundle:
        raise HTTPException(
            status_code=404, detail="No pre-key bundle found for this address"
        )

    # Atomically consume one OPK
    opk_list = bundle.one_time_prekeys
    opq_list = bundle.one_time_pq_prekeys

    opk: str | None = None
    opq: str | None = None

    if opk_list:
        opk = opk_list.pop(0)
    if opq_list:
        opq = opq_list.pop(0)

    # Save changes back to JSON fields
    bundle.one_time_prekeys = opk_list
    bundle.one_time_pq_prekeys = opq_list

    await session.commit()

    remaining = len(opk_list)
    if remaining < 5:
        logger.warning("opk_pool_low", onion=onion[:12], remaining=remaining)

    return PreKeyBundleResponse(
        onion_address=bundle.onion_address,
        identity_key=bundle.identity_key,
        signed_prekey=bundle.signed_prekey,
        signed_prekey_sig=bundle.signed_prekey_sig,
        pq_prekey=bundle.pq_prekey,
        pq_prekey_sig=bundle.pq_prekey_sig,
        one_time_prekey=opk,
        one_time_pq_prekey=opq,
        published_at=bundle.published_at,
        opk_pool_size=remaining,
    )
