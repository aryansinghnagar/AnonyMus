"""
FastAPI v3 application factory for the AnonyMus Relay server.

The relay is a public-facing (Tor hidden service) directory server that:
  - Maintains a live node registry (onion_address → last_seen)
  - Fan-outs presence events via SSE
  - Will proxy sealed-sender messages in Phase 5

Run standalone:
    uvicorn transports.relay.app_relay:app --reload --port 5002
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from core.config import settings
from core.logging_v3 import configure_logging, get_logger
from transports.relay.routers import nodes, presence

logger = get_logger(__name__)

# ── Prometheus ─────────────────────────────────────────────────────────────────

RELAY_REQUEST_COUNT = Counter(
    "anonymus_relay_http_requests_total",
    "Total relay HTTP requests",
    ["method", "path", "status_code"],
)
RELAY_LATENCY = Histogram(
    "anonymus_relay_http_request_duration_seconds",
    "Relay HTTP request latency",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI):
    configure_logging(log_level=settings.log_level, json_logs=settings.is_production)
    logger.info("relay_starting", environment=settings.environment)
    yield
    logger.info("relay_shutdown")


# ── App factory ────────────────────────────────────────────────────────────────


def create_relay_app() -> FastAPI:
    application = FastAPI(
        title="AnonyMus Relay v3",
        description="Onion node directory and presence relay",
        version="3.0.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Relay is public — any Tor client can register
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def _metrics_middleware(request: Request, call_next) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start
        RELAY_REQUEST_COUNT.labels(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        ).inc()
        RELAY_LATENCY.labels(method=request.method, path=request.url.path).observe(duration)
        return response

    @application.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("relay_unhandled_exception", path=request.url.path, error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    application.include_router(nodes.router)
    application.include_router(presence.router)

    @application.get("/healthz", tags=["observability"])
    async def healthz() -> dict:
        return {"status": "ok", "role": "relay"}

    @application.get("/metrics", tags=["observability"])
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return application


app = create_relay_app()
