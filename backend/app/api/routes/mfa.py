"""MFA endpoints router (Pack 13.0).

All endpoints require an authenticated session (current_user dependency).
The current user dependency import path is auto-detected (Anthropic-style
FastAPI projects use either app.api.deps or app.core.security).
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mfa import MfaMethod
from app.models.user import User
from app.schemas.mfa import (
    MfaDisableIn, MfaEnableIn, MfaEnableOut,
    MfaLinkTelegramOut, MfaRecoveryCodesOut, MfaStatusOut,
    MfaTestNotificationOut, MfaUnlinkTelegramIn,
    TelegramPrefIn, TelegramPrefOut,
)
from app.services import mfa_service

# Auto-detect the project's auth + db dependency conventions
try:
    from app.api.deps import get_current_user, get_db
except ImportError:
    try:
        from app.api.dependencies import get_current_user, get_db
    except ImportError:
        from app.dependencies import get_current_user, get_db


router = APIRouter(prefix="/mfa", tags=["mfa"])


def _bot_username() -> str:
    return os.getenv("TELEGRAM_BOT_USERNAME", "UzAssets_bot").lstrip("@")


def _deep_link(token: str) -> str:
    return f"https://t.me/{_bot_username()}?start={token}"


# ─────────────────────────────────────────────────────────────────────────
# GET /mfa/status — current state
# ─────────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=MfaStatusOut)
async def get_status(
    current_user: User = Depends(get_current_user),
):
    return mfa_service.build_status(current_user)


# ─────────────────────────────────────────────────────────────────────────
# POST /mfa/enable — turn on 2FA, generate recovery codes
# ─────────────────────────────────────────────────────────────────────────

@router.post("/enable", response_model=MfaEnableOut)
async def enable_mfa(
    body: MfaEnableIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Require linked Telegram for telegram/both modes
    if body.method in ("telegram", "both"):
        if not getattr(current_user, "telegram_chat_id_encrypted", None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Telegram должен быть привязан до включения 2FA. Сначала вызовите /mfa/link-telegram.",
            )

    # Generate fresh recovery codes
    plain_codes = mfa_service.generate_recovery_codes()
    hashed = [mfa_service._hash_bcrypt(c) for c in plain_codes]

    current_user.mfa_enabled = True
    # Map literal → enum value
    method_value = {
        "telegram": MfaMethod.TELEGRAM,
        "totp":     MfaMethod.TOTP,
        "both":     MfaMethod.BOTH,
    }[body.method]
    current_user.mfa_method = method_value
    from app.services.mfa_service import set_recovery_codes
    set_recovery_codes(current_user, hashed)
    await db.flush()
    await db.commit()

    return MfaEnableOut(enabled=True, method=body.method, recovery_codes=plain_codes)


# ─────────────────────────────────────────────────────────────────────────
# POST /mfa/disable — turn off 2FA (must confirm with current code)
# ─────────────────────────────────────────────────────────────────────────

@router.post("/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_mfa(
    body: MfaDisableIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not getattr(current_user, "mfa_enabled", False):
        return  # already disabled, idempotent

    code = body.confirm_code.strip()

    # Try recovery code first (10-char with dash)
    if "-" in code and len(code) >= 9:
        if await mfa_service.verify_recovery_code(db, current_user, code):
            ok = True
        else:
            ok = False
    else:
        # 6-digit login code requires a fresh challenge — but the user is
        # already logged in, so they'd need to trigger emit. Easier path:
        # require the user to enter a recovery code to disable.
        ok = False

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Введите recovery code для подтверждения отключения 2FA.",
        )

    current_user.mfa_enabled = False
    current_user.mfa_method = MfaMethod.NONE
    from app.services.mfa_service import set_recovery_codes
    set_recovery_codes(current_user, None)
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────
# POST /mfa/link-telegram — start link flow, get deep-link token
# ─────────────────────────────────────────────────────────────────────────

@router.post("/link-telegram", response_model=MfaLinkTelegramOut)
async def link_telegram(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token, expires_at = await mfa_service.init_link_telegram(db, current_user)
    await db.commit()
    return MfaLinkTelegramOut(
        bot_username=_bot_username(),
        deep_link=_deep_link(token),
        token=token,
        expires_at=expires_at,
    )


# ─────────────────────────────────────────────────────────────────────────
# DELETE /mfa/unlink-telegram — wipe TG link (may disable 2FA if mode=telegram)
# ─────────────────────────────────────────────────────────────────────────

@router.delete("/unlink-telegram", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(
    body: MfaUnlinkTelegramIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Подтверждение обязательно (передайте confirm=true).",
        )
    await mfa_service.unlink_telegram(db, current_user)
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────
# POST /mfa/recovery-codes/regenerate — fresh 10 codes
# ─────────────────────────────────────────────────────────────────────────

@router.post("/recovery-codes/regenerate", response_model=MfaRecoveryCodesOut)
async def regenerate_recovery_codes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not getattr(current_user, "mfa_enabled", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA должна быть включена для генерации recovery codes.",
        )
    plain_codes = mfa_service.generate_recovery_codes()
    hashed = [mfa_service._hash_bcrypt(c) for c in plain_codes]
    from app.services.mfa_service import set_recovery_codes
    set_recovery_codes(current_user, hashed)
    await db.commit()
    return MfaRecoveryCodesOut(codes=plain_codes)


# ─────────────────────────────────────────────────────────────────────────
# GET / PATCH /mfa/notification-prefs
# ─────────────────────────────────────────────────────────────────────────

@router.get("/notification-prefs", response_model=TelegramPrefOut)
async def get_notification_prefs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await mfa_service.get_or_create_pref(db, current_user.id)
    await db.commit()
    return TelegramPrefOut(
        enabled=pref.enabled,
        type_assignments=pref.type_assignments,
        type_mentions=pref.type_mentions,
        type_deadlines=pref.type_deadlines,
        type_moderation=pref.type_moderation,
        type_broadcasts=pref.type_broadcasts,
        type_system=pref.type_system,
        quiet_hours_enabled=pref.quiet_hours_enabled,
        quiet_hours_start=pref.quiet_hours_start,
        quiet_hours_end=pref.quiet_hours_end,
        timezone=pref.timezone,
    )


@router.patch("/notification-prefs", response_model=TelegramPrefOut)
async def patch_notification_prefs(
    body: TelegramPrefIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    changes = body.model_dump(exclude_unset=True)
    pref = await mfa_service.update_pref(db, current_user.id, **changes)
    await db.commit()
    return TelegramPrefOut(
        enabled=pref.enabled,
        type_assignments=pref.type_assignments,
        type_mentions=pref.type_mentions,
        type_deadlines=pref.type_deadlines,
        type_moderation=pref.type_moderation,
        type_broadcasts=pref.type_broadcasts,
        type_system=pref.type_system,
        quiet_hours_enabled=pref.quiet_hours_enabled,
        quiet_hours_start=pref.quiet_hours_start,
        quiet_hours_end=pref.quiet_hours_end,
        timezone=pref.timezone,
    )


# ─────────────────────────────────────────────────────────────────────────
# POST /mfa/test-notification — send a probe message to user's TG
# ─────────────────────────────────────────────────────────────────────────

@router.post("/test-notification", response_model=MfaTestNotificationOut)
async def test_notification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not getattr(current_user, "telegram_chat_id_encrypted", None):
        return MfaTestNotificationOut(
            enqueued=False,
            detail="Telegram не привязан. Сначала /mfa/link-telegram.",
        )

    from app.models.mfa import OutboxType
    row = await mfa_service.enqueue_telegram_message(
        db, current_user.id, OutboxType.TEST,
        payload={
            "title": "Тестовое уведомление UzAssets",
            "body": "Если вы видите это сообщение, доставка через Telegram настроена корректно.",
            "email": current_user.email,
        },
    )
    await db.commit()
    return MfaTestNotificationOut(enqueued=True, outbox_id=str(row.id))


# ─────────────────────────────────────────────────────────────────────────
# Pack 13.3 — MFA onboarding (first-login wizard)
# ─────────────────────────────────────────────────────────────────────────

from datetime import timedelta as _td, timezone as _tz
from pydantic import BaseModel as _BaseModel


class OnboardingStatusOut(_BaseModel):
    """Returned to frontend to decide whether to show the wizard."""
    needed: bool
    reason: str  # 'mfa_enabled' | 'skipped' | 'show'
    skipped_until: Optional[str] = None  # ISO-8601 if reason='skipped'


class OnboardingSkipOut(_BaseModel):
    ok: bool
    skipped_until: str


@router.get("/onboarding/status", response_model=OnboardingStatusOut)
async def onboarding_status(
    current_user: User = Depends(get_current_user),
):
    if getattr(current_user, "mfa_enabled", False):
        return OnboardingStatusOut(needed=False, reason="mfa_enabled")

    skipped = getattr(current_user, "mfa_onboarding_skipped_until", None)
    if skipped is not None:
        now = datetime.now(_tz.utc)
        if skipped.tzinfo is None:
            skipped = skipped.replace(tzinfo=_tz.utc)
        if skipped > now:
            return OnboardingStatusOut(
                needed=False,
                reason="skipped",
                skipped_until=skipped.isoformat(),
            )

    return OnboardingStatusOut(needed=True, reason="show")


@router.post("/onboarding/skip", response_model=OnboardingSkipOut)
async def onboarding_skip(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    until = datetime.now(_tz.utc) + _td(days=7)
    current_user.mfa_onboarding_skipped_until = until
    await db.commit()
    return OnboardingSkipOut(ok=True, skipped_until=until.isoformat())


@router.post("/onboarding/complete", status_code=status.HTTP_204_NO_CONTENT)
async def onboarding_complete(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.mfa_onboarding_skipped_until = None
    await db.commit()


# ── /mfa/onboarding/send-code  + /verify-and-enable  (Pack 13.3.2) ─────

class OnboardingSendCodeOut(_BaseModel):
    challenge_id: str
    ttl_minutes: int


@router.post("/onboarding/send-code", response_model=OnboardingSendCodeOut)
async def onboarding_send_code(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not getattr(current_user, "telegram_chat_id_encrypted", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram должен быть привязан до отправки кода.",
        )

    from app.models.mfa import MfaLoginChallenge as _Chal, OutboxType as _Out
    code = mfa_service._gen_login_code()
    now = datetime.now(_tz.utc)
    challenge = _Chal(
        user_id=current_user.id,
        code_hashed=mfa_service._hash_bcrypt(code),
        created_at=now,
        expires_at=now + _td(minutes=mfa_service.LOGIN_CODE_TTL_MINUTES),
    )
    db.add(challenge)
    await db.flush()

    await mfa_service.enqueue_telegram_message(
        db, current_user.id, _Out.MFA_CODE,
        payload={
            "code": code,
            "ttl_minutes": mfa_service.LOGIN_CODE_TTL_MINUTES,
            "challenge_id": str(challenge.id),
        },
    )
    await db.commit()
    return OnboardingSendCodeOut(
        challenge_id=str(challenge.id),
        ttl_minutes=mfa_service.LOGIN_CODE_TTL_MINUTES,
    )


class OnboardingVerifyEnableIn(_BaseModel):
    challenge_id: str
    code: str


@router.post("/onboarding/verify-and-enable", response_model=MfaEnableOut)
async def onboarding_verify_and_enable(
    body: OnboardingVerifyEnableIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await mfa_service.verify_login_challenge(db, body.challenge_id, body.code)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный код или срок действия истёк. Запросите код заново.",
        )

    plain_codes = mfa_service.generate_recovery_codes()
    hashed = [mfa_service._hash_bcrypt(c) for c in plain_codes]

    current_user.mfa_enabled = True
    current_user.mfa_method = MfaMethod.TELEGRAM
    from app.services.mfa_service import set_recovery_codes
    set_recovery_codes(current_user, hashed)
    current_user.mfa_onboarding_skipped_until = None
    await db.commit()

    return MfaEnableOut(enabled=True, method="telegram", recovery_codes=plain_codes)