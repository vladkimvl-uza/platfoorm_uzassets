"""Per-IP rate limiting via slowapi.

Buckets:
  - RATE_LIMIT_AUTH   — strict, applied to /auth/login + /auth/refresh
  - RATE_LIMIT_API    — generous, default for other API endpoints
  - RATE_LIMIT_HEAVY  — for /reports, /export, AI chat

In production, swap the in-memory storage for Redis by passing a `storage_uri`
to the Limiter constructor.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


def _key_func(request: Request) -> str:
    """Per-user key when authenticated, per-IP otherwise."""
    user = getattr(request.state, "user", None)
    if user and getattr(user, "id", None):
        return f"user:{user.id}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=_key_func,
    default_limits=[settings.RATE_LIMIT_API],
    enabled=settings.RATE_LIMIT_ENABLED,
)


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Return a clean 429 response without leaking limiter internals."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests",
            "retry_after_seconds": int(exc.detail.split(" per ")[1].split(" ")[0]) if " per " in str(exc.detail) else 60,
        },
        headers={"Retry-After": "60"},
    )
