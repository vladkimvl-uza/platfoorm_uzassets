"""Security middlewares: headers, request ID, body-size limit, HTTPS enforce.

Wired in `app.main`."""
from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

log = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Minimal app-specific security headers.

    nginx is the canonical source for static security headers (CSP,
    X-Frame-Options, Referrer-Policy, COOP/CORP, Permissions-Policy,
    X-Permitted-Cross-Domain-Policies, X-Content-Type-Options) — see
    `nginx/conf.d/default.conf`. This middleware keeps only the bits
    that are app-aware:

      - HSTS — belt-and-suspenders for the rare case where backend is
               hit directly (eg. internal debugging) without nginx.
      - Cache-Control: no-store on /auth and /admin — defense against
               intermediaries caching credentials.
      - Server-token strip.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        h = response.headers

        # HSTS — only meaningful over HTTPS, browser caches it after first hit
        if settings.FORCE_HTTPS or settings.is_production:
            preload = "; preload" if settings.HSTS_PRELOAD else ""
            h.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.HSTS_MAX_AGE_SECONDS}; includeSubDomains{preload}",
            )

        # API auth/admin responses must not be cached by intermediaries
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
