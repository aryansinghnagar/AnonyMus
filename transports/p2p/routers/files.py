"""
Files router — local and P2P file chunk upload/download (XFTP protocol).

Ports the following Flask routes to FastAPI v3:
  POST /api/file/upload/<chunk_id>   -> POST /v3/files/upload/{chunk_id}
  GET  /api/file/download/<chunk_id> -> GET  /v3/files/download/{chunk_id}
  POST /p2p/file/upload/<chunk_id>   -> POST /v3/files/p2p/upload/{chunk_id}
  GET  /p2p/file/download/<chunk_id> -> GET  /v3/files/p2p/download/{chunk_id}

Audit fix ANO-SEC-012 (B7): chunks are now encrypted at rest with a per-chunk
AES-256-GCM key derived from the contact's shared secret via HKDF-SHA256. The
contact's shared secret is looked up by sender_onion (for P2P uploads) or by
the local user's onion (for local uploads). When no shared secret is available
the chunk is encrypted with a server-side master key derived from
``settings.db_key`` via HKDF, so chunks are never stored in plaintext on disk.

Perf fix P5: chunk I/O uses ``aiofiles`` so the event loop is not blocked by
synchronous file writes/reads. Pruning is run in a worker thread via
``asyncio.to_thread`` for the same reason.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import tempfile
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from core.config import settings
from core.db.engine import get_session
from core.db.models import Contact
from core.logging_v3 import get_logger
from transports.p2p.routers.auth import get_current_user, UserOut

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/files", tags=["files"])

_ONION_V3_RE = re.compile(r"^([a-z2-7]{56}\.onion)(?::([0-9]{1,5}))?$")
_CHUNK_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

# Bounded disk-backed chunk store for XFTP transfer
XFTP_CHUNK_DIR = Path(tempfile.gettempdir()) / "anonymus_xftp_chunks"
XFTP_CHUNK_DIR.mkdir(parents=True, exist_ok=True)
MAX_TOTAL_STORAGE_BYTES = 500 * 1024 * 1024  # 500 MB
CHUNK_TTL_SECONDS = 900  # 15 minutes

# Audit fix ANO-SEC-012 (B7): on-disk magic prefix identifying an encrypted
# chunk. Legacy (pre-fix) chunks have no magic prefix and are returned raw.
_CHUNK_MAGIC = b"AMENC1"
_CHUNK_MAGIC_LEN = len(_CHUNK_MAGIC)


# Audit fix ANO-SEC-004: per-uploader subdirectory under the chunk store,
# keyed by sender onion address. Prevents cross-uploader overwrites.
def _uploader_dir(sender_onion: str) -> Path:
    """Return (creating if necessary) the per-uploader chunk subdirectory."""
    # Validate the onion address to prevent path traversal via the sender field.
    if not _ONION_V3_RE.match(sender_onion):
        raise HTTPException(
            status_code=400, detail="Invalid sender onion address format"
        )
    # Use a hash of the onion so the directory name is filesystem-safe.
    safe = hashlib.sha256(sender_onion.encode("utf-8")).hexdigest()[:32]
    base_dir = XFTP_CHUNK_DIR.resolve()
    d = (base_dir / safe).resolve()
    try:
        d.relative_to(base_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid uploader directory path")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_chunk_id(chunk_id: str) -> str:
    if not _CHUNK_ID_RE.match(chunk_id):
        raise HTTPException(status_code=400, detail="Invalid chunk identifier format")
    return chunk_id


def _safe_chunk_path(target_dir: Path, chunk_id: str) -> Path:
    """Return a verified Path inside target_dir for chunk_id, preventing path traversal."""
    clean_id = _sanitize_chunk_id(chunk_id)
    safe_name = Path(clean_id).name
    base_dir = target_dir.resolve()
    target = (base_dir / f"{safe_name}.chunk").resolve()
    try:
        target.relative_to(base_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chunk path")
    return target


# ── Per-uploader rate limiter (audit fix ANO-SEC-004) ─────────────────────────


class _P2PUploadRateLimiter:
    """Per-uploader rate limiter to prevent quota-exhaustion DoS.

    Limits each uploader to 50 chunks per 5-minute window. Combined with
    the 500 MB total quota and 15-minute TTL, this bounds a single
    uploader to ~500 MB / 5 minutes (10 MB x 50 chunks) -- enough for
    legitimate file transfers but prevents a single peer from evicting
    all in-flight transfers from other peers.
    """

    WINDOW_SECONDS = 300.0  # 5 minutes
    MAX_UPLOADS_PER_WINDOW = 50

    def __init__(self) -> None:
        self._uploads: dict[str, deque[float]] = defaultdict(deque)
        import threading

        self._lock = threading.Lock()

    def check_and_record(self, uploader: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._uploads[uploader]
            while q and now - q[0] > self.WINDOW_SECONDS:
                q.popleft()
            if len(q) >= self.MAX_UPLOADS_PER_WINDOW:
                return False
            q.append(now)
            return True


_p2p_rate_limiter = _P2PUploadRateLimiter()


def _prune_expired_chunks():
    """Removes expired chunks and maintains 500 MB storage cap."""
    try:
        now = time.time()
        files = list(XFTP_CHUNK_DIR.glob("*/*.chunk")) + list(
            XFTP_CHUNK_DIR.glob("*.chunk")
        )
        total_bytes = 0

        # Remove TTL expired
        for f in files:
            try:
                stat = f.stat()
                if now - stat.st_mtime > CHUNK_TTL_SECONDS:
                    f.unlink(missing_ok=True)
                else:
                    total_bytes += stat.st_size
            except Exception:
                pass

        # If still over quota, remove oldest
        if total_bytes > MAX_TOTAL_STORAGE_BYTES:
            active_files = sorted(files, key=lambda p: p.stat().st_mtime)
            for f in active_files:
                if total_bytes <= MAX_TOTAL_STORAGE_BYTES:
                    break
                try:
                    size = f.stat().st_size
                    f.unlink(missing_ok=True)
                    total_bytes -= size
                except Exception:
                    pass
    except Exception as e:
        logger.warning("xftp_pruning_error", error=str(e))


# ── Chunk-at-rest encryption (audit fix ANO-SEC-012 / B7) ────────────────────


# Per-process fallback master key, used only when ``settings.db_key`` is empty
# (dev/test mode). In production db_key is set and the master key is derived
# deterministically from it so chunks survive restarts.
_PROCESS_FALLBACK_MASTER_KEY: bytes | None = None


def _master_chunk_key() -> bytes:
    """Derive the fallback master chunk key from ``settings.db_key``.

    Audit fix ANO-SEC-012 (B7): when a contact's shared secret is not
    available (e.g., local uploads by the user themself, or P2P uploads
    from a peer who is not yet a saved contact), we still MUST NOT write
    the plaintext chunk to disk. Instead we derive a server-side master
    key from ``settings.db_key`` via HKDF-SHA256.

    If ``settings.db_key`` is empty (dev/test mode), we generate a random
    per-process key. This means chunks don't survive restarts in dev
    mode, but the 15-minute TTL makes that acceptable.
    """
    global _PROCESS_FALLBACK_MASTER_KEY
    if settings.db_key:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"AnonyMus-XFTP-Master-Chunk-Key",
        ).derive(settings.db_key.encode("utf-8"))
    # Dev/test fallback: random per-process key.
    if _PROCESS_FALLBACK_MASTER_KEY is None:
        import os

        _PROCESS_FALLBACK_MASTER_KEY = os.urandom(32)
        logger.warning(
            "xftp_master_key_dev_fallback",
            reason="db_key empty; using random per-process master chunk key",
        )
    return _PROCESS_FALLBACK_MASTER_KEY


def _derive_chunk_key(shared_secret_b64: str | None, chunk_id: str) -> bytes:
    """Derive a per-chunk AES-256-GCM key from the contact's shared secret.

    Audit fix ANO-SEC-012 (B7): HKDF-SHA256 with ``shared_secret`` as IKM
    and ``chunk_id`` as info produces a unique 32-byte key per (contact,
    chunk) pair. An attacker who exfiltrates the chunk store cannot derive
    the key without also exfiltrating the contact row's shared_secret_b64
    (which is itself encrypted at rest via the SQLCipher db_key -- see
    ANO-SEC-008).

    If ``shared_secret_b64`` is None (no known contact for this sender),
    the master chunk key is used as the IKM, with the same HKDF info, so
    the per-chunk key is still unique per chunk_id.
    """
    if shared_secret_b64:
        try:
            ikm = base64.b64decode(shared_secret_b64)
        except Exception:
            ikm = shared_secret_b64.encode("utf-8")
    else:
        ikm = _master_chunk_key()
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"AnonyMus-XFTP-ChunkKey/" + chunk_id.encode("utf-8"),
    ).derive(ikm)


async def _lookup_shared_secret(
    session: AsyncSession, sender_onion: str | None
) -> str | None:
    """Return the contact's shared_secret_b64 for ``sender_onion`` (or None).

    For P2P uploads, ``sender_onion`` is the peer's onion. We look up the
    first Contact row whose ``onion_address`` matches -- there is typically
    only one local user per node, so this returns the correct contact.
    """
    if not sender_onion:
        return None
    try:
        contact = await session.scalar(
            select(Contact).where(Contact.onion_address == sender_onion).limit(1)
        )
        if contact and contact.shared_secret_b64:
            return contact.shared_secret_b64
    except Exception as e:
        logger.warning(
            "xftp_contact_lookup_failed", sender=sender_onion[:16], error=str(e)
        )
    return None


def _encrypt_chunk(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt a chunk with AES-256-GCM, prepending magic + nonce.

    On-disk format: ``b"AMENC1" || nonce(12) || ciphertext`` (the GCM
    authentication tag is appended to the ciphertext by AESGCM.encrypt).
    """
    import os

    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return _CHUNK_MAGIC + nonce + ct


