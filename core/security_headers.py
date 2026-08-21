from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for FastAPI / Starlette to enforce defense-in-depth security headers.
    """

    async def dispatch(
        self, request: StarletteRequest, call_next: Any
    ) -> StarletteResponse:
        response = await call_next(request)

        # 1. HSTS (Strict-Transport-Security)
        if (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https"
        ):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # 2. Frame & Content Sniffing Protection
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        # 3. Cross-Origin Policies (COOP, COEP, CORP)
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

        # 4. Content Security Policy (CSP)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.socket.io https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "connect-src 'self' ws: wss:;"
        )

        # 5. Disable caching on sensitive API endpoints
        path = request.url.path
        if (
            path in ["/", "/login", "/register", "/chat"]
            or path.startswith("/v3/auth")
            or path.startswith("/v3/keys")
            or path.startswith("/v3/sync")
        ):
            response.headers["Cache-Control"] = "no-store, max-age=0"

        return response


# ── Legacy Flask Compatibility ─────────────────────────────────────────────────


def set_security_headers(response: Any) -> Any:
    """
    Flask hook to enforce browser security headers.
    """
    from flask import request

    # 1. HSTS (Strict-Transport-Security) - support reverse proxies
    if (
        request.is_secure
        or request.headers.get("X-Forwarded-Proto", "").lower() == "https"
    ):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # 2. Frame & Content Sniffing Protection
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    # 3. Cross-Origin Policies (COOP, COEP, CORP)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

    # 4. Content Security Policy (CSP)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.socket.io https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "connect-src 'self' ws: wss:;"
    )

    # 5. Disable caching on sensitive views
    if request.path in ["/", "/login", "/register", "/chat"]:
        response.headers["Cache-Control"] = "no-store, max-age=0"

    return response


def setup_security_headers(app: Any) -> None:
    """Registers security headers on Flask application."""
    app.after_request(set_security_headers)
