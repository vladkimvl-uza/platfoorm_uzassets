"""User-facing MFA endpoints (Pack 13.0/13.3).

12 endpoints:
  GET    /mfa/status                                     current state
  POST   /mfa/enable                                     turn on 2FA
  POST   /mfa/disable                                    turn off (recovery code req)
  POST   /mfa/link-telegram                              deep-link token
  DELETE /mfa/unlink-telegram                            wipe TG link
  POST   /mfa/recovery-codes/regenerate                  new 10 codes
  GET    /mfa/notification-prefs                         read prefs
  PATCH  /mfa/notification-prefs                         write prefs
  POST   /mfa/test-notification                          send probe to TG
  GET    /mfa/onboarding/status                          wizard show?
  POST   /mfa/onboarding/skip                            +7 days
  POST   /mfa/onboarding/complete                        clear skip flag
  POST   /mfa/onboarding/send-code                       wizard step 2
  POST   /mfa/onboarding/verify-and-enable               wizard step 3

Core `app.services.mfa_service` not touched.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import current_locale, locale_of_user, tr
from app.models.mfa import MfaMethod
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
from app.services import mfa_service

# ─── Onboarding payload schemas ──────────────────────────────────

class OnboardingStatusOut(BaseModel):
    needed: bool
    reason: str  # 'mfa_enabled' | 'skipped' | 'show'
    skipped_until: Optional[str] = None


class OnboardingSkipOut(BaseModel):
    ok: bool
    skipped_until: str


class OnboardingSendCodeOut(BaseModel):
    challenge_id: str
    ttl_minutes: int


class OnboardingVerifyEnableIn(BaseModel):
    challenge_id: str
    code: str


# ─── Helpers ──────────────────────────────────────────────────────

def _bot_username() -> str:
    return os.getenv("TELEGRAM_BOT_USERNAME", "UzAssets_bot").lstrip("@")


def _deep_link(token: str) -> str:
    return f"https://t.me/{_bot_username()}?start={token}"


@dataclass
class MfaUserService:
    # ─── Status ───────────────────────────────────────────────────

    def status(self, current_user: User) -> MfaStatusOut:
        return mfa_service.build_status(current_user)

    # ─── Enable / Disable ─────────────────────────────────────────

    async def enable(
        self,
        body: MfaEnableIn,
        current_user: User,
        db: AsyncSession,
    ) -> MfaEnableOut:
        if body.method in ("telegram", "both"):
            if not getattr(current_user, "telegram_chat_id_encrypted", None):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=tr(
                        "Telegram должен быть привязан до включения 2FA. "
                        "Сначала вызовите /mfa/link-telegram.",
                        current_locale(),
                    ),
                )
        plain_codes = mfa_service.generate_recovery_codes()
        hashed = [mfa_service._hash_bcrypt(c) for c in plain_codes]

        current_user.mfa_enabled = True
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
        return MfaEnableOut(
            enabled=True, method=body.method, recovery_codes=plain_codes,
        )

    async def disable(
        self,
        body: MfaDisableIn,
        current_user: User,
        db: AsyncSession,
    ) -> None:
        if not getattr(current_user, "mfa_enabled", False):
            return  # idempotent
        code = body.confirm_code.strip()
        if "-" in code and len(code) >= 9:
            ok = await mfa_service.verify_recovery_code(
                db, current_user, code,
            )
        else:
            ok = False
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=tr(
                    "Введите recovery code для подтверждения отключения 2FA.",
                    current_locale(),
                ),
            )
        current_user.mfa_enabled = False
        current_user.mfa_method = MfaMethod.NONE
        from app.services.mfa_service import set_recovery_codes
        set_recovery_codes(current_user, None)
        await db.commit()

    # ─── Telegram link / unlink ───────────────────────────────────

    async def link_telegram(
        self, current_user: User, db: AsyncSession,
    ) -> MfaLinkTelegramOut:
        token, expires_at = await mfa_service.init_link_telegram(
            db, current_user,
        )
        await db.commit()
        return MfaLinkTelegramOut(
            bot_username=_bot_username(),
            deep_link=_deep_link(token),
            token=token,
            expires_at=expires_at,
        )

    async def unlink_telegram(
        self,
        body: MfaUnlinkTelegramIn,
        current_user: User,
        db: AsyncSession,
    ) -> None:
        if not body.confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=tr(
                    "Подтверждение обязательно (передайте confirm=true).",
                    current_locale(),
                ),
            )
        await mfa_service.unlink_telegram(db, current_user)
        await db.commit()

    # ─── Recovery codes ───────────────────────────────────────────

    async def regenerate_recovery_codes(
        self, current_user: User, db: AsyncSession,
    ) -> MfaRecoveryCodesOut:
        if not getattr(current_user, "mfa_enabled", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=tr(
                    "2FA должна быть включена для генерации recovery codes.",
                    current_locale(),
                ),
            )
        plain_codes = mfa_service.generate_recovery_codes()
        hashed = [mfa_service._hash_bcrypt(c) for c in plain_codes]
        from app.services.mfa_service import set_recovery_codes
        set_recovery_codes(current_user, hashed)
        await db.commit()
        return MfaRecoveryCodesOut(codes=plain_codes)

    # ─── Notification prefs ───────────────────────────────────────

    async def get_notification_prefs(
        self, current_user: User, db: AsyncSession,
    ) -> TelegramPrefOut:
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

    async def patch_notification_prefs(
        self,
        body: TelegramPrefIn,
        current_user: User,
        db: AsyncSession,
    ) -> TelegramPrefOut:
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

    async def test_notification(
        self, current_user: User, db: AsyncSession,
    ) -> MfaTestNotificationOut:
        locale = locale_of_user(current_user)
        if not getattr(current_user, "telegram_chat_id_encrypted", None):
            return MfaTestNotificationOut(
                enqueued=False,
                detail=tr(
                    "Telegram не привязан. Сначала /mfa/link-telegram.",
                    current_locale(),
                ),
            )
        from app.models.mfa import OutboxType
        row = await mfa_service.enqueue_telegram_message(
            db, current_user.id, OutboxType.TEST,
            payload={
                "title": tr("Тестовое уведомление UzAssets", locale),
                "body": tr(
                    "Если вы видите это сообщение, доставка через "
                    "Telegram настроена корректно.",
                    locale,
                ),
                "email": current_user.email,
                "locale": locale,
            },
        )
        await db.commit()
        return MfaTestNotificationOut(enqueued=True, outbox_id=str(row.id))

    # ─── Onboarding wizard ───────────────────────────────────────

    def onboarding_status(self, current_user: User) -> OnboardingStatusOut:
        if getattr(current_user, "mfa_enabled", False):
            return OnboardingStatusOut(needed=False, reason="mfa_enabled")
        skipped = getattr(current_user, "mfa_onboarding_skipped_until", None)
        if skipped is not None:
            now = datetime.now(UTC)
            if skipped.tzinfo is None:
                skipped = skipped.replace(tzinfo=UTC)
            if skipped > now:
                return OnboardingStatusOut(
                    needed=False,
                    reason="skipped",
                    skipped_until=skipped.isoformat(),
                )
        return OnboardingStatusOut(needed=True, reason="show")

    async def onboarding_skip(
        self, current_user: User, db: AsyncSession,
    ) -> OnboardingSkipOut:
        until = datetime.now(UTC) + timedelta(days=7)
        current_user.mfa_onboarding_skipped_until = until
        await db.commit()
        return OnboardingSkipOut(ok=True, skipped_until=until.isoformat())

    async def onboarding_complete(
        self, current_user: User, db: AsyncSession,
    ) -> None:
        current_user.mfa_onboarding_skipped_until = None
        await db.commit()

    async def onboarding_send_code(
        self, current_user: User, db: AsyncSession,
    ) -> OnboardingSendCodeOut:
        if not getattr(current_user, "telegram_chat_id_encrypted", None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=tr(
                    "Telegram должен быть привязан до отправки кода.",
                    current_locale(),
                ),
            )
        from app.models.mfa import MfaLoginChallenge, OutboxType
        code = mfa_service._gen_login_code()
        now = datetime.now(UTC)
        challenge = MfaLoginChallenge(
            user_id=current_user.id,
            code_hashed=mfa_service._hash_bcrypt(code),
            created_at=now,
            expires_at=now + timedelta(
                minutes=mfa_service.LOGIN_CODE_TTL_MINUTES,
            ),
        )
        db.add(challenge)
        await db.flush()
        await mfa_service.enqueue_telegram_message(
            db, current_user.id, OutboxType.MFA_CODE,
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

    async def onboarding_verify_and_enable(
        self,
        body: OnboardingVerifyEnableIn,
        current_user: User,
        db: AsyncSession,
    ) -> MfaEnableOut:
        ok = await mfa_service.verify_login_challenge(
            db, body.challenge_id, body.code,
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=tr(
                    "Неверный код или срок действия истёк. "
                    "Запросите код заново.",
                    current_locale(),
                ),
            )
        plain_codes = mfa_service.generate_recovery_codes()
        hashed = [mfa_service._hash_bcrypt(c) for c in plain_codes]
        current_user.mfa_enabled = True
        current_user.mfa_method = MfaMethod.TELEGRAM
        from app.services.mfa_service import set_recovery_codes
        set_recovery_codes(current_user, hashed)
        current_user.mfa_onboarding_skipped_until = None
        await db.commit()
        return MfaEnableOut(
            enabled=True, method="telegram", recovery_codes=plain_codes,
        )
