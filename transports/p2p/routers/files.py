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
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from core.logging_v3 import get_logger
from transports.p2p.routers.auth import get_current_user, UserOut

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/files", tags=["files"])

_ONION_V3_RE = re.compile(r"^([a-z2-7]{56}\.onion)(?::([0-9]{1,5}))?$")

# In-memory chunk store (XFTP temporary storage)
# chunk_id -> bytes
_chunks: dict[str, bytes] = {}


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

    _chunks[chunk_id] = body
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

    # Local download from memory
    chunk = _chunks.get(chunk_id)
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
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")
    if len(body) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Chunk size too large")

    _chunks[chunk_id] = body
    logger.info("chunk_uploaded_p2p", chunk_id=chunk_id, size=len(body))
    return {"success": True}


@router.get(
    "/p2p/download/{chunk_id}",
    summary="Download a file chunk (inbound P2P over Tor)",
)
async def p2p_download(
    chunk_id: str,
) -> Response:
    chunk = _chunks.get(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    logger.info("chunk_downloaded_p2p", chunk_id=chunk_id, size=len(chunk))
    return Response(content=chunk, media_type="application/octet-stream")
