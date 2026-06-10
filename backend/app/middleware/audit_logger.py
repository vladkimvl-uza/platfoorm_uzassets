"""Audit logging middleware (Pack 9.0).

Wraps every HTTP request and writes a single audit_log row after the response.
Skips noisy endpoints (health, audit stream, static, OPTIONS preflights).
Auth user extracted from request.state.user if upstream auth dep set it,
otherwise from the bearer token directly.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database import AsyncSessionLocal
from app.services.audit_service import (
    action_from_method,
    module_from_path,
    write_event,
)

logger = logging.getLogger(__name__)

# Path prefixes excluded from logging — high-volume / internal / не-действия.
SKIP_PREFIXES = (
    "/healthz",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon",
    "/presence",               # heartbeat присутствия (каждые 45с) — не действие, флудит аудит
    "/auth/refresh",           # авто-обновление токена сессии — не действие пользователя
    "/notifications/unread-count",  # поллинг счётчика уведомлений (каждые 30с)
    "/notifications/ws",       # websocket-апгрейд
    "/admin/audit/overview",   # self-referential; avoid recursive logging spam
    "/admin/audit/stream",
    "/admin/audit/events",
    "/admin/audit/timeline",
    "/admin/audit/stats",
)


def _should_skip(path: str, method: str) -> bool:
    if method.upper() == "OPTIONS":
        return True
    return any(path.startswith(p) for p in SKIP_PREFIXES)


async def _extract_user(request: Request) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Get (actor_id, actor_email, actor_role) from request.state if available."""
    user = getattr(request.state, "user", None)
    if user is None:
        return None, None, None
    try:
        actor_id = str(user.id) if getattr(user, "id", None) else None
        email = getattr(user, "email", None)
        role = None
        roles = getattr(user, "roles", None)
        if roles and len(roles) > 0:
            r0 = roles[0]
            role = getattr(r0, "code", None) or getattr(r0, "name", None)
        return actor_id, email, role
    except Exception:
        return None, None, None


class AuditLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        if _should_skip(path, method):
            return await call_next(request)

        start = time.perf_counter()
        status = 500
        response: Optional[Response] = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)

            # Audit write — never use `return` inside a `finally`, it overrides
            # the request's response with None and breaks downstream middleware.
            try:
                action = action_from_method(method, status)
                module = module_from_path(path)
                actor_id, actor_email, actor_role = await _extract_user(request)

                # Skip unauthenticated views — they're typically pre-auth pings
                should_log = not (
                    actor_email is None and action == "VIEW" and status < 400
                )
                if should_log:
                    ip = (request.client.host if request.client else None)
                    ua = request.headers.get("user-agent", "")[:512]
                    is_critical = action == "DELETE" or status >= 500

                    async with AsyncSessionLocal() as db:
                        await write_event(
                            db,
                            actor_id=actor_id,
                            actor_email=actor_email,
                            actor_role=actor_role,
                            action=action,
                            module=module,
                            http_method=method,
                            http_path=path[:512],
                            http_status=status,
                            duration_ms=duration_ms,
                            ip_address=ip,
                            user_agent=ua,
                            is_critical=is_critical,
                        )
                        await db.commit()

                        # OWNER activity feed: notify owners of meaningful
                        # changes across all companies (status/comments/files/
                        # editor edits). Best-effort, in-app only, throttled.
                        try:
                            from app.services.owner_activity import (
                                notify_owners_of_change,
                            )
                            await notify_owners_of_change(
                                db,
                                http_path=path,
                                http_method=method,
                                status=status,
                                actor_id=actor_id,
                                actor_email=actor_email,
                            )
                        except Exception as _oe:
                            logger.warning("owner-activity hook failed: %s", _oe)
            except Exception as e:
                # Never let audit logging break the request path
                logger.warning("audit middleware error: %s", e)

        return response
