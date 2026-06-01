"""MFA-aware login flow — thin HTTP shim (refactored 2026-05-25).

Endpoints:
  - POST /auth/login-mfa  — MFA-gated wrapper around auth_service.authenticate
  - POST /auth/verify-mfa — second step (TG code OR recovery code)

Both endpoints are rate-limited the same way as /auth/login.
Business logic lives in `app.services.auth_mfa.service.AuthMfaService`.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth_mfa import LoginMfaResponse, VerifyMfaIn
from app.config import settings
from app.core.rate_limit import limiter
from app.database import get_db
from app.dependencies.auth_mfa import AuthMfaServiceDep
from app.schemas.auth import LoginRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["auth-mfa"])


def _client_ip(request: Request) -> Optional[str]:
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


@router.post("/login-mfa", response_model=LoginMfaResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login_mfa(
    request: Request,
    body: LoginRequest,
    service: AuthMfaServiceDep,
    db: AsyncSession = Depends(get_db),
) -> LoginMfaResponse:
    return await service.login_mfa(
        db, body,
        ip=_client_ip(request),
        ua=request.headers.get("user-agent", "")[:512],
    )


@router.post("/verify-mfa", response_model=TokenPair)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def verify_mfa(
    request: Request,
    body: VerifyMfaIn,
    service: AuthMfaServiceDep,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    return await service.verify_mfa(
        db, body,
        ip=_client_ip(request),
        ua=request.headers.get("user-agent", "")[:512],
    )