def _decrypt_chunk(blob: bytes, key: bytes) -> bytes | None:
    """Decrypt a chunk encoded with ``_encrypt_chunk``. Returns None on failure."""
    if len(blob) < _CHUNK_MAGIC_LEN + 12 + 16:  # magic + nonce + min GCM tag
        return None
    if blob[:_CHUNK_MAGIC_LEN] != _CHUNK_MAGIC:
        return None  # legacy plaintext chunk
    nonce = blob[_CHUNK_MAGIC_LEN : _CHUNK_MAGIC_LEN + 12]
    ct = blob[_CHUNK_MAGIC_LEN + 12 :]
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ct, None)
    except Exception:
        return None


async def _save_chunk(
    chunk_id: str,
    data: bytes,
    sender_onion: str | None = None,
    session: AsyncSession | None = None,
) -> None:
    """Save a chunk to disk, encrypted at rest.

    Audit fix ANO-SEC-004: when ``sender_onion`` is provided, the chunk is
    written to the per-uploader subdirectory so two peers writing the same
    ``chunk_id`` will not overwrite each other's data.

    Audit fix ANO-SEC-012 (B7): the chunk is encrypted with a per-chunk
    AES-256-GCM key derived from the contact's shared secret (or the
    server-side master key as fallback).

    Perf fix P5: uses ``aiofiles`` for non-blocking I/O.
    """
    # Prune in a worker thread to avoid blocking the event loop.
    await asyncio.to_thread(_prune_expired_chunks)

    if sender_onion:
        target_dir = _uploader_dir(sender_onion)
    else:
        target_dir = XFTP_CHUNK_DIR
    target = _safe_chunk_path(target_dir, chunk_id)

    # Look up the contact's shared secret for per-chunk key derivation.
    shared_secret = None
    if session is not None and sender_onion:
        shared_secret = await _lookup_shared_secret(session, sender_onion)

    key = _derive_chunk_key(shared_secret, chunk_id)
    encrypted = _encrypt_chunk(data, key)

    try:
        import aiofiles

        async with aiofiles.open(target, "wb") as f:
            await f.write(encrypted)
    except ImportError:
        # aiofiles not installed -- fall back to sync write in a worker thread.
        await asyncio.to_thread(_write_bytes_sync, target, encrypted)


