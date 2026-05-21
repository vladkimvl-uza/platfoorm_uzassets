"""Per-IP rate limiting via slowapi.

Buckets:
  - RATE_LIMIT_AUTH   — strict, applied to /auth/login + /auth/refresh
  - RATE_LIMIT_API    — generous, default for other API endpoints
  - RATE_LIMIT_HEAVY  — for /reports, /export, AI chat

In production, swap the in-memory storage for Redis by passing a `storage_uri`
to the Limiter constructor.
"""
from __future__ import annotations

import ipaddress
import os

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


# Trusted upstream proxies. Default = Docker bridge networks where nginx
# lives. X-Forwarded-For is honored ONLY when request.client.host is one
# of these — otherwise an attacker on the public internet could spoof
# the header to bypass per-IP rate limits.
_DEFAULT_TRUSTED = ["172.16.0.0/12", "10.0.0.0/8", "127.0.0.0/8", "::1/128"]
_RAW = os.environ.get("RATE_LIMIT_TRUSTED_PROXIES", ",".join(_DEFAULT_TRUSTED))
_TRUSTED_NETS = []
for cidr in (s.strip() for s in _RAW.split(",")):
    if cidr:
        try:
            _TRUSTED_NETS.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            pass


def _real_client_ip(request: Request) -> str:
    """Return the originating client IP, considering X-Forwarded-For only
    when the immediate peer (request.client.host) is in the trusted proxy
    list. Otherwise the immediate peer is the client.
    """
    peer = (request.client.host if request.client else "") or "0.0.0.0"
    try:
        peer_addr = ipaddress.ip_address(peer)
        is_trusted = any(peer_addr in net for net in _TRUSTED_NETS)
    except ValueError:
        is_trusted = False
    if not is_trusted:
        return peer
    fwd = request.headers.get("x-forwarded-for", "").strip()
    if not fwd:
        return peer
    # Right-most non-trusted IP in the chain is the real client.
    chain = [p.strip() for p in fwd.split(",") if p.strip()]
    for candidate in reversed(chain):
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not any(ip in net for net in _TRUSTED_NETS):
            return candidate
    # All hops were trusted proxies — fall back to left-most.
    return chain[0] if chain else peer


def _key_func(request: Request) -> str:
    """Per-user key when authenticated, per-IP otherwise.
    Per-IP uses trusted-proxy-aware client resolution to prevent
    X-Forwarded-For spoofing bypass of the auth bucket.
    """
    user = getattr(request.state, "user", None)
    if user and getattr(user, "id", None):
        return f"user:{user.id}"
    return f"ip:{_real_client_ip(request)}"


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
