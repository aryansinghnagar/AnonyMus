"""
Application settings for AnonyMus v3.

All values are read from environment variables (or .env file via pydantic-settings).

Perf fix P7: supports hot-reload of the .env file. When the file changes on
disk, registered listeners are notified so they can re-initialise subsystems
(database engine, Tor manager, logger, etc.) without restarting the process.
The hot-reload is opt-in via ``settings.enable_config_hot_reload`` (default
False) and starts a background thread that uses the ``watchdog`` library
(which is already a transitive dependency via ``uvicorn[standard]``).
"""

from __future__ import annotations

import os
import threading
from enum import StrEnum
from typing import Callable

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"
    # Audit fix ANO-V2-NEW-007: alias "testing" to TEST so CI's ANONYMUS_ENV=testing works
    TESTING = "testing"


class Settings(BaseSettings):
    """Unified settings — replaces the ad-hoc os.getenv() calls scattered across the codebase."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=False)
    secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION", description="Flask/FastAPI session secret"
    )

    # ── Server ─────────────────────────────────────────────────────────────────
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=5000, ge=1, le=65535)
    workers: int = Field(default=1, ge=1)

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./anonymus.db",
        description="SQLAlchemy async DB URL (sqlite+aiosqlite:// or postgresql+asyncpg://)",
    )
    db_key: str = Field(
        default="",
        description="SQLCipher passphrase / DB encryption key (leave empty to disable encryption)",
    )

    # ── Tor ────────────────────────────────────────────────────────────────────
    tor_enabled: bool = Field(default=True)
    tor_control_port: int = Field(default=9051)
    tor_socks_port: int = Field(default=9050)

    # ── Rate Limiting ──────────────────────────────────────────────────────────
    rate_limit_default: str = Field(default="60/minute")
    rate_limit_auth: str = Field(default="10/minute")

    # ── Observability ──────────────────────────────────────────────────────────
    sentry_dsn: str = Field(default="", description="Sentry DSN (empty = disabled)")
    otel_endpoint: str = Field(
        default="", description="OpenTelemetry collector endpoint"
    )
    log_level: str = Field(default="INFO")

    # ── Feature Flags ──────────────────────────────────────────────────────────
    enable_v3_api: bool = Field(
        default=True,
        description="Mount the FastAPI v3 router alongside the legacy Flask app",
    )
    enable_config_hot_reload: bool = Field(
        default=False,
        description=(
            "Perf fix P7: if True, the .env file is watched for changes and "
            "registered listeners are notified so subsystems can reload."
        ),
    )

    @field_validator("secret_key")
    @classmethod
    def _secret_key_not_default_in_prod(cls, v: str, info) -> str:
        # Validated at startup — prevents shipping with the placeholder key.
        if v == "CHANGE_ME_IN_PRODUCTION":
            import os

            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                raise ValueError("SECRET_KEY must be set in production")
        return v

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_test(self) -> bool:
        return self.environment in (Environment.TEST, Environment.TESTING)


# Module-level singleton — import anywhere as `from core.config import settings`
settings = Settings()


# ============================================================================
# Perf fix P7: Config hot-reload via watchdog file watching.
# ============================================================================
#
# Subsystems that hold long-lived references to ``settings`` (e.g., the
# SQLAlchemy engine, the Tor manager, the logger) cannot transparently
# re-read env vars when .env changes. The hot-reload mechanism solves this
# by:
#   1. Watching the .env file with ``watchdog`` (a transitive dependency
#      via ``uvicorn[standard]`` → ``watchfiles``).
#   2. When .env changes, re-instantiating ``Settings()`` and copying the
#      new field values into the existing ``settings`` singleton's
#      ``__dict__`` in-place (so existing references stay valid).
#   3. Notifying registered listeners via the ``_config_change_listeners``
#      registry so they can re-initialise their state (e.g., the DB engine
#      can be disposed and recreated with a new pool_size).
#
# Hot-reload is OPT-IN via ``enable_config_hot_reload=True`` (default False)
# so production deployments that prefer the restart-on-config-change pattern
# are not surprised by in-process mutations.


_config_change_listeners: list[Callable[[Settings], None]] = []
_config_change_lock = threading.Lock()
_config_watcher_thread: threading.Thread | None = None
_config_watcher_stop_event: threading.Event | None = None


def register_config_change_listener(listener: Callable[[Settings], None]) -> None:
    """Register a callback invoked when the .env file changes.

    The callback receives the (mutated in-place) ``settings`` singleton.
    Callbacks are invoked sequentially on the watcher thread; long-running
    work should be offloaded to a worker.
    """
    with _config_change_lock:
        _config_change_listeners.append(listener)


def _reload_settings_in_place() -> None:
    """Re-read .env into a new ``Settings()`` and copy fields into ``settings``.

    This mutates the existing ``settings`` singleton's ``__dict__`` in-place
    so existing module-level references (``from core.config import settings``)
    continue to work.
    """
    try:
        new_settings = Settings()  # re-reads .env
    except Exception as e:
        # Don't crash the watcher thread; just log.
        import logging

        logging.getLogger(__name__).warning("config_hot_reload_failed", error=str(e))
        return

    # Mutate in place so existing references stay valid.
    settings.__dict__.update(new_settings.__dict__)

    # Notify listeners.
    with _config_change_lock:
        listeners = list(_config_change_listeners)
    for listener in listeners:
        try:
            listener(settings)
        except Exception:
            pass  # Listener errors must not kill the watcher.


def start_config_hot_reload(env_file: str = ".env") -> None:
    """Start a background thread that watches ``env_file`` for changes.

    No-op if ``settings.enable_config_hot_reload`` is False or if the
    watcher is already running. Safe to call multiple times.
    """
    global _config_watcher_thread, _config_watcher_stop_event

    if not settings.enable_config_hot_reload:
        return
    if _config_watcher_thread is not None and _config_watcher_thread.is_alive():
        return

    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        # watchdog not installed — hot-reload is best-effort.
        return

    env_path = os.path.abspath(env_file)
    if not os.path.exists(env_path):
        return

    class _EnvChangeHandler(FileSystemEventHandler):
        def __init__(self_inner) -> None:
            super().__init__()
            self_inner._last_event_time: float = 0.0

        def on_modified(self_inner, event) -> None:  # type: ignore[override]
            if event.is_directory or os.path.abspath(event.src_path) != env_path:
                return
            # Debounce: editors often fire multiple on_modified events in
            # quick succession (one per fsync). Only reload if at least 500 ms
            # has passed since the last event.
            import time

            now = time.monotonic()
            if now - self_inner._last_event_time < 0.5:
                return
            self_inner._last_event_time = now
            _reload_settings_in_place()

    stop_event = threading.Event()
    observer = Observer()
    observer.schedule(_EnvChangeHandler(), os.path.dirname(env_path), recursive=False)

    def _run():
        observer.start()
        try:
            while not stop_event.is_set():
                stop_event.wait(timeout=1.0)
        finally:
            observer.stop()
            observer.join(timeout=2.0)

    _config_watcher_stop_event = stop_event
    _config_watcher_thread = threading.Thread(
        target=_run, name="anonymus-config-watcher", daemon=True
    )
    _config_watcher_thread.start()


def stop_config_hot_reload() -> None:
    """Stop the config watcher (mainly used in tests)."""
    global _config_watcher_thread, _config_watcher_stop_event
    if _config_watcher_stop_event is not None:
        _config_watcher_stop_event.set()
    if _config_watcher_thread is not None:
        _config_watcher_thread.join(timeout=3.0)
        _config_watcher_thread = None
    _config_watcher_stop_event = None


# Auto-start hot-reload if explicitly enabled via env var.
if settings.enable_config_hot_reload:
    start_config_hot_reload()
