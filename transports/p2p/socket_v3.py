"""
Socket.IO ASGI module for AnonyMus v3.

Migrates flask-socketio to python-socketio[asgi] using native asyncio.
Provides a global Socket.IO server mounted on FastAPI.
"""

from __future__ import annotations

import socketio
from core.logging_v3 import get_logger

logger = get_logger(__name__)

# Create the async Socket.IO server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",  # Configured to match FastAPI CORS
)

# Wrap it in an ASGI application
socket_app = socketio.ASGIApp(sio)


@sio.event
async def connect(sid: str, environ: dict) -> None:
    logger.info("socket_connected", sid=sid)


@sio.event
async def disconnect(sid: str) -> None:
    logger.info("socket_disconnected", sid=sid)


async def emit_socket(event: str, data: dict) -> None:
    """Helper to broadcast messages to all connected web/desktop clients."""
    logger.debug("socket_emit", event=event, data=data)
    await sio.emit(event, data)
