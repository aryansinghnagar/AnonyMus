"""
Node router — local node information, Tor status, and invite system.

Ports the following Flask routes to FastAPI v3:
  GET  /api/my_info                  → GET  /v3/node/info
  POST /api/contacts/generate_invite → POST /v3/node/invite
  POST /api/contacts/accept_invite   → POST /v3/node/invite/accept
  POST /api/reset-data               → POST /v3/node/reset
  GET  /api/settings/preferred_relay → GET  /v3/node/settings/relay
  POST /api/settings/preferred_relay → POST /v3/node/settings/relay
"""

from __future__ import annotations

import os
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session
from core.logging_v3 import get_logger
from transports.p2p.routers.auth import get_current_user, UserOut

logger = get_logger(__name__)
router = APIRouter(prefix="/v3/node", tags=["node"])

ONION_RE = re.compile(r"^[a-z2-7]{16,56}\.onion$")

# ── Schemas ────────────────────────────────────────────────────────────────────


class NodeInfoResponse(BaseModel):
    onion_address: str | None
    username: str


class GenerateInviteResponse(BaseModel):
    invite_onion: str
    service_name: str
    token: str


class AcceptInviteRequest(BaseModel):
    invite_onion: str = Field(min_length=16, max_length=128)
    nickname: str = Field(min_length=1, max_length=50)
    my_public_key: str = Field(min_length=1, max_length=5000)

    @field_validator("invite_onion")
    @classmethod
    def validate_onion(cls, v: str) -> str:
        v = v.strip().lower()
        if not ONION_RE.match(v):
            raise ValueError("Invalid onion address")
        return v

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9._\- @()]+$", v):
            raise ValueError("Nickname contains invalid characters")
        return v


class RelaySettingRequest(BaseModel):
    preferred_file_relay: str = Field(default="", max_length=512)

    @field_validator("preferred_file_relay")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("preferred_file_relay must be an HTTP/HTTPS URL")
        return v


class RelaySettingResponse(BaseModel):
    preferred_file_relay: str


class ResetRequest(BaseModel):
    confirm: str = Field(min_length=5, max_length=5)


