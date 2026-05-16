"""Security middlewares: headers, request ID, body-size limit, HTTPS enforce.

Wired in `app.main`."""
from __future__ import annotations

import logging
import secrets
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.config import settings

log = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply state-grade security headers to every response.

    Includes:
      - HSTS (Strict-Transport-Security) with preload
      - CSP (Content-Security-Policy) — restrictive defaults
      - X-Frame-Options DENY (legacy clients)
      - X-Content-Type-Options nosniff
      - Referrer-Policy strict-origin-when-cross-origin
      - Cross-Origin-Opener-Policy same-origin
      - Cross-Origin-Resource-Policy same-site
      - Permissions-Policy — disable unused browser APIs
      - X-Permitted-Cross-Domain-Policies none
      - Cache-Control / Pragma — for API responses
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        h = response.headers

        # HSTS — only meaningful over HTTPS
        if settings.FORCE_HTTPS or settings.is_production:
            preload = "; preload" if settings.HSTS_PRELOAD else ""
            h["Strict-Transport-Security"] = (
                f"max-age={settings.HSTS_MAX_AGE_SECONDS}; includeSubDomains{preload}"
            )

        # Default CSP — adjust if frontend needs additional sources.
        # Vue dev with HMR over WS needs 'unsafe-inline' for styles in dev.
        if settings.is_production:
            h["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: blob:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "object-src 'none'"
            )
        else:
            # Dev — relaxed for HMR
            h["Content-Security-Policy"] = (
                "default-src 'self' http: https: ws: wss: data: blob: 'unsafe-inline' 'unsafe-eval'"
            )

        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-site")
        h.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        h.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()",
        )
        # API responses must not be cached by intermediaries
        if request.url.path.startswith("/auth") or request.url.path.startswith("/admin"):
            h["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            h["Pragma"] = "no-cache"

        # Strip server fingerprint
        if "server" in h:
            del h["server"]
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject an X-Request-ID into every request and response.
    Used by structured logger as a correlation key."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("X-Request-ID") or secrets.token_hex(8)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies above the configured cap.
    Defense against memory-exhaustion DoS."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                size = int(cl)
            except ValueError:
                size = -1
            if size > settings.REQUEST_BODY_MAX_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )
        return await call_next(request)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """In production with FORCE_HTTPS, redirect plain HTTP to HTTPS.
    Edge proxy normally handles this — middleware is a defense-in-depth fallback."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if settings.FORCE_HTTPS and request.url.scheme == "http":
            url = request.url.replace(scheme="https")
            return JSONResponse(
                status_code=301,
                content={"detail": "Use HTTPS"},
                headers={"Location": str(url)},
            )
        return await call_next(request)
