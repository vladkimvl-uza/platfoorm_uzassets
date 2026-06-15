"""Forgot-password flow (Pack 152) — Telegram-code based use-case.

Two endpoints:
  POST /auth/forgot-password         { login } → enqueue 6-digit code to TG
  POST /auth/forgot-password/verify  { reset_id, code, new_password }

Security: Bcrypt-hashed reset_code (как MFA challenge); SHA256-hashed reset_id;
TTL 5min; max 5 attempts. Core helpers (`mfa_service._hash_*`, `_gen_login_code`,
`enqueue_telegram_message`, `core.password.*`) NOT touched.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.password import hash_password, validate_password_policy
from app.models.mfa import OutboxType
from app.models.user import User
from app.services import mfa_service

log = logging.getLogger(__name__)

RESET_TTL_MINUTES = 5
MAX_CODE_ATTEMPTS = 5


# ─── Schemas ──────────────────────────────────────────────────────

class ForgotInitRequest(BaseModel):
    login: str = Field(..., min_length=3, max_length=255)


class ForgotInitResponse(BaseModel):
    reset_id: str
    ttl_minutes: int
    masked_telegram: Optional[str] = None
    message: str


class ForgotVerifyRequest(BaseModel):
    reset_id: str = Field(..., min_length=8, max_length=128)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=12, max_length=128)


class ForgotVerifyResponse(BaseModel):
    ok: bool
    mfa_required: bool = False


def _client_ip(request: Request) -> Optional[str]:
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


def _mask_tg_username(username: Optional[str]) -> str:
    if not username:
        return "@***"
    if len(username) <= 4:
        return f"@***{username[-1:]}"
    return f"@***{username[-3:]}"


def _clear_reset_state(user: User) -> None:
    user.password_reset_token_hashed = None
    user.password_reset_code_hashed = None
    user.password_reset_expires_at = None
    user.password_reset_attempts = 0


@dataclass
class ForgotPasswordService:
    async def init(
        self,
        body: ForgotInitRequest,
        request: Request,
        db: AsyncSession,
    ) -> ForgotInitResponse:
        login = body.login.strip()
        login_lc = login.lower()
        user = (await db.execute(
            select(User).where(or_(
                User.email == login_lc,
                User.username == login,
            ))
        )).scalar_one_or_none()

        if not user:
            try:
                await append_audit_entry(
                    db,
                    actor_email=login_lc,
                    action="auth.forgot_password.init_unmatched",
                    entity_type="auth",
                    ip_address=_client_ip(request),
                    user_agent=(request.headers.get("user-agent") or "")[:512],
                )
                await db.commit()
            except Exception:
                await db.rollback()
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Аккаунт с таким email или логином не найден.",
            )

        if not user.telegram_chat_id_encrypted:
            try:
                await append_audit_entry(
                    db,
                    actor_id=str(user.id),
                    actor_email=user.email,
                    action="auth.forgot_password.init_no_telegram",
                    entity_type="auth",
                    ip_address=_client_ip(request),
                    user_agent=(request.headers.get("user-agent") or "")[:512],
                )
                await db.commit()
            except Exception:
                await db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "К аккаунту не привязан Telegram. Обратитесь к администратору.",
            )

        reset_id = secrets.token_urlsafe(24)
        code = mfa_service._gen_login_code()
        user.password_reset_token_hashed = mfa_service._hash_sha256(reset_id)
        user.password_reset_code_hashed = mfa_service._hash_bcrypt(code)
        user.password_reset_expires_at = (
            datetime.now(UTC) + timedelta(minutes=RESET_TTL_MINUTES)
        )
        user.password_reset_attempts = 0

        await mfa_service.enqueue_telegram_message(
            db,
            user_id=user.id,
            msg_type=OutboxType.MFA_CODE,
            payload={
                "code": code,
                "purpose": "password_reset",
                "ttl_minutes": RESET_TTL_MINUTES,
                "subject": "Код восстановления пароля",
            },
        )

        # Дублируем код восстановления на email (best-effort, если SMTP включён).
        try:
            from app.services.email.service import send_email, email_configured
            if email_configured() and user.email:
                from app.services.email import templates as _tpl
                subj, html = _tpl.notification_email(
                    eyebrow="Сброс пароля", title="Код восстановления пароля", accent="#111A3E",
                    lines=[
                        f'Ваш код для восстановления доступа: <b style="font-size:20px;letter-spacing:.12em;color:#1E2A4A">{code}</b>',
                        f"Код действителен <b>{RESET_TTL_MINUTES} минут</b>. Если вы не запрашивали сброс — проигнорируйте письмо.",
                    ],
                )
                await send_email(user.email, subj, html)
        except Exception:  # noqa: BLE001
            pass

        await append_audit_entry(
            db,
            actor_id=str(user.id),
            actor_email=user.email,
            action="auth.forgot_password.init",
            entity_type="auth",
            ip_address=_client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:512],
            notes=f"reset_code issued to telegram (ttl={RESET_TTL_MINUTES}m)",
        )
        await db.commit()

        return ForgotInitResponse(
            reset_id=reset_id,
            ttl_minutes=RESET_TTL_MINUTES,
            masked_telegram=_mask_tg_username(user.telegram_username),
            message="Код отправлен в Telegram.",
        )

    async def verify(
        self,
        body: ForgotVerifyRequest,
        request: Request,
        db: AsyncSession,
    ) -> ForgotVerifyResponse:
        reset_hash = mfa_service._hash_sha256(body.reset_id)
        user = (await db.execute(
            select(User).where(User.password_reset_token_hashed == reset_hash)
        )).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Неверный код или истёк срок действия",
            )

        now = datetime.now(UTC)
        if not user.password_reset_expires_at or user.password_reset_expires_at < now:
            _clear_reset_state(user)
            try:
                await append_audit_entry(
                    db, actor_id=str(user.id), actor_email=user.email,
                    action="auth.forgot_password.expired",
                    entity_type="auth", ip_address=_client_ip(request),
                )
                await db.commit()
            except Exception:
                await db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Код истёк. Запросите новый.",
            )

        if not mfa_service._check_bcrypt(
            body.code, user.password_reset_code_hashed or "",
        ):
            user.password_reset_attempts = (user.password_reset_attempts or 0) + 1
            if user.password_reset_attempts >= MAX_CODE_ATTEMPTS:
                _clear_reset_state(user)
                await append_audit_entry(
                    db, actor_id=str(user.id), actor_email=user.email,
                    action="auth.forgot_password.attempts_exceeded",
                    entity_type="auth", ip_address=_client_ip(request),
                    is_critical=True,
                )
                await db.commit()
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Превышено количество попыток. Запросите новый код.",
                )
            await db.commit()
            remaining = MAX_CODE_ATTEMPTS - user.password_reset_attempts
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Неверный код. Осталось попыток: {remaining}",
            )

        try:
            validate_password_policy(body.new_password)
        except Exception as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        user.password_hash = hash_password(body.new_password)
        user.password_changed_at = now
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None
        _clear_reset_state(user)

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="auth.forgot_password.success",
            entity_type="auth", ip_address=_client_ip(request),
            is_critical=True,
            notes="password reset via telegram code",
        )
        await db.commit()

        # Уведомление о сбросе пароля (841 п.5.1.2.2 — без секретов в теле).
        from app.services.auth_service import send_security_alert
        await send_security_alert(
            db, user.id,
            title="Пароль изменён",
            body="Пароль вашего аккаунта был сброшен. Если это были не вы — "
                 "немедленно обратитесь к администратору.",
        )

        return ForgotVerifyResponse(
            ok=True, mfa_required=bool(user.mfa_enabled),
        )