# ── In-process config store (mirrors v1 database.get/set_config) ──────────────
# In a full migration this will be backed by the relay DB table.
_config: dict[str, str] = {}


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get(
    "/info",
    response_model=NodeInfoResponse,
    summary="Get local node onion address and username",
)
async def get_node_info(
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NodeInfoResponse:
    onion = current_user.onion_address
    if not onion:
        import transports.p2p.database as legacy_db

        onion = legacy_db.get_config("my_onion_address", None)
        if onion:
            current_user.onion_address = onion
            session.add(current_user)
            await session.commit()
    return NodeInfoResponse(onion_address=onion, username=current_user.username)


import asyncio


@router.post(
    "/invite",
    response_model=GenerateInviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a pairwise invite link (spawns a new hidden service)",
)
async def generate_invite(
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GenerateInviteResponse:
    token = secrets.token_urlsafe(12)
    service_name = f"inv_{token}"

    from transports.p2p.tor_manager import add_onion_service

    try:
        onion = await asyncio.to_thread(add_onion_service, service_name)
    except Exception as e:
        logger.error("failed_to_spawn_invite_onion", error=str(e))
        onion = current_user.onion_address or "pending.onion"

    logger.info("invite_generated", service_name=service_name, invite_onion=onion)
    return GenerateInviteResponse(
        invite_onion=onion,
        service_name=service_name,
        token=token,
    )


@router.post(
    "/invite/accept",
    summary="Accept a pairwise invite link and initiate the X3DH handshake",
)
async def accept_invite(
    body: AcceptInviteRequest,
    current_user: UserOut = Depends(get_current_user),
) -> dict:
    # Placeholder: in Phase 5 this triggers X3DH + pre-key bundle exchange.
    logger.info("invite_accepted", invite_onion=body.invite_onion[:12])
    return {"success": True, "invite_onion": body.invite_onion}


@router.get(
    "/settings/relay",
    response_model=RelaySettingResponse,
    summary="Get preferred file-relay URL",
)
async def get_relay_setting(
    current_user: UserOut = Depends(get_current_user),
) -> RelaySettingResponse:
    return RelaySettingResponse(
        preferred_file_relay=current_user.preferred_file_relay or ""
    )


@router.post(
    "/settings/relay",
    response_model=RelaySettingResponse,
    summary="Set preferred file-relay URL",
)
async def set_relay_setting(
    body: RelaySettingRequest,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RelaySettingResponse:
    current_user.preferred_file_relay = body.preferred_file_relay
    session.add(current_user)
    await session.commit()
    return RelaySettingResponse(preferred_file_relay=body.preferred_file_relay)


@router.post(
    "/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Wipe all local data — IRREVERSIBLE",
)
async def reset_data(
    body: ResetRequest,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if body.confirm != "RESET":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation phrase 'RESET' is required",
        )
    logger.warning("data_reset", username=current_user.username)

    from core.db.models import Contact, Message

    await session.execute(
        delete(Message).where(
            (Message.sender_onion == current_user.onion_address)
            | (Message.recipient_onion == current_user.onion_address)
        )
    )
    await session.execute(
        delete(Contact).where(Contact.owner_onion == current_user.onion_address)
    )

    current_user.preferred_file_relay = ""
    current_user.onion_address = None
    session.add(current_user)
    await session.commit()

    import transports.p2p.database as legacy_db

    legacy_db.close_pool()
    if os.path.exists(legacy_db.DB_FILE):
        try:
            os.remove(legacy_db.DB_FILE)
        except Exception:
            pass
    _config.clear()


@router.get(
    "/tor/status",
    summary="Get Tor background process status",
)
async def get_tor_status(
    current_user: UserOut = Depends(get_current_user),
) -> dict:
    try:
        from transports.p2p.tor_manager import tor_process, SOCKS_PORT

        is_running = tor_process is not None and tor_process.poll() is None
        return {
            "is_running": is_running,
            "socks_port": SOCKS_PORT if is_running else None,
        }
    except Exception as e:
        return {"is_running": False, "error": str(e)}


@router.post(
    "/tor/restart",
    summary="Restart background Tor service",
)
async def restart_tor(
    current_user: UserOut = Depends(get_current_user),
) -> dict:
    try:
        from transports.p2p.tor_manager import cleanup, launch_tor, PEER_PORT

        cleanup()
        import threading

        def do_restart():
            try:
                launch_tor(PEER_PORT)
            except Exception as ex:
                logger.error("tor_restart_failed", error=str(ex))

        threading.Thread(target=do_restart, daemon=True).start()
        return {"success": True, "message": "Tor restart initiated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart Tor: {e}")


@router.get(
    "/lan_peers",
    summary="Discover active peers on the local area network (LAN) via mDNS",
)
async def get_lan_peers(
    current_user: UserOut = Depends(get_current_user),
) -> list:
    try:
        from zeroconf import Zeroconf, ServiceBrowser
        import socket
        import asyncio

        class MyListener:
            def __init__(self):
                self.services = []

            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info:
                    ips = [socket.inet_ntoa(addr) for addr in info.addresses]
                    onion = info.properties.get(b"onion", b"").decode("utf-8")
                    self.services.append(
                        {
                            "name": name,
                            "ip": ips[0] if ips else "127.0.0.1",
                            "port": info.port,
                            "onion": onion,
                        }
                    )

            def update_service(self, zc, type_, name):
                pass

            def remove_service(self, zc, type_, name):
                pass

        zc = Zeroconf()
        listener = MyListener()
        browser = ServiceBrowser(zc, "_anonymus._tcp.local.", listener)
        await asyncio.sleep(1.5)
        zc.close()
        return listener.services
    except Exception as e:
        logger.error("lan_discovery_failed", error=str(e))
        return []


@router.post(
    "/obliviate",
    summary="Obliviate Panic Wipe — secure zeroization of database and cryptographic identity keys",
)
async def obliviate(
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    logger.critical("obliviate_panic_wipe_initiated")
    import os
    import time
    import shutil
    from core.config import settings
    from core.db.engine import engine

    # 1. Stop active Tor processes
    try:
        from transports.p2p.tor_manager import cleanup

        cleanup()
    except Exception as e:
        logger.error("panic_wipe_tor_cleanup_failed", error=str(e))

    # Close DB connection pool immediately
    await session.close()
    await engine.dispose()

    # 2. Secure overwrite and delete helper
    def secure_wipe_file(filepath: str):
        if os.path.exists(filepath):
            try:
                size = os.path.getsize(filepath)
                if size > 0:
                    with open(filepath, "ba+", buffering=0) as f:
                        f.seek(0)
                        f.write(os.urandom(size))
                        f.flush()
                os.remove(filepath)
            except Exception as ex:
                logger.error("panic_wipe_file_failed", path=filepath, error=str(ex))

    def secure_wipe_dir(dirpath: str):
        if os.path.exists(dirpath):
            for root, dirs, files in os.walk(dirpath, topdown=False):
                for file in files:
                    secure_wipe_file(os.path.join(root, file))
                for d in dirs:
                    try:
                        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                    except Exception:
                        pass
            try:
                shutil.rmtree(dirpath, ignore_errors=True)
            except Exception:
                pass

    # Determine SQLite file paths
    db_url = settings.database_url
    db_path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    db_path = os.path.abspath(db_path)

    db_files = [db_path, f"{db_path}-wal", f"{db_path}-shm", f"{db_path}-journal"]

    # 3. Perform file zeroization
    for f in db_files:
        secure_wipe_file(f)

    # 4. Wipe Tor directories
    from transports.p2p.tor_manager import TOR_DATA_DIR, TOR_SERVICES_PARENT_DIR

    secure_wipe_dir(TOR_DATA_DIR)
    secure_wipe_dir(TOR_SERVICES_PARENT_DIR)

    # 5. Shut down server in a background thread to allow response to return
    def exit_process():
        time.sleep(0.5)
        os._exit(0)

    import threading

    threading.Thread(target=exit_process, daemon=True).start()

    return {"success": True, "message": "Panic wipe completed, server shutting down."}
