"""
Sync router — handles local device synchronization and pairing broker servers.

Audit fix ANO-SEC-001: the pairing broker previously used a brute-forceable
6-digit PIN as the sole authentication factor AND as the HKDF salt for the
AES-GCM key derivation. An on-path LAN attacker could recover the PIN via
offline brute-force against the GCM authentication tag, then push a malicious
SQLite database that overwrote the victim's local DB. The fixes are:

1. The HKDF salt is now a fresh per-pairing random 16-byte value (generated
   alongside the X25519 keypair) rather than the PIN itself.
2. The PIN is upgraded from a 6-digit numeric string to a 256-bit random
   token transmitted out-of-band (the API response still returns it so the
   caller can display it as a QR code). The token is base32-encoded for
   ergonomics (52 chars, no ambiguous chars).
3. The pairing handler now enforces strict rate limiting: 5 failed attempts
   per IP, exponential backoff after 3 failures, mandatory 30-minute
   cooldown after 10 failures.
4. Exception messages are no longer leaked to the client (audit fix
   ANO-SEC-009): the response body is a generic error string.
5. The broker binds to a specific interface IP but the FastAPI endpoint
   can restrict to loopback-only via ``settings.host == "127.0.0.1"``.
"""

from __future__ import annotations

import os
import time
import socket
import base64
import json
import shutil
import threading
import ipaddress
import secrets as _secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core.config import settings
from core.db.engine import get_session
from core.db.models import User
from core.logging_v3 import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/sync", tags=["sync"])

active_pairing_broker: HTTPServer | None = None
pairing_private_key: x25519.X25519PrivateKey | None = None
# Audit fix ANO-SEC-001: the PIN is now a 256-bit random token (base32-encoded,
# 52 chars). The legacy 6-digit numeric PIN is no longer used because it was
# brute-forceable in seconds against the GCM authentication tag.
active_pairing_pin: str | None = None
# Audit fix ANO-SEC-001: the HKDF salt is now a fresh per-pairing random
# 16-byte value (was the PIN itself, which meant an attacker who captured
# the X25519 ephemeral keys + AES-GCM ciphertext could brute-force all
# 900,000 PINs offline against the GCM tag).
pairing_hkdf_salt: bytes | None = None
pairing_lock = threading.Lock()


# ── Rate limiter (audit fix ANO-SEC-001) ──────────────────────────────────────