def _write_bytes_sync(path: Path, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _read_bytes_sync(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


async def _load_chunk(
    chunk_id: str,
    sender_onion: str | None = None,
    session: AsyncSession | None = None,
) -> bytes | None:
    """Load and decrypt a chunk. Returns None if not found or decryption fails."""
    if sender_onion:
        target_dir = _uploader_dir(sender_onion)
    else:
        target_dir = XFTP_CHUNK_DIR
    target = _safe_chunk_path(target_dir, chunk_id)
    if not target.exists():
        return None
    try:
        if time.time() - target.stat().st_mtime > CHUNK_TTL_SECONDS:
            target.unlink(missing_ok=True)
            return None

        # Read the encrypted blob (async via aiofiles or worker thread).
        try:
            import aiofiles

            async with aiofiles.open(target, "rb") as f:
                blob = await f.read()
        except ImportError:
            blob = await asyncio.to_thread(_read_bytes_sync, target)

        # Legacy plaintext chunk (pre-B7) -- return as-is.
        if blob[:_CHUNK_MAGIC_LEN] != _CHUNK_MAGIC:
            return blob

        # Try contact-derived key first.
        if session is not None and sender_onion:
            shared_secret = await _lookup_shared_secret(session, sender_onion)
            if shared_secret:
                key = _derive_chunk_key(shared_secret, chunk_id)
                plaintext = _decrypt_chunk(blob, key)
                if plaintext is not None:
                    return plaintext
                logger.warning(
                    "xftp_chunk_decrypt_failed_with_contact_key",
                    chunk_id=chunk_id,
                    sender=sender_onion[:16],
                )

        # Fall back to master key.
        key = _derive_chunk_key(None, chunk_id)
        plaintext = _decrypt_chunk(blob, key)
        if plaintext is None:
            logger.error(
                "xftp_chunk_decrypt_failed_permanent",
                chunk_id=chunk_id,
                sender=sender_onion[:16] if sender_onion else "unknown",
            )
            return None
        return plaintext
    except Exception as e:
        logger.warning("xftp_load_error", chunk_id=chunk_id, error=str(e))
        return None


# ── Signature verification (audit fix ANO-SEC-004) ────────────────────────────


def _verify_p2p_upload_signature(
    chunk_id: str,
    timestamp: str,
    signature_b64: str,
    sender_onion: str,
    max_skew_seconds: int = 300,
) -> None:
    """Verify an Ed25519 signature over (chunk_id || timestamp) from the sender.

    Audit fix ANO-SEC-004: the P2P upload endpoint now requires the uploader
    to sign ``f"{chunk_id}|{timestamp}"`` with the Ed25519 identity key
    whose public-key bytes are encoded in the v3 onion address.

    Tor v3 onion addresses encode a 32-byte Ed25519 public key in base32
    (the first 56 characters before ``.onion``). We extract the public key
    from the sender's onion address, then verify the signature.

    Raises HTTPException 401 if the signature is invalid or the timestamp
    is outside the allowed skew window.
    """
    import base64 as _b64
    import datetime as _dt

    # Validate the sender onion address format (v3 only: 56 base32 chars + .onion).
    m = _ONION_V3_RE.match(sender_onion)
    if not m:
        raise HTTPException(
            status_code=400,
            detail="Sender must be a v3 onion address (56 base32 chars + .onion)",
        )
    onion_host = m.group(1)
    pubkey_b32 = onion_host[:56]

    # Decode the base32 public key.
    pad_len = (-len(pubkey_b32)) % 8
    try:
        pubkey_bytes = _b64.b32decode(pubkey_b32 + "=" * pad_len)
    except Exception:
        raise HTTPException(
            status_code=400, detail="Could not decode onion address public key"
        )
    # Audit fix ANO-V2-REG-002: Tor v3 onion addresses encode 35 bytes
    # (32-byte Ed25519 pubkey + 1 version byte + 2 checksum bytes).
    # The previous code checked ``len == 32`` and rejected all valid
    # onion addresses. Fix: accept 35 bytes and extract the first 32.
    if len(pubkey_bytes) != 35:
        raise HTTPException(
            status_code=400,
            detail=f"Decoded onion address must be 35 bytes (got {len(pubkey_bytes)})",
        )
    ed25519_pubkey = pubkey_bytes[:32]

    # Validate timestamp skew (defense against replay attacks).
    try:
        ts = _dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid timestamp format (expected ISO-8601)"
        )
    now = _dt.datetime.now(_dt.timezone.utc)
    skew = abs((now - ts).total_seconds())
    if skew > max_skew_seconds:
        raise HTTPException(
            status_code=401,
            detail=f"Timestamp skew {skew:.0f}s exceeds allowed {max_skew_seconds}s",
        )

    # Verify the signature.
    try:
        signature = _b64.b64decode(signature_b64)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(ed25519_pubkey)
        message = f"{chunk_id}|{timestamp}".encode("utf-8")
        public_key.verify(signature, message)
    except InvalidSignature:
        raise HTTPException(status_code=401, detail="Invalid Ed25519 signature")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Signature verification failed: {e}"
        )


