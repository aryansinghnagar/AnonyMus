"""
Notifications router — token-based push-notification polling queue.

Ports the following Flask routes to FastAPI v3:
  POST /api/notifications/register → POST /v3/notifications/register
  GET  /api/notifications/poll     → GET  /v3/notifications/poll
  POST /api/notifications/clear    → POST /v3/notifications/clear

The design is intentionally metadata-only: no message content ever appears
in notification responses.  The token is opaque to the relay and scoped to
a single (user, contact) pair.
"""

from __future__ import annotations

import base64
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.db.models import Contact, NotificationQueue
from core.logging_v3 import get_logger
from transports.p2p.routers.auth import get_current_user, UserOut

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/notifications", tags=["notifications"])

ONION_RE = re.compile(r"^[a-z2-7]{16,56}\.onion$")
MAX_TOKENS = 200


def _valid_onion(addr: str) -> str | None:
    addr = (addr or "").strip().lower()
    return addr if ONION_RE.match(addr) else None


# ── Schemas ───────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    onion_address: str = Field(min_length=16, max_length=128)


class RegisterResponse(BaseModel):
    token: str


class ClearRequest(BaseModel):
    tokens: list[str] = Field(max_length=MAX_TOKENS)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a notification token for a contact",
)
async def register(
    body: RegisterRequest,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    onion = _valid_onion(body.onion_address)
    if not onion:
        raise HTTPException(status_code=400, detail="Invalid onion address")

    # Fetch the contact
    contact = await session.scalar(
        select(Contact).where(
            Contact.owner_onion == current_user.onion_address,
            Contact.onion_address == onion,
        )
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    token = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    contact.notify_queue_token = token
    session.add(contact)
    await session.commit()
    return RegisterResponse(token=token)


@router.get(
    "/poll",
    summary="Poll for pending notifications (no message content)",
)
async def poll(
    tokens: str = Query(description="Comma-separated list of tokens (max 200)"),
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    token_list = [t.strip() for t in tokens.split(",") if t.strip()]
    if not token_list:
        return {"has_new": {}}
    if len(token_list) > MAX_TOKENS:
        raise HTTPException(
            status_code=400, detail=f"Too many tokens (max {MAX_TOKENS})"
        )

    stmt = select(NotificationQueue.token).where(
        NotificationQueue.token.in_(token_list)
    )
    res = await session.scalars(stmt)
    pending_tokens = set(res.all())

    result = {t: (t in pending_tokens) for t in token_list}
    return {"has_new": result}


@router.post(
    "/clear",
    summary="Clear pending notification flags",
)
async def clear(
    body: ClearRequest,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if len(body.tokens) > MAX_TOKENS:
        raise HTTPException(
            status_code=400, detail=f"Too many tokens (max {MAX_TOKENS})"
        )

    from sqlalchemy import delete

    await session.execute(
        delete(NotificationQueue).where(NotificationQueue.token.in_(body.tokens))
    )
    await session.commit()
    return {"success": True}


# ── Internal helper (called by the message router on delivery) ─────────────────


def notify_contact(onion: str) -> None:
    """Called when a new message arrives for a contact — sets has_new=True."""
    import transports.p2p.database as legacy_db

    conn = legacy_db.get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT notify_queue_token FROM contacts WHERE onion_address = ?", (onion,)
        )
        rows = c.fetchall()
        for r in rows:
            token = r[0]
            if token:
                c.execute(
                    "INSERT OR IGNORE INTO notify_queue (token, created_at) VALUES (?, datetime('now'))",
                    (token,),
                )
        conn.commit()
    except Exception as e:
        logger.error("notify_contact_failed", error=str(e))
    finally:
        conn.close()
