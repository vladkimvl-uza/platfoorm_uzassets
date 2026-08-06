"""MFA endpoints (Pack 13.0/13.3) — thin HTTP shim (refactored 2026-05-25).

All endpoints require an authenticated session. Logic in
`app.services.mfa_user.MfaUserService`. Core `app.services.mfa_service` untouched.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.mfa import (
    MfaDisableIn,
    MfaEnableIn,
    MfaEnableOut,
    MfaRecoveryCodesOut,
    MfaStatusOut,
)

# Auto-detect the project's auth + db dependency conventions
try:
    from app.api.deps import get_current_user, get_db
except ImportError:
    try:
        from app.api.dependencies import get_current_user, get_db
    except ImportError:
        from app.dependencies import get_current_user, get_db

from app.dependencies.mfa_user import MfaUserServiceDep

router = APIRouter(prefix="/mfa", tags=["mfa"])


# ─── Status / Enable / Disable ────────────────────────────────────

@router.get("/status", response_model=MfaStatusOut)
async def get_status(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
):
    return service.status(current_user)


@router.post("/enable", response_model=MfaEnableOut)
async def enable_mfa(
    body: MfaEnableIn,
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.enable(body, current_user, db)


@router.post("/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_mfa(
    body: MfaDisableIn,
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.disable(body, current_user, db)


# ─── Telegram link / unlink ───────────────────────────────────────

@router.post("/recovery-codes/regenerate", response_model=MfaRecoveryCodesOut)
async def regenerate_recovery_codes(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.regenerate_recovery_codes(current_user, db)


# ─── Notification prefs ───────────────────────────────────────────

