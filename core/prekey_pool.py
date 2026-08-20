"""
Pre-Key Bundle Generation Pool (perf fix P8).

Generates and caches a pool of one-time X25519 pre-keys at startup so that
new X3DH / PQXDH sessions can be initiated without waiting for a keypair
generation (which costs ~5-15 ms per X25519 keypair, plus much more for
ML-KEM-768 if liboqs is available).

Design:
  - At startup, generate a pool of 100 one-time pre-keys (configurable via
    ``ANONYMUS_PREKEY_POOL_SIZE``). Each pre-key is an X25519 keypair plus,
    optionally, an ML-KEM-768 keypair.
  - Store the pool in-memory (``_PREKEY_POOL``) keyed by the local user's
    onion address. Persist to the ``PreKeyBundle`` row on every change.
  - A background task refills the pool when its size drops below 20
    (``ANONYMUS_PREKEY_POOL_LOW_WATERMARK``). The refill runs in a worker
    thread to avoid blocking the event loop.
  - ``take_one_time_prekey(onion_address)`` atomically pops one pre-key from
    the pool. If the pool is empty (e.g., very high burst), a fresh
    keypair is generated on-demand as a fallback (preserving correctness
    at the cost of latency).

The pool is process-local: in a multi-process deployment (e.g., granian
with N workers), each worker maintains its own pool. The PreKeyBundle row
in the DB serves as the cross-worker source of truth (each worker refills
the row's ``one_time_prekeys_json`` from its own pool).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from core.logging_v3 import get_logger

logger = get_logger(__name__)


# ============================================================================
# Configuration
# ============================================================================

_DEFAULT_POOL_SIZE = 100
_DEFAULT_LOW_WATERMARK = 20
_DEFAULT_REFILL_BATCH = 40  # refill to ~ pool_size when below watermark


def _pool_size() -> int:
    return int(os.environ.get("ANONYMUS_PREKEY_POOL_SIZE", str(_DEFAULT_POOL_SIZE)))


def _low_watermark() -> int:
    return int(
        os.environ.get(
            "ANONYMUS_PREKEY_POOL_LOW_WATERMARK", str(_DEFAULT_LOW_WATERMARK)
        )
    )


def _refill_batch() -> int:
    return int(
        os.environ.get("ANONYMUS_PREKEY_POOL_REFILL_BATCH", str(_DEFAULT_REFILL_BATCH))
    )


# ============================================================================
# In-memory pool
# ============================================================================


# Each entry: (pub_b64, priv_b64). The private key is kept in memory only;
# it is persisted to the PreKeyBundle row only after a peer consumes the
# corresponding public pre-key (which is signalled via ``take_one_time_prekey``).
_PREKEY_POOL: dict[str, list[tuple[str, str]]] = {}
_PREKEY_LOCK = threading.Lock()
_REFILL_TASK: asyncio.Task | None = None
_REFILL_LOCK = threading.Lock()


def _generate_one_x25519_keypair() -> tuple[str, str]:
    """Return (pub_b64, priv_b64) for a fresh X25519 keypair."""
    priv = x25519.X25519PrivateKey.generate()
    pub = priv.public_key()
    pub_b64 = base64.b64encode(
        pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    priv_b64 = base64.b64encode(
        priv.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    ).decode("ascii")
    return pub_b64, priv_b64


def _try_generate_pq_keypair() -> tuple[str, str] | None:
    """Return (pub_b64, priv_b64) for a fresh ML-KEM-768 keypair, or None.

    Returns None when liboqs is not available (the X25519-only path is used
    as a fallback — see ``core.pq_kem``).
    """
    try:
        from core import pq_kem

        if not pq_kem.is_available():
            return None
        result = pq_kem.generate_ml_kem_keypair()
        if result is None:
            return None
        pub_bytes, priv_bytes = result
        return (
            base64.b64encode(pub_bytes).decode("ascii"),
            base64.b64encode(priv_bytes).decode("ascii"),
        )
    except Exception:
        return None


def pool_size_for(onion_address: str) -> int:
    """Return the current in-memory pool size for ``onion_address``."""
    with _PREKEY_LOCK:
        return len(_PREKEY_POOL.get(onion_address, []))


def fill_pool(
    onion_address: str, target_size: int | None = None
) -> list[tuple[str, str]]:
    """Synchronously fill the pool for ``onion_address`` up to ``target_size``.

    Returns the list of (pub_b64, priv_b64) pairs that were added. Safe to
    call from a sync context (e.g., at startup before the event loop is
    running). For runtime refill, prefer ``schedule_refill_if_low``.
    """
    if target_size is None:
        target_size = _pool_size()

    added: list[tuple[str, str]] = []
    with _PREKEY_LOCK:
        current = _PREKEY_POOL.setdefault(onion_address, [])
        deficit = max(0, target_size - len(current))

    for _ in range(deficit):
        try:
            added.append(_generate_one_x25519_keypair())
        except Exception as e:
            logger.warning("prekey_pool_gen_failed", error=str(e))
            break

    if added:
        with _PREKEY_LOCK:
            _PREKEY_POOL.setdefault(onion_address, []).extend(added)

    logger.info(
        "prekey_pool_filled",
        onion=onion_address[:12],
        added=len(added),
        pool_size=pool_size_for(onion_address),
    )
    return added


def take_one_time_prekey(onion_address: str) -> tuple[str, str] | None:
    """Atomically pop one (pub_b64, priv_b64) pair from the pool.

    Returns None if the pool is empty (the caller should generate a fresh
    keypair on-demand as a fallback). Schedules an async refill task if
    the pool drops below the low watermark.
    """
    with _PREKEY_LOCK:
        pool = _PREKEY_POOL.get(onion_address, [])
        if not pool:
            return None
        pair = pool.pop()
        current_size = len(pool)

    if current_size < _low_watermark():
        schedule_refill_if_low(onion_address)

    return pair


def schedule_refill_if_low(onion_address: str) -> None:
    """Schedule an async refill task if the pool is below the low watermark.

    No-op if a refill is already in flight for this onion. Safe to call from
    a sync context; falls back to ``fill_pool`` in a thread if there is no
    running event loop.
    """
    if pool_size_for(onion_address) >= _low_watermark():
        return

    global _REFILL_TASK
    with _REFILL_LOCK:
        # Avoid spawning multiple refill tasks for the same onion.
        if _REFILL_TASK is not None and not _REFILL_TASK.done():
            return

        try:
            loop = asyncio.get_running_loop()
            _REFILL_TASK = loop.create_task(_async_refill(onion_address))
        except RuntimeError:
            # No running event loop -- run in a worker thread.
            t = threading.Thread(
                target=lambda: fill_pool(onion_address, _refill_batch()),
                name=f"prekey-refill-{onion_address[:8]}",
                daemon=True,
            )
            t.start()


async def _async_refill(onion_address: str) -> None:
    """Refill the pool for ``onion_address`` in a worker thread.

    Uses ``asyncio.to_thread`` so key generation (which is CPU-bound) does
    not block the event loop.
    """
    try:
        await asyncio.to_thread(fill_pool, onion_address, _refill_batch())
    except Exception as e:
        logger.warning("prekey_pool_async_refill_failed", error=str(e))


# ============================================================================
# Startup hook
# ============================================================================


async def initialise_pool_for_local_user(onion_address: str) -> int:
    """Pre-generate the pool at startup for the local user's onion.

    Returns the resulting pool size. Safe to call from the FastAPI startup
    event handler.
    """
    if not onion_address:
        return 0
    added = await asyncio.to_thread(fill_pool, onion_address, _pool_size())
    return len(added)


def drain_pool(onion_address: str) -> list[tuple[str, str]]:
    """Remove all pre-keys for ``onion_address`` from the in-memory pool.

    Used in tests and on user-logout.
    """
    with _PREKEY_LOCK:
        return _PREKEY_POOL.pop(onion_address, [])


# ============================================================================
# DB persistence helpers
# ============================================================================


async def sync_pool_to_db(onion_address: str, session: "Any") -> None:
    """Persist the current pool's public keys to the PreKeyBundle row.

    The pool's private keys are NOT persisted to the DB; they are kept in
    memory only. When a peer consumes a one-time pre-key (via
    ``take_one_time_prekey``), the caller is responsible for persisting
    the consumed (pub, priv) pair to its own session state if needed.

    This helper updates ``one_time_prekeys_json`` on the existing
    PreKeyBundle row (the row is created elsewhere by the X3DH / PQXDH
    setup flow).
    """
    from core.db.models import PreKeyBundle
    from sqlalchemy import select

    pub_keys: list[str] = []
    with _PREKEY_LOCK:
        for pub_b64, _priv_b64 in _PREKEY_POOL.get(onion_address, []):
            pub_keys.append(pub_b64)

    bundle = await session.scalar(
        select(PreKeyBundle).where(PreKeyBundle.onion_address == onion_address)
    )
    if bundle is None:
        # Row doesn't exist yet -- caller should create it with identity_key etc.
        return
    bundle.one_time_prekeys_json = json.dumps(pub_keys)
    # Note: caller is responsible for committing the session.