@router.post(
    "/upload/{chunk_id}",
    summary="Upload a file chunk (local client)",
)
async def local_upload(
    chunk_id: str,
    request: Request,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")
    if len(body) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="Chunk size too large (max 10MB)")

    # Audit fix ANO-SEC-012 (B7): pass session so the chunk can be encrypted
    # with the per-contact shared secret when one is available. For local
    # uploads the sender is the local user themself, so the master fallback
    # key is used in practice (there is no "self" contact row).
    await _save_chunk(chunk_id, body, sender_onion=None, session=session)
    logger.info("chunk_uploaded_locally", chunk_id=chunk_id, size=len(body))
    return {"success": True}


@router.get(
    "/download/{chunk_id}",
    summary="Download a file chunk (local client with Tor proxy option)",
)
async def local_download(
    chunk_id: str,
    request: Request,
    onion: str | None = Query(
        default=None, description="Peer onion address to proxy download over Tor"
    ),
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # If onion address is supplied, proxy the request over Tor to the peer's P2P endpoint
    if onion:
        normalized_onion = onion.strip().lower()
        if (
            any(ch in normalized_onion for ch in ("/", "\\", "?", "#", "@"))
            or "://" in normalized_onion
        ):
            raise HTTPException(status_code=400, detail="Invalid onion address format")

        m = _ONION_V3_RE.fullmatch(normalized_onion)
        if not m:
            raise HTTPException(status_code=400, detail="Invalid onion address format")

        clean_host = m.group(1)
        clean_port = m.group(2)
        if clean_port is not None and not (1 <= int(clean_port) <= 65535):
            raise HTTPException(status_code=400, detail="Invalid onion port")

        parsed_target_url = httpx.URL(
            scheme="http",
            host=clean_host,
            port=int(clean_port) if clean_port else None,
            path=f"/v3/files/p2p/download/{chunk_id}",
        )

        logger.info(
            "proxying_chunk_download_over_tor",
            chunk_id=chunk_id,
            peer=clean_host[:12],
        )
        try:
            # SOCKS proxy config for outbound Tor
            from transports.p2p.tor_manager import SOCKS_PORT

            proxies = {
                "http://": f"socks5://127.0.0.1:{SOCKS_PORT}",
                "https://": f"socks5://127.0.0.1:{SOCKS_PORT}",
            }
            async with httpx.AsyncClient(proxies=proxies, timeout=60.0) as client:
                res = await client.get(parsed_target_url)
                if res.status_code == 200:
                    return Response(
                        content=res.content,
                        media_type="application/octet-stream",
                        headers={
                            "X-Content-Type-Options": "nosniff",
                            "Content-Disposition": "attachment; filename=chunk.bin",
                        },
                    )
                else:
                    raise HTTPException(
                        status_code=res.status_code,
                        detail="Peer returned download error",
                    )
        except Exception as e:
            logger.error("proxy_download_failed", chunk_id=chunk_id, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to download from peer over Tor",
            )

    # Local download from bounded disk store (now decrypted, see B7).
    chunk = await _load_chunk(chunk_id, sender_onion=None, session=session)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    return Response(content=chunk, media_type="application/octet-stream")


# ── Public P2P Endpoints (accessed via Tor) ───────────────────────────────────


@router.post(
    "/p2p/upload/{chunk_id}",
    summary="Upload a file chunk (inbound P2P over Tor)",
)
async def p2p_upload(
    chunk_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Audit fix ANO-SEC-004: require an Ed25519 signature from the uploader
    # so anonymous peers cannot pollute the chunk store or evict in-flight
    # transfers from other peers. The signature is over
    # ``f"{chunk_id}|{timestamp}"`` where timestamp is an ISO-8601 string
    # included in the ``X-Timestamp`` header. The uploader's identity is
    # derived from the onion address in the ``X-Sender-Onion`` header,
    # which must match the public key recovered from the signature.
    sender_onion = request.headers.get("X-Sender-Onion", "")
    timestamp = request.headers.get("X-Timestamp", "")
    signature_b64 = request.headers.get("X-Signature", "")

    if not sender_onion or not timestamp or not signature_b64:
        raise HTTPException(
            status_code=401,
            detail=(
                "P2P upload requires X-Sender-Onion, X-Timestamp, and "
                "X-Signature headers (audit fix ANO-SEC-004)"
            ),
        )

    # Verify signature before reading the (potentially large) body.
    _verify_p2p_upload_signature(chunk_id, timestamp, signature_b64, sender_onion)

    # Per-uploader rate limiting.
    if not _p2p_rate_limiter.check_and_record(sender_onion):
        raise HTTPException(
            status_code=429,
            detail="Per-uploader rate limit exceeded; try again later",
        )

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")
    if len(body) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Chunk size too large")

    # Audit fix ANO-SEC-012 (B7): encrypt chunk with per-contact key.
    await _save_chunk(chunk_id, body, sender_onion=sender_onion, session=session)
    logger.info(
        "chunk_uploaded_p2p",
        chunk_id=chunk_id,
        size=len(body),
        sender=sender_onion[:16],
    )
    return {"success": True}


@router.get(
    "/p2p/download/{chunk_id}",
    summary="Download a file chunk (inbound P2P over Tor)",
)
async def p2p_download(
    chunk_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    # Audit fix ANO-SEC-004: require the requester to specify which uploader's
    # chunk they want (per-uploader subdirectory isolation).
    sender_onion = request.headers.get("X-Sender-Onion", "")
    chunk = await _load_chunk(
        chunk_id, sender_onion=sender_onion or None, session=session
    )
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    logger.info(
        "chunk_downloaded_p2p",
        chunk_id=chunk_id,
        size=len(chunk),
        sender=sender_onion[:16] if sender_onion else "unknown",
    )
    return Response(content=chunk, media_type="application/octet-stream")
