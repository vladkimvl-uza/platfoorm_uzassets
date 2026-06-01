"""Error handlers.

Three layers:

  1. `AppError`        → uniform JSON shape, no TG alert (intentional client errors)
  2. `HTTPException`   → pass through as-is, no TG alert for 4xx, alert on 5xx
  3. `Exception`       → 500 + TG alert + traceback in log

JSON shape:
    { "error": "<code>", "detail": "<msg>", "request_id": "<id>" }

`request_id` is read from `request.state.request_id` if RequestIDMiddleware
registered it; otherwise omitted.

Registered via `register_error_handlers(app)` from main.py.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) if hasattr(request, "state") else None


def _user_id(request: Request) -> str | None:
    try:
        u = getattr(request.state, "user", None)
        return str(getattr(u, "id", "") or "") or None
    except Exception:
        return None


def _payload(error_code: str, detail: str, request: Request,
             extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": error_code, "detail": detail}
    rid = _request_id(request)
    if rid:
        body["request_id"] = rid
    if extra:
        body.update(extra)
    return body


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(exc.error_code, exc.detail, request, exc.extra),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    body = _payload("HTTPError", detail, request)

    # Alert on server-side HTTPException (rare but legitimate — e.g. 503 from /health/ready).
    if exc.status_code >= 500:
        try:
            from app.services.error_alerter import send_5xx_alert
            asyncio.create_task(send_5xx_alert(
                exc=exc,
                method=request.method,
                path=request.url.path,
                request_id=_request_id(request),
                user_id=_user_id(request),
            ))
        except Exception:
            logger.exception("Failed to dispatch 5xx alert for HTTPException")

    return JSONResponse(status_code=exc.status_code, content=body)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log full traceback locally regardless of alerter state.
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method, request.url.path, exc,
        exc_info=True,
    )

    try:
        from app.services.error_alerter import send_5xx_alert
        # Fire-and-forget — do not await; user gets 500 response immediately.
        asyncio.create_task(send_5xx_alert(
            exc=exc,
            method=request.method,
            path=request.url.path,
            request_id=_request_id(request),
            user_id=_user_id(request),
        ))
    except Exception:
        logger.exception("Failed to dispatch 5xx alert")

    return JSONResponse(
        status_code=500,
        content=_payload(
            "InternalError",
            "Произошла внутренняя ошибка. Попробуйте позднее.",
            request,
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Wire all three handlers. Call from main.py after FastAPI() instantiation."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
