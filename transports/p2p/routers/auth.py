"""
Auth router — register, login, logout, session status.

All endpoints are localhost-only in production (enforced at the
NGINX/firewall level; the middleware check is a defence-in-depth measure).

Audit fix ANO-SEC-016 (B10): the login endpoint enforces a per-IP failed-login
lockout. Previously any IP could submit unlimited password guesses (subject
only to bcrypt's per-attempt CPU cost, ~50-200 ms). With the per-IP limiter,
an attacker from a single IP is capped at 5 failed attempts per 5-minute
window and is then locked out for 15 minutes. This is a defence-in-depth
measure — bcrypt's CPU cost remains the primary protection against offline
attackers who exfiltrate the password_hash column.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.db.models import User
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/auth", tags=["auth"])


# ── Per-IP failed-login lockout (audit fix ANO-SEC-016 / B10) ─────────────────


class _LoginRateLimiter:
    """Per-IP failed-login lockout (ANO-SEC-016).

    Policy:
      - Track failed login attempts per client IP in a rolling 5-minute window.
      - After 5 failures in the window, lock the IP out for 15 minutes.
      - Successful login resets the counter for that IP.

    This replaces the previous global counter (which a single attacker IP
    could exhaust against one user, locking out ALL users globally) with
    a per-IP counter that only affects the offending IP.

    The IP is extracted via ``_client_ip`` which prefers the socket peer
    address and only trusts ``X-Forwarded-For`` when the request originates
    from loopback (i.e., the Caddy reverse proxy on localhost) — see the
    matching pattern used in ``transports/p2p/routers/sync.py`` (ANO-V2-REG-003).
    """

    MAX_FAILURES_SHORT = 5
    SHORT_WINDOW = 300.0  # 5 minutes
    LOCKOUT_DURATION = 900.0  # 15 minutes

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_locked(self, client_ip: str) -> bool:
        with self._lock:
            until = self._locked_until.get(client_ip, 0.0)
            if time.monotonic() < until:
                return True
            # Lockout expired — clear stale entry.
            if until:
                self._locked_until.pop(client_ip, None)
                self._failures.pop(client_ip, None)
            return False

    def record_failure(self, client_ip: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._failures[client_ip]
            q.append(now)
            while q and now - q[0] > self.SHORT_WINDOW:
                q.popleft()
            if len(q) >= self.MAX_FAILURES_SHORT:
                self._locked_until[client_ip] = now + self.LOCKOUT_DURATION
                logger.warning(
                    "login_ip_locked_out",
                    client_ip=client_ip,
                    failures=len(q),
                    lockout_seconds=self.LOCKOUT_DURATION,
                )

    def record_success(self, client_ip: str) -> None:
        with self._lock:
            self._failures.pop(client_ip, None)
            self._locked_until.pop(client_ip, None)


_login_rate_limiter = _LoginRateLimiter()


def _client_ip(request: Request) -> str:
    """Best-effort client IP extraction.

    Audit fix ANO-V2-REG-003 (matching pattern in sync.py): only trust
    ``X-Forwarded-For`` when the request originates from loopback (the Caddy
    reverse proxy on localhost). For direct connections, use the socket
    peer address to prevent IP spoofing.
    """
    peer = request.client.host if request.client else "unknown"
    if peer in ("127.0.0.1", "::1", "localhost"):
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return peer


# ── Schemas ────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("username")
    @classmethod
    def _username_safe(cls, v: str) -> str:
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username may only contain letters, digits, _ and -")
        return v.lower()


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    onion_address: str | None = None

    model_config = {"from_attributes": True}


# UserOut is an alias for User, exported for use by other routers.
UserOut = User


# ── Auth dependency ────────────────────────────────────────────────────────────


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Return the authenticated user from the session cookie, or raise 401."""
    username = request.session.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    user = await session.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new local user account",
)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    existing = await session.scalar(select(User).where(User.username == body.username))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    import asyncio

    hashed = await asyncio.to_thread(
        lambda: bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    )
    user = User(username=body.username, password_hash=hashed)
    session.add(user)
    await session.flush()  # populate id before commit

    logger.info("user_registered", username=body.username)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=UserResponse,
    summary="Authenticate and start a session",
)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    # Audit fix ANO-SEC-016 (B10): per-IP failed-login lockout.
    client_ip = _client_ip(request)
    if _login_rate_limiter.is_locked(client_ip):
        logger.warning("login_attempt_locked_ip", client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": "900"},
        )

    user = await session.scalar(
        select(User).where(User.username == body.username.lower())
    )
    if not user:
        _login_rate_limiter.record_failure(client_ip)
        # Constant-ish error message (do NOT reveal whether the username exists).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    import asyncio

    is_valid = await asyncio.to_thread(
        bcrypt.checkpw, body.password.encode(), user.password_hash.encode()
    )
    if not is_valid:
        _login_rate_limiter.record_failure(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Audit fix ANO-SEC-016 (B10): reset the per-IP counter on success.
    _login_rate_limiter.record_success(client_ip)

    # Store minimal session data (FastAPI sessions via starlette SessionMiddleware)
    request.session["username"] = user.username
    logger.info("user_login", username=user.username, client_ip=client_ip)
    return UserResponse.model_validate(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate the current session",
)
async def logout(request: Request) -> None:
    request.session.clear()


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the currently authenticated user",
)
async def me(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
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

    return UserResponse.model_validate(user)
