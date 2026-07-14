"""
Sync router — handles local device synchronization and pairing broker servers.
"""

from __future__ import annotations

import os
import asyncio
import socket
import base64
import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import requests
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
pairing_lock = threading.Lock()


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


# ── Schemas ────────────────────────────────────────────────────────────────────


class PushSyncRequest(BaseModel):
    ip: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    k: str = Field(min_length=1)


class PairingHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Suppress standard HTTP log clutter
        pass

    def do_POST(self) -> None:
        global pairing_private_key
        if self.path == "/api/sync/pairing":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            try:
                if pairing_private_key is None:
                    raise ValueError("Pairing server keys not initialized")

                payload = json.loads(post_data.decode("utf-8"))
                client_pub_b64 = payload.get("client_public_key")
                ciphertext_b64 = payload.get("ciphertext")
                iv_b64 = payload.get("iv")

                peer_pub = x25519.X25519PublicKey.from_public_bytes(
                    base64.b64decode(client_pub_b64)
                )
                shared_key = pairing_private_key.exchange(peer_pub)

                aes_key = HKDF(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=None,
                    info=b"AnonyMus-Device-Sync-Key",
                ).derive(shared_key)

                aesgcm = AESGCM(aes_key)
                decrypted = aesgcm.decrypt(
                    base64.b64decode(iv_b64), base64.b64decode(ciphertext_b64), None
                )

                db_path = get_db_path()
                if os.path.exists(db_path):
                    shutil.copyfile(db_path, db_path + ".bak")

                with open(db_path, "wb") as f:
                    f.write(decrypted)

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"success": true}')
                logger.info("sync_pairing_db_successfully_restored", db_path=db_path)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode())
                logger.error("sync_pairing_failed", error=str(e))
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

    global active_pairing_broker, pairing_private_key

    with pairing_lock:
        ip = get_local_ip()
        port = 8999

        if active_pairing_broker is not None and pairing_private_key is not None:
            pub_bytes = pairing_private_key.public_key().public_bytes_raw()
            pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")
            return {"success": True, "ip": ip, "port": port, "k": pub_b64}

        pairing_private_key = x25519.X25519PrivateKey.generate()
        pub_bytes = pairing_private_key.public_key().public_bytes_raw()
        pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")

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
        return {"success": True, "ip": ip, "port": port, "k": pub_b64}


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

        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
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
        }

        # Run POST request in a background thread to prevent blocking
        def do_post() -> requests.Response:
            return requests.post(
                f"http://{body.ip}:{body.port}/api/sync/pairing",
                json=payload,
                timeout=20,
            )

        loop = Request.scope.get("fastapi_astack")
        # Direct requests execution
        res = await asyncio.to_thread(do_post)

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
