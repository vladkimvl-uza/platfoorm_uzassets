"""Centralized exception taxonomy.

Use these in new code instead of raising HTTPException directly.
Each maps to a specific HTTP status and gets a uniform JSON shape via
`app.core.error_handlers.register_error_handlers()`.

    raise NotFoundError("Company 12 not found")
    raise BusinessError("Cannot delete: 3 dependent projects")
    raise ForbiddenError("Not authorized to view this company")
    raise ExternalServiceError("Gateway", "GNK API timeout")

Legacy `raise HTTPException(...)` keeps working — we don't sweep the codebase,
just provide the taxonomy for new endpoints and gradual migration.
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base for all app-level errors. Carries (error_code, detail, status_code)."""

    status_code: int = 500
    error_code: str = "InternalError"

    def __init__(
        self,
        detail: str = "",
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ):
        self.detail = detail
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        self.extra = extra or {}
        super().__init__(detail or self.error_code)


class BusinessError(AppError):
    """Domain rule violation. 400."""
    status_code = 400
    error_code = "BusinessError"


class ValidationError(AppError):
    """Input failed semantic validation (beyond pydantic). 422."""
    status_code = 422
    error_code = "ValidationError"


class NotFoundError(AppError):
    """Resource not found. 404."""
    status_code = 404
    error_code = "NotFound"


class ConflictError(AppError):
    """Resource conflict (duplicate, version mismatch). 409."""
    status_code = 409
    error_code = "Conflict"


class UnauthorizedError(AppError):
    """Missing / invalid auth. 401."""
    status_code = 401
    error_code = "Unauthorized"


class ForbiddenError(AppError):
    """Authenticated but not permitted. 403."""
    status_code = 403
    error_code = "Forbidden"


class RateLimitError(AppError):
    """Caller exceeded a quota. 429."""
    status_code = 429
    error_code = "RateLimit"


class ExternalServiceError(AppError):
    """Upstream service failed (gateway, SSO, eGov, etc.). 502."""
    status_code = 502
    error_code = "ExternalServiceError"

    def __init__(self, service: str, detail: str = "", **kwargs):
        full_detail = f"{service}: {detail}" if detail else service
        super().__init__(full_detail, error_code=f"{service}Error", **kwargs)
        self.service = service
