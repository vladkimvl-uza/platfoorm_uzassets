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
    MfaLinkTelegramOut,
    MfaRecoveryCodesOut,
    MfaStatusOut,
    MfaTestNotificationOut,
    MfaUnlinkTelegramIn,
    TelegramPrefIn,
    TelegramPrefOut,
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
from app.services.mfa_user.service import (
    OnboardingSendCodeOut,
    OnboardingSkipOut,
    OnboardingStatusOut,
    OnboardingVerifyEnableIn,
)

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

@router.post("/link-telegram", response_model=MfaLinkTelegramOut)
async def link_telegram(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.link_telegram(current_user, db)


@router.delete("/unlink-telegram", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(
    body: MfaUnlinkTelegramIn,
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.unlink_telegram(body, current_user, db)


# ─── Recovery codes ───────────────────────────────────────────────

@router.post("/recovery-codes/regenerate", response_model=MfaRecoveryCodesOut)
async def regenerate_recovery_codes(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.regenerate_recovery_codes(current_user, db)


# ─── Notification prefs ───────────────────────────────────────────

@router.get("/notification-prefs", response_model=TelegramPrefOut)
async def get_notification_prefs(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_notification_prefs(current_user, db)


@router.patch("/notification-prefs", response_model=TelegramPrefOut)
async def patch_notification_prefs(
    body: TelegramPrefIn,
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.patch_notification_prefs(body, current_user, db)


@router.post("/test-notification", response_model=MfaTestNotificationOut)
async def test_notification(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.test_notification(current_user, db)


# ─── Onboarding wizard (Pack 13.3) ────────────────────────────────

@router.get("/onboarding/status", response_model=OnboardingStatusOut)
async def onboarding_status(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
):
    return service.onboarding_status(current_user)


@router.post("/onboarding/skip", response_model=OnboardingSkipOut)
async def onboarding_skip(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.onboarding_skip(current_user, db)


@router.post("/onboarding/complete", status_code=status.HTTP_204_NO_CONTENT)
async def onboarding_complete(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.onboarding_complete(current_user, db)


@router.post("/onboarding/send-code", response_model=OnboardingSendCodeOut)
async def onboarding_send_code(
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.onboarding_send_code(current_user, db)


@router.post("/onboarding/verify-and-enable", response_model=MfaEnableOut)
async def onboarding_verify_and_enable(
    body: OnboardingVerifyEnableIn,
    service: MfaUserServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.onboarding_verify_and_enable(body, current_user, db)
