"""
FastAPI v3 application factory for the AnonyMus P2P node.

Runs alongside the legacy Flask/Socket.IO server in Phase 2a dual-stack mode.
All new routes are under /v3/ and /healthz, /readyz, /metrics.

Mount into the Flask app with a WSGIMiddleware, or run standalone with uvicorn:
    uvicorn transports.p2p.app_v3:app --reload --port 5001
"""

from __future__ import annotations

import asyncio
import threading

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.middleware.sessions import SessionMiddleware

from core.config import settings
from core.db.engine import engine
from core.logging_v3 import configure_logging, get_logger
from transports.p2p.routers import (
    auth,
    contacts,
    files,
    groups,
    keys,
    messages,
    notifications,
    node,
)

logger = get_logger(__name__)

# ── Prometheus Metrics ─────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "anonymus_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "anonymus_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)


# ── Rate Limiting Middleware ──────────────────────────────────────────────────


class RateLimiterMiddleware:
    """Simple self-contained in-memory rate-limiter ASGI middleware."""

    def __init__(self, app, max_requests: int = 120, period: float = 60.0):
        self.app = app
        self.max_requests = max_requests
        self.period = period
        self.requests = {}
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        ip = client[0] if client else "127.0.0.1"

        path = scope.get("path", "")
        if path in ("/healthz", "/readyz", "/metrics"):
            await self.app(scope, receive, send)
            return

        now = time.time()
        with self.lock:
            timestamps = self.requests.get(ip, [])
            timestamps = [t for t in timestamps if now - t < self.period]
            if len(timestamps) >= self.max_requests:
                from fastapi.responses import JSONResponse

                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                )
                await response(scope, receive, send)
                return
            timestamps.append(now)
            self.requests[ip] = timestamps

        await self.app(scope, receive, send)


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run migrations and Tor transport on startup, clean up on shutdown."""
    configure_logging(
        log_level=settings.log_level,
        json_logs=settings.is_production,
    )
    logger.info(
        "anonymus_v3_starting",
        environment=settings.environment,
        database_url=settings.database_url.split("@")[-1],
    )

    try:
        from alembic.config import Config
        from alembic import command

        logger.info("running_alembic_migrations")

        def run_migrations():
            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, "head")

        await asyncio.to_thread(run_migrations)
        logger.info("alembic_migrations_completed")
    except Exception as e:
        logger.error("alembic_migrations_failed", error=str(e))

    p2p_transport = None
    import os
    import sys

    is_test_env = (
        settings.is_test
        or os.environ.get("TESTING") == "True"
        or "pytest" in sys.modules
    )

    if settings.tor_enabled and not is_test_env:
        try:
            from transports.p2p.adapter import P2PTransport

            p2p_transport = P2PTransport()
            logger.info("starting_p2p_transport_tor", port=settings.port)
            p2p_transport.start({"PORT": settings.port})
            logger.info("p2p_transport_tor_started", onion=p2p_transport.onion_address)
        except Exception as e:
            logger.error("p2p_transport_tor_startup_failed", error=str(e))

    zeroconf_instance = None
    if os.environ.get("ANONYMUS_MDNS", "false").lower() == "true" and not is_test_env:
        try:
            from zeroconf import ServiceInfo, Zeroconf
            import socket
            from sqlalchemy import select

            def get_local_ip():
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("10.255.255.255", 1))
                    ip = s.getsockname()[0]
                except Exception:
                    ip = "127.0.0.1"
                finally:
                    s.close()
                return ip

            user_onion = None
            try:
                from sqlalchemy.ext.asyncio import AsyncSession
                from core.db.models import User

                async with AsyncSession(engine) as db_session:
                    user = await db_session.scalar(select(User).limit(1))
                    if user:
                        user_onion = user.onion_address
            except Exception as db_err:
                logger.warning("mdns_db_query_failed", error=str(db_err))

            local_ip = get_local_ip()
            zeroconf_instance = Zeroconf()
            info = ServiceInfo(
                "_anonymus._tcp.local.",
                f"AnonyMus Peer {settings.port}._anonymus._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=settings.port,
                properties={"onion": user_onion or ""},
            )
            zeroconf_instance.register_service(info)
            logger.info(
                "mdns_advertised",
                service="_anonymus._tcp.local.",
                ip=local_ip,
                port=settings.port,
            )
        except Exception as e:
            logger.error("mdns_advertisement_failed", error=str(e))

    yield

    if zeroconf_instance:
        try:
            logger.info("stopping_mdns_advertisement")
            zeroconf_instance.close()
            logger.info("mdns_advertisement_stopped")
        except Exception as e:
            logger.error("mdns_shutdown_failed", error=str(e))

    if p2p_transport:
        try:
            logger.info("stopping_p2p_transport_tor")
            p2p_transport.stop()
            logger.info("p2p_transport_tor_stopped")
        except Exception as e:
            logger.error("p2p_transport_tor_shutdown_failed", error=str(e))

    await engine.dispose()
    logger.info("anonymus_v3_shutdown")


# ── App Factory ────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    application = FastAPI(
        title="AnonyMus API v3",
        description="Privacy-first encrypted messaging — FastAPI backend",
        version="3.0.0",
        docs_url="/v3/docs" if settings.is_development else None,
        redoc_url="/v3/redoc" if settings.is_development else None,
        openapi_url="/v3/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="strict",
        https_only=settings.is_production,
    )
    application.add_middleware(RateLimiterMiddleware, max_requests=120, period=60.0)

    # ── Prometheus timing middleware ───────────────────────────────────────────
    @application.middleware("http")
    async def _metrics_middleware(request: Request, call_next) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start
        REQUEST_COUNT.labels(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            path=request.url.path,
        ).observe(duration)
        return response

    # ── Exception Handlers ─────────────────────────────────────────────────────
    @application.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error("unhandled_exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # ── V3 API Routers ─────────────────────────────────────────────────────────
    application.include_router(auth.router)
    application.include_router(contacts.router)
    application.include_router(messages.router)
    application.include_router(groups.router)
    # Phase 2b — new routers (node info, notifications, pre-key bundles)
    application.include_router(node.router)
    application.include_router(notifications.router)
    application.include_router(keys.router)
    application.include_router(files.router)
    from transports.p2p.routers import p2p, profiles, sync, supporter, compat

    application.include_router(p2p.router)
    application.include_router(profiles.router)
    application.include_router(sync.router)
    application.include_router(supporter.router)
    application.include_router(compat.router)

    # ── Observability Endpoints ────────────────────────────────────────────────
    @application.get("/healthz", tags=["observability"], summary="Liveness probe")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.get(
        "/readyz", tags=["observability"], summary="Readiness probe — checks DB"
    )
    async def readyz() -> dict[str, Any]:
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    __import__("sqlalchemy", fromlist=["text"]).text("SELECT 1")
                )
            return {"status": "ready", "database": "ok"}
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "database": str(exc)},
            )

    @application.get("/metrics", tags=["observability"], summary="Prometheus metrics")
    async def metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    # ── Socket.IO ASGI mount ───────────────────────────────────────────────────
    from transports.p2p.socket_v3 import socket_app

    application.mount("/socket.io", socket_app)

    return application


# Module-level app instance for uvicorn / granian
app = create_app()
