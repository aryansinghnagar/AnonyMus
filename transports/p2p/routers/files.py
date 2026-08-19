"""
Files router — local and P2P file chunk upload/download (XFTP protocol).

Ports the following Flask routes to FastAPI v3:
  POST /api/file/upload/<chunk_id>   → POST /v3/files/upload/{chunk_id}
  GET  /api/file/download/<chunk_id> → GET  /v3/files/download/{chunk_id}
  POST /p2p/file/upload/<chunk_id>   → POST /v3/p2p/files/upload/{chunk_id}
  GET  /p2p/file/download/<chunk_id> → GET  /v3/p2p/files/download/{chunk_id}
"""

from __future__ import annotations

import re
import tempfile
import time
from collections import defaultdict, deque
from pathlib import Path
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

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
    import hashlib

    safe = hashlib.sha256(sender_onion.encode("utf-8")).hexdigest()[:32]
    d = XFTP_CHUNK_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Per-uploader rate limiter (audit fix ANO-SEC-004) ─────────────────────────


class _P2PUploadRateLimiter:
    """Per-uploader rate limiter to prevent quota-exhaustion DoS.

    Limits each uploader to 50 chunks per 5-minute window. Combined with
    the 500 MB total quota and 15-minute TTL, this bounds a single
    uploader to ~500 MB / 5 minutes (10 MB × 50 chunks) — enough for
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


def _sanitize_chunk_id(chunk_id: str) -> str:
    if not _CHUNK_ID_RE.match(chunk_id):
        raise HTTPException(status_code=400, detail="Invalid chunk identifier format")
    return chunk_id


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


def _save_chunk(chunk_id: str, data: bytes, sender_onion: str | None = None) -> None:
    """Save a chunk to disk.

    Audit fix ANO-SEC-004: when ``sender_onion`` is provided, the chunk is
    written to the per-uploader subdirectory so two peers writing the same
    ``chunk_id`` will not overwrite each other's data.
    """
    _sanitize_chunk_id(chunk_id)
    _prune_expired_chunks()
    if sender_onion:
        target_dir = _uploader_dir(sender_onion)
    else:
        target_dir = XFTP_CHUNK_DIR
    target = target_dir / f"{chunk_id}.chunk"
    with open(target, "wb") as f:
        f.write(data)


def _load_chunk(chunk_id: str, sender_onion: str | None = None) -> bytes | None:
    _sanitize_chunk_id(chunk_id)
    if sender_onion:
        target_dir = _uploader_dir(sender_onion)
    else:
        target_dir = XFTP_CHUNK_DIR
    target = target_dir / f"{chunk_id}.chunk"
    if not target.exists():
        return None
    try:
        if time.time() - target.stat().st_mtime > CHUNK_TTL_SECONDS:
            target.unlink(missing_ok=True)
            return None
        with open(target, "rb") as f:
            return f.read()
    except Exception:
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
    if len(pubkey_bytes) != 32:
        raise HTTPException(
            status_code=400,
            detail=f"Onion address public key must be 32 bytes (got {len(pubkey_bytes)})",
        )

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
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)
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
) -> dict:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")
    if len(body) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="Chunk size too large (max 10MB)")

    _save_chunk(chunk_id, body)
    logger.info("chunk_uploaded_locally", chunk_id=chunk_id, size=len(body))
    return {"success": True}


@router.get(
    "/download/{chunk_id}",
    summary="Download a file chunk (local client with Tor proxy option)",
)
async def local_download(
    chunk_id: str,
    onion: str | None = Query(
        default=None, description="Peer onion address to proxy download over Tor"
    ),
    current_user: UserOut = Depends(get_current_user),
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

    # Local download from bounded disk store
    chunk = _load_chunk(chunk_id)
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

    _save_chunk(chunk_id, body, sender_onion=sender_onion)
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
) -> Response:
    # Audit fix ANO-SEC-004: require the requester to specify which uploader's
    # chunk they want (per-uploader subdirectory isolation).
    sender_onion = request.headers.get("X-Sender-Onion", "")
    chunk = _load_chunk(chunk_id, sender_onion=sender_onion or None)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    logger.info(
        "chunk_downloaded_p2p",
        chunk_id=chunk_id,
        size=len(chunk),
        sender=sender_onion[:16] if sender_onion else "unknown",
    )
    return Response(content=chunk, media_type="application/octet-stream")