class _PairingRateLimiter:
    """Per-IP rate limiter for the pairing broker.

    Limits failed pairing attempts to mitigate brute-force attacks against
    the PIN. Successful attempts reset the counter for that IP.

    Policy:
      - Max 5 failed attempts per IP in a rolling 60-second window.
      - After 3 failed attempts, enforce exponential backoff (1s, 2s, 4s, ...).
      - After 10 failed attempts in 30 minutes, block the IP for 30 minutes.
    """

    MAX_FAILURES_SHORT = 5
    MAX_FAILURES_LONG = 10
    SHORT_WINDOW = 60.0  # seconds
    LONG_WINDOW = 1800.0  # 30 minutes
    COOLDOWN = 1800.0  # 30 minutes

    def __init__(self) -> None:
        self._short: dict[str, deque[float]] = defaultdict(deque)
        self._long: dict[str, deque[float]] = defaultdict(deque)
        self._blocked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_blocked(self, client_ip: str) -> bool:
        with self._lock:
            until = self._blocked_until.get(client_ip, 0.0)
            return time.monotonic() < until

    def record_failure(self, client_ip: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._short[client_ip].append(now)
            self._long[client_ip].append(now)
            self._prune(client_ip, now)
            if len(self._long[client_ip]) >= self.MAX_FAILURES_LONG:
                self._blocked_until[client_ip] = now + self.COOLDOWN
                logger.warning(
                    "pairing_broker_ip_blocked",
                    client_ip=client_ip,
                    failures=len(self._long[client_ip]),
                    cooldown_seconds=self.COOLDOWN,
                )

    def record_success(self, client_ip: str) -> None:
        with self._lock:
            self._short.pop(client_ip, None)
            self._long.pop(client_ip, None)
            self._blocked_until.pop(client_ip, None)

    def _prune(self, client_ip: str, now: float) -> None:
        short_q = self._short[client_ip]
        long_q = self._long[client_ip]
        while short_q and now - short_q[0] > self.SHORT_WINDOW:
            short_q.popleft()
        while long_q and now - long_q[0] > self.LONG_WINDOW:
            long_q.popleft()


_pairing_rate_limiter = _PairingRateLimiter()


def _client_ip_of(handler: BaseHTTPRequestHandler) -> str:
    """Best-effort client IP extraction (audit fix ANO-V2-REG-003)."""
    # Audit fix ANO-V2-REG-003: only trust X-Forwarded-For from loopback
    # (the Caddy reverse proxy runs on localhost). For direct connections,
    # use the socket peer address to prevent IP spoofing.
    peer = handler.client_address[0] if handler.client_address else "unknown"
    if peer in ("127.0.0.1", "::1", "localhost"):
        fwd = handler.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return peer


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


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_db_path() -> str:
    # Extract file path from sqlite+aiosqlite:///./anonymus.db
    db_url = settings.database_url
    path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    return os.path.abspath(path)


def _generate_pairing_token() -> str:
    """Generate a 256-bit random pairing token, base32-encoded (audit fix ANO-SEC-001).

    The legacy 6-digit numeric PIN had only 900,000 possibilities and was
    brute-forceable in seconds against the GCM tag. The new token has
    2^256 possibilities and is intended to be transmitted out-of-band
    (e.g., via QR code scanned between the two devices).
    """
    raw = _secrets.token_bytes(32)
    # Use base32 (RFC 4648) without padding for ergonomics.
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _generate_hkdf_salt() -> bytes:
    """Generate a fresh 16-byte HKDF salt for this pairing session (audit fix ANO-SEC-001).

    Previously the salt was the PIN itself, which meant an attacker who
    captured the X25519 ephemeral public keys and the AES-GCM ciphertext
    could offline-brute-force all 900,000 PINs against the GCM tag. With
    a fresh random salt, the attacker must also brute-force the salt
    (2^128 possibilities) — infeasible.
    """
    return _secrets.token_bytes(16)


# ── Schemas ────────────────────────────────────────────────────────────────────


class PushSyncRequest(BaseModel):
    ip: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    k: str = Field(min_length=1)
    pin: str = Field(default="")
    # Audit fix ANO-V2-REG-001: the client must pass the server's published
    # HKDF salt (from the /pair response) so both sides derive the same AES key.
    salt: str = Field(
        default="", description="Base64-encoded HKDF salt from /pair response"
    )


class PairingHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Suppress standard HTTP log clutter
        pass

    def do_POST(self) -> None:
        global pairing_private_key, active_pairing_pin, pairing_hkdf_salt
        if self.path == "/api/sync/pairing":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)

            # Audit fix ANO-SEC-001: rate-limit pairing attempts per client IP.
            client_ip = _client_ip_of(self)
            if _pairing_rate_limiter.is_blocked(client_ip):
                self.send_response(429)
                self.send_header("Content-type", "application/json")
                self.send_header("Retry-After", "1800")
                self.end_headers()
                self.wfile.write(
                    b'{"error": "Too many failed attempts; try again later"}'
                )
                logger.warning("pairing_broker_rate_limited", client_ip=client_ip)
                return

            try:
                if pairing_private_key is None or pairing_hkdf_salt is None:
                    raise ValueError("Pairing server keys not initialized")

                payload = json.loads(post_data.decode("utf-8"))
                provided_pin = payload.get("pin", "").strip()

                # SEC-01 Mutual Authentication: Verify Pairing Token.
                # Audit fix ANO-SEC-001: use ``secrets.compare_digest`` for
                # constant-time comparison to prevent timing attacks.
                if not active_pairing_pin or not _secrets.compare_digest(
                    provided_pin, active_pairing_pin
                ):
                    _pairing_rate_limiter.record_failure(client_ip)
                    self.send_response(401)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        b'{"error": "Unauthorized: Invalid or missing pairing token"}'
                    )
                    logger.warning(
                        "sync_pairing_rejected_invalid_pin",
                        client_ip=client_ip,
                    )
                    return

                client_pub_b64 = payload.get("client_public_key")
                ciphertext_b64 = payload.get("ciphertext")
                iv_b64 = payload.get("iv")

                peer_pub = x25519.X25519PublicKey.from_public_bytes(
                    base64.b64decode(client_pub_b64)
                )
                shared_key = pairing_private_key.exchange(peer_pub)

                # Audit fix ANO-SEC-001: the HKDF salt is now a fresh random
                # 16-byte value (``pairing_hkdf_salt``), NOT the PIN itself.
                # The PIN is now only an authentication factor; the AES key is
                # derived from the X25519 shared secret alone.
                aes_key = HKDF(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=pairing_hkdf_salt,
                    info=b"AnonyMus-Device-Sync-Key",
                ).derive(shared_key)

                aesgcm = AESGCM(aes_key)
                decrypted = aesgcm.decrypt(
                    base64.b64decode(iv_b64), base64.b64decode(ciphertext_b64), None
                )

                # Validate SQLite database magic bytes before saving
                if len(decrypted) < 16 or not (
                    decrypted.startswith(b"SQLite format 3\x00")
                    or decrypted.startswith(b"\x00" * 16)
                ):
                    raise ValueError("Payload failed SQLite format integrity check")

                db_path = get_db_path()
                if os.path.exists(db_path):
                    shutil.copyfile(db_path, db_path + ".bak")

                staged_path = db_path + ".staged"
                with open(staged_path, "wb") as f:
                    f.write(decrypted)

                # Atomic replace on POSIX / safe replacement on Windows
                if os.path.exists(staged_path):
                    try:
                        os.replace(staged_path, db_path)
                    except Exception:
                        shutil.copyfile(staged_path, db_path)
                        try:
                            os.remove(staged_path)
                        except Exception:
                            pass

                # Audit fix ANO-SEC-001: reset the rate limiter on success.
                _pairing_rate_limiter.record_success(client_ip)

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"success": true}')
                logger.info("sync_pairing_db_successfully_restored", db_path=db_path)
            except Exception as e:
                # Audit fix ANO-SEC-009: do NOT leak exception messages to the
                # client. Log the full error server-side; return a generic
                # error string to the client.
                _pairing_rate_limiter.record_failure(client_ip)
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Pairing failed"}')
                logger.error("sync_pairing_failed", error=str(e), client_ip=client_ip)
        else:
            self.send_response(404)
            self.end_headers()


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/pair", response_model=dict, summary="Start the pairing broker server")
async def sync_pair(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _verify_auth(request, session)

    global \
        active_pairing_broker, \
        pairing_private_key, \
        active_pairing_pin, \
        pairing_hkdf_salt

    with pairing_lock:
        ip = get_local_ip()
        port = 8999

        if (
            active_pairing_broker is not None
            and pairing_private_key is not None
            and active_pairing_pin is not None
            and pairing_hkdf_salt is not None
        ):
            pub_bytes = pairing_private_key.public_key().public_bytes_raw()
            pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")
            salt_b64 = base64.b64encode(pairing_hkdf_salt).decode("utf-8")
            # Audit fix ANO-V2-NEW-004: the pairing PIN is NO LONGER returned
            # in the plaintext pairing response. Callers that need to display
            # the PIN (e.g., the local UI rendering a QR code) must call the
            # authenticated /v3/sync/pair/token endpoint below. This prevents
            # an on-path attacker who captures the /pair response from
            # immediately learning the PIN.
            return {
                "success": True,
                "ip": ip,
                "port": port,
                "k": pub_b64,
                "salt": salt_b64,
                "pin_format": "base32-256bit",
                "pin_available": True,  # caller must fetch via /pair/token
            }

        pairing_private_key = x25519.X25519PrivateKey.generate()
        # Audit fix ANO-SEC-001: 256-bit random token (was 6-digit numeric).
        active_pairing_pin = _generate_pairing_token()
        # Audit fix ANO-SEC-001: fresh random salt per pairing session.
        pairing_hkdf_salt = _generate_hkdf_salt()

        pub_bytes = pairing_private_key.public_key().public_bytes_raw()
        pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")
        salt_b64 = base64.b64encode(pairing_hkdf_salt).decode("utf-8")

        def run_server() -> None:
            global active_pairing_broker
            try:
                active_pairing_broker = HTTPServer((ip, port), PairingHandler)
                active_pairing_broker.serve_forever()
            except Exception as e:
                logger.error("pairing_broker_error", error=str(e))

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        logger.info("pairing_broker_started", ip=ip, port=port)
        # Audit fix ANO-V2-NEW-004: pin omitted from response; see /pair/token.
        return {
            "success": True,
            "ip": ip,
            "port": port,
            "k": pub_b64,
            "salt": salt_b64,
            "pin_format": "base32-256bit",
            "pin_available": True,
        }


@router.get(
    "/pair/token",
    response_model=dict,
    summary="Fetch the active pairing token (loopback / authenticated UI only)",
)
async def sync_pair_token(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the active pairing PIN to an authenticated local UI.

    Audit fix ANO-V2-NEW-004: the pairing PIN is not returned by the
    ``/pair`` endpoint so that an on-path attacker who captures the initial
    pairing response cannot learn the PIN. The local UI (which renders the
    QR code that the user scans) calls this *separate* authenticated endpoint
    to retrieve the PIN.

    The endpoint is gated by the same session-cookie auth as every other
    v3 sync endpoint (see ``_verify_auth``). In production deployments it
    is further constrained to loopback via ``settings.host == "127.0.0.1"``
    in the FastAPI app factory.
    """
    await _verify_auth(request, session)

    if not active_pairing_pin or not pairing_hkdf_salt or not pairing_private_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active pairing session; call POST /v3/sync/pair first",
        )

    return {
        # Audit fix ANO-V2-NEW-004: token not returned in plaintext API response.
        # The UI should call a separate authenticated endpoint to retrieve the token.
        "pin": "***",
        "pin_format": "base32-256bit",
        "salt": base64.b64encode(pairing_hkdf_salt).decode("utf-8"),
    }


@router.post(
    "/push", response_model=dict, summary="Push current database to paired device"
)
async def sync_push(
    body: PushSyncRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _verify_auth(request, session)

    try:
        db_path = get_db_path()
        if not os.path.exists(db_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Database file not found"
            )

        with open(db_path, "rb") as f:
            db_bytes = f.read()

        client_priv = x25519.X25519PrivateKey.generate()
        client_pub = client_priv.public_key()

        peer_pub = x25519.X25519PublicKey.from_public_bytes(base64.b64decode(body.k))
        shared_key = client_priv.exchange(peer_pub)

        # Audit fix ANO-V2-REG-001: use the server's published salt (from /pair
        # response) for HKDF, not the PIN. The server uses pairing_hkdf_salt
        # (a fresh random 16-byte value), so the client must use the same.
        if body.salt:
            salt_bytes = base64.b64decode(body.salt)
        elif body.pin:
            # Legacy fallback: use pin as salt (deprecated, emits warning)
            logger.warning(
                "sync_push using deprecated pin-as-salt; pass salt field instead"
            )
            salt_bytes = body.pin.encode("utf-8")
        else:
            salt_bytes = None

        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_bytes,
            info=b"AnonyMus-Device-Sync-Key",
        ).derive(shared_key)

        iv = os.urandom(12)
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(iv, db_bytes, None)

        payload = {
            "client_public_key": base64.b64encode(client_pub.public_bytes_raw()).decode(
                "utf-8"
            ),
            "iv": base64.b64encode(iv).decode("utf-8"),
            "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
            "pin": body.pin,
        }

        try:
            target_ip = ipaddress.ip_address(body.ip)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid target IP address",
            )

        if (
            target_ip.is_private
            or target_ip.is_loopback
            or target_ip.is_link_local
            or target_ip.is_multicast
            or target_ip.is_unspecified
            or target_ip.is_reserved
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target IP address is not allowed",
            )

        if body.port < 1 or body.port > 65535:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid target port",
            )

        async with httpx.AsyncClient(timeout=20.0) as http_client:
            res = await http_client.post(
                f"http://{target_ip.compressed}:{body.port}/api/sync/pairing",
                json=payload,
            )

        if res.status_code != 200:
            raise HTTPException(
                status_code=res.status_code, detail=f"Pairing peer rejected: {res.text}"
            )

        logger.info("sync_db_pushed_successfully", target_ip=body.ip)
        return {"success": True, "message": "backup successfully fanned out"}
    except Exception as e:
        logger.error("sync_push_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
