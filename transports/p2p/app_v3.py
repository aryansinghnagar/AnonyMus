"""
FastAPI v3 application factory for the AnonyMus P2P node.

Runs alongside the legacy Flask/Socket.IO server in Phase 2a dual-stack mode.
All new routes are under /v3/ and /healthz, /readyz, /metrics.

Mount into the Flask app with a WSGIMiddleware, or run standalone with uvicorn:
    uvicorn transports.p2p.app_v3:app --reload --port 5001
"""

from __future__ import annotations

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
from core.db.models import Base
from core.logging_v3 import configure_logging, get_logger
from transports.p2p.routers import auth, contacts, groups, messages

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


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create tables on startup, clean up on shutdown."""
    configure_logging(
        log_level=settings.log_level,
        json_logs=settings.is_production,
    )
    logger.info(
        "anonymus_v3_starting",
        environment=settings.environment,
        database_url=settings.database_url.split("@")[-1],  # redact credentials
    )

    async with engine.begin() as conn:
        # In Phase 2a we create tables if they don't exist.
        # Phase 2c switches to Alembic migrations for schema management.
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database_tables_ready")
    yield
    # Dispose of the connection pool on shutdown
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
        allow_origins=["http://127.0.0.1:*", "http://localhost:*"],
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
    v3_prefix = "/v3"
    application.include_router(auth.router, prefix=v3_prefix)
    application.include_router(contacts.router, prefix=v3_prefix)
    application.include_router(messages.router, prefix=v3_prefix)
    application.include_router(groups.router, prefix=v3_prefix)

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

    return application


# Module-level app instance for uvicorn / granian
app = create_app()
