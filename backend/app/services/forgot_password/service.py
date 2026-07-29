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
from app.core.i18n import current_locale, locale_of_user, tr
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
    # Канал доставки кода: "telegram" | "email" | None (авто: telegram, иначе email)
    channel: Optional[str] = None


class ForgotInitResponse(BaseModel):
    reset_id: str
    ttl_minutes: int
    channel: str = "telegram"  # фактически использованный канал
    masked_telegram: Optional[str] = None
    masked_email: Optional[str] = None
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


def _mask_email(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    head = local[0] if local else "*"
    return f"{head}***@{domain}"


def _clear_reset_state(user: User) -> None:
    user.password_reset_token_hashed = None
    user.password_reset_code_hashed = None
    user.password_reset_expires_at = None
    user.password_reset_attempts = 0


class ForgotChannelsResponse(BaseModel):
    telegram: bool = False
    email: bool = False
    masked_telegram: Optional[str] = None
    masked_email: Optional[str] = None


@dataclass
class ForgotPasswordService:
    async def channels(self, login: str, db: AsyncSession) -> ForgotChannelsResponse:
        """Доступные каналы восстановления для login (чтобы фронт скрыл
        недоступные опции). Если аккаунт не найден — оба false (без 404,
        чтобы не плодить enumeration сверх того, что уже даёт init)."""
        login_lc = login.strip().lower()
        user = (await db.execute(
            select(User).where(or_(User.email == login_lc, User.username == login.strip()))
        )).scalar_one_or_none()
        if not user:
            return ForgotChannelsResponse()
        from app.services.email.service import email_configured
        tg_ok = bool(user.telegram_chat_id_encrypted)
        email_ok = email_configured() and bool(user.email)
        return ForgotChannelsResponse(
            telegram=tg_ok, email=email_ok,
            masked_telegram=_mask_tg_username(user.telegram_username) if tg_ok else None,
            masked_email=_mask_email(user.email) if email_ok else None,
        )

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
                tr("Аккаунт с таким email или логином не найден.", current_locale()),
            )

        locale = locale_of_user(user)

        # Доступные каналы доставки кода.
        from app.services.email.service import email_configured, send_email
        tg_ok = bool(user.telegram_chat_id_encrypted)
        email_ok = email_configured() and bool(user.email)

        # Выбор канала: явный из запроса, иначе авто (telegram → email).
        requested = (body.channel or "").lower().strip() or None
        chosen = requested or ("telegram" if tg_ok else ("email" if email_ok else None))

        if chosen == "telegram" and not tg_ok:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                tr("К аккаунту не привязан Telegram.", current_locale()),
            )
        if chosen == "email" and not email_ok:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                tr("Отправка на email недоступна.", current_locale()),
            )
        if chosen not in ("telegram", "email"):
            try:
                await append_audit_entry(
                    db, actor_id=str(user.id), actor_email=user.email,
                    action="auth.forgot_password.init_no_channel", entity_type="auth",
                    ip_address=_client_ip(request),
                )
                await db.commit()
            except Exception:
                await db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                tr(
                    "Нет доступного канала восстановления. Обратитесь к администратору.",
                    current_locale(),
                ),
            )

        reset_id = secrets.token_urlsafe(24)
        code = mfa_service._gen_login_code()
        user.password_reset_token_hashed = mfa_service._hash_sha256(reset_id)
        user.password_reset_code_hashed = mfa_service._hash_bcrypt(code)
        user.password_reset_expires_at = (
            datetime.now(UTC) + timedelta(minutes=RESET_TTL_MINUTES)
        )
        user.password_reset_attempts = 0

        if chosen == "telegram":
            await mfa_service.enqueue_telegram_message(
                db, user_id=user.id, msg_type=OutboxType.MFA_CODE,
                payload={
                    "code": code, "purpose": "password_reset",
                    "ttl_minutes": RESET_TTL_MINUTES,
                    "subject": tr("Код восстановления пароля", locale),
                    "locale": locale,
                },
            )
            msg = tr("Код отправлен в Telegram.", current_locale())
        else:  # email
            from app.services.email import templates as _tpl
            subj, html = _tpl.notification_email(
                eyebrow=tr("Сброс пароля", locale),
                title=tr("Код восстановления пароля", locale),
                accent="#111A3E",
                lines=[
                    tr(
                        "Ваш код для восстановления доступа: {code}", locale,
                        code=f'<b style="font-size:20px;letter-spacing:.12em;color:#1E2A4A">{code}</b>',
                    ),
                    tr(
                        "Код действителен {minutes} минут. Если вы не запрашивали сброс — проигнорируйте письмо.",
                        locale, minutes=f"<b>{RESET_TTL_MINUTES}</b>",
                    ),
                ],
                locale=locale,
            )
            await send_email(user.email, subj, html, locale=locale)
            msg = tr("Код отправлен на email.", current_locale())

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="auth.forgot_password.init", entity_type="auth",
            ip_address=_client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:512],
            notes=f"reset_code issued via {chosen} (ttl={RESET_TTL_MINUTES}m)",
        )
        await db.commit()

        return ForgotInitResponse(
            reset_id=reset_id,
            ttl_minutes=RESET_TTL_MINUTES,
            channel=chosen,
            masked_telegram=_mask_tg_username(user.telegram_username) if chosen == "telegram" else None,
            masked_email=_mask_email(user.email) if chosen == "email" else None,
            message=msg,
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
                tr("Неверный код или истёк срок действия", current_locale()),
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
                tr("Код истёк. Запросите новый.", current_locale()),
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
                    tr(
                        "Превышено количество попыток. Запросите новый код.",
                        current_locale(),
                    ),
                )
            await db.commit()
            remaining = MAX_CODE_ATTEMPTS - user.password_reset_attempts
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                tr(
                    "Неверный код. Осталось попыток: {remaining}",
                    current_locale(), remaining=remaining,
                ),
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

        # Security (audit H-3): отозвать ВСЕ активные сессии/токены — иначе сессия
        # атакующего (refresh до 14 дней, access до 30 мин) переживала сброс пароля.
        # revoke_all_sessions внутри вызывает bump_tokens_invalid_before. Выровнено
        # с self-service change_password (auth_service:518).
        from app.services.auth_service import revoke_all_sessions
        await revoke_all_sessions(db, user.id)

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
            title_template="Пароль изменён",
            body_template="Пароль вашего аккаунта был сброшен. Если это были не вы — немедленно обратитесь к администратору.",
        )

        return ForgotVerifyResponse(
            ok=True, mfa_required=bool(user.mfa_enabled),
        )
