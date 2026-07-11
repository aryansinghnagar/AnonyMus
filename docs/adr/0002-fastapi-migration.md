# ADR-0002: Migrate Python Backend from Flask/eventlet to FastAPI/granian

**Date:** 2026-07-11
**Status:** Accepted
**Deciders:** AnonyMus Core Team

## Context

The AnonyMus v1.0 Python backend runs on **Flask 3.1.3 + eventlet 0.36.1 + gunicorn 23.0.0** with **psycopg2-binary** for the relay database and **raw `sqlite3`** for the P2P node.

### Root problems with the current stack

| Problem | Impact |
|---|---|
| `eventlet` monkey-patches stdlib | Fundamentally incompatible with native `asyncio`, `asyncpg`, and `uvloop`. Cannot be migrated incrementally. |
| Flask is WSGI-only | Will never get first-class async support. Every async operation blocks. |
| `gunicorn` is WSGI-era | Cannot use Rust-based ASGI servers (`granian`, `uvicorn`). |
| `psycopg2-binary` | Not recommended for production. Sync-only. `asyncpg` is 3× faster. |
| `requests` | Sync-only. Blocks the thread on every Tor/peer HTTP call. |
| `unittest` | Inferior to `pytest` ecosystem (fixtures, plugins, parametrize). |
| No structured logging | Can't guarantee sensitive fields are never logged. |
| No observability | No metrics, no tracing, no health probes. Impossible to run in Kubernetes. |

## Decision

Migrate the Python backend to **FastAPI + uvicorn (dev) + granian (prod)** in four phases (2a–2d), running Flask and FastAPI **in dual-stack mode** during the transition. This avoids a big-bang migration.

## Migration Phases

| Phase | Weeks | Action |
|---|---|---|
| **2a** | 8-12 | Stand up FastAPI alongside Flask. Both run; FastAPI handles new `/v3/*` endpoints. |
| **2b** | 12-16 | Migrate legacy Flask HTTP routes to FastAPI. Socket.IO stays on Flask temporarily. |
| **2c** | 16-20 | Migrate Socket.IO to ASGI mode. Migrate DB to SQLAlchemy 2.0 async + Alembic. |
| **2d** | 20-24 | Delete Flask + eventlet. Relay is pure FastAPI + granian + asyncio. |

## Target Stack

```
fastapi >= 0.115          # ASGI framework
uvicorn[standard] >= 0.32 # dev server (--reload)
granian >= 1.6            # prod server (Rust, 4× uvicorn, HTTP/1+2+3)
pydantic >= 2.10          # validation (replaces marshmallow + manual validation)
pydantic-settings >= 2.6  # env config (replaces os.getenv() calls)
sqlalchemy >= 2.0.36      # async ORM
aiosqlite >= 0.20         # async SQLite (P2P node)
asyncpg >= 0.30           # async PostgreSQL (relay)
alembic >= 1.14           # schema migrations (replaces raw SQL files)
httpx >= 0.28             # async HTTP client (replaces requests)
orjson >= 3.10            # fast JSON
structlog >= 24.4          # structured logging with PII scrubbing
prometheus-client >= 0.21 # /metrics endpoint
opentelemetry-distro      # distributed tracing
sentry-sdk[fastapi]       # error monitoring
```

## Consequences

### Positive
- **Native async** throughout: DB, HTTP, Socket.IO, Tor all on the same `asyncio` event loop.
- **10× concurrent connections** headroom: uvloop + granian vs. eventlet's green threads.
- **Structural PII safety**: structlog scrubs sensitive fields before any log event is written.
- **Observability from day 1**: `/healthz`, `/readyz`, `/metrics`, OpenTelemetry tracing.
- **Type safety**: Pydantic v2 models for all request/response schemas; pyright checks them.
- **Faster JSON**: `orjson` is ~10× faster than `stdlib json`.

### Negative
- **Dual-stack complexity** during Phase 2a–2c: two frameworks running simultaneously.
  - Mitigated by running them on separate ports (`5000` Flask, `5001` FastAPI) in development.
- **Socket.IO ASGI migration** in Phase 2c requires client-side testing.
  - Mitigated by keeping the existing Socket.IO event names/shapes unchanged.

## Rejected Alternatives

| Alternative | Reason rejected |
|---|---|
| Stay on Flask, add `flask-async` | Flask async is a band-aid; eventlet fundamentally incompatible with asyncio. |
| Migrate to Django + ASGI | Django's ORM is sync-first; migration complexity similar but with less async ecosystem. |
| Migrate to Litestar | Smaller community; fewer resources for the privacy/security use case. |
