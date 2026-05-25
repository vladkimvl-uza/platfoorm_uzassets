"""Forgot-password flow (Pack 152) — thin HTTP shim (refactored 2026-05-25).

POST /auth/forgot-password         { login } → enqueue 6-digit code to TG
POST /auth/forgot-password/verify  { reset_id, code, new_password }

Rate-limited 5/hour (init), 10/hour (verify) per IP. Audit_log на оба endpoint.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from app.database import get_db
from app.dependencies.forgot_password import ForgotPasswordServiceDep
from app.services.forgot_password.service import (
    ForgotInitRequest, ForgotInitResponse,
    ForgotVerifyRequest, ForgotVerifyResponse,
)


router = APIRouter(prefix="/auth/forgot-password", tags=["auth"])


@router.post("", response_model=ForgotInitResponse)
@limiter.limit("5/hour")
async def forgot_init(
    request: Request,
    body: ForgotInitRequest,
    service: ForgotPasswordServiceDep,
    db: AsyncSession = Depends(get_db),
):
    return await service.init(body, request, db)


@router.post("/verify", response_model=ForgotVerifyResponse)
@limiter.limit("10/hour")
async def forgot_verify(
    request: Request,
    body: ForgotVerifyRequest,
    service: ForgotPasswordServiceDep,
    db: AsyncSession = Depends(get_db),
):
    return await service.verify(body, request, db)
