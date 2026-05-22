"""Forgot-password flow (Pack 152) — Telegram-code based.

Flow:
  1. POST /auth/forgot-password         { login }      → enqueue 6-digit code to TG
  2. POST /auth/forgot-password/verify  { reset_id, code, new_password } → set new password

Security:
  - Generic-response on init (даже если user не найден / без TG) — anti-enumeration
  - Bcrypt-hashed reset_code (как с MFA challenge); SHA256-hashed reset_id
  - TTL 5 minutes
  - Max 5 неверных попыток ввода кода → reset state кляйрится, нужно запросить новый
  - Rate-limit 5/hour per IP (init), 10/hour per IP (verify)
  - Audit_log для init + verify (both success + failure)
"""
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.password import hash_password, validate_password_policy
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.models.mfa import OutboxType
from app.services import mfa_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/forgot-password", tags=["auth"])

RESET_TTL_MINUTES = 5
MAX_CODE_ATTEMPTS = 5


# ─── Schemas ────────────────────────────────────────────────────────────

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


# ─── Helpers ────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> Optional[str]:
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


def _mask_tg_username(username: Optional[str]) -> str:
    if not username:
        return "@***"
    if len(username) <= 4:
        return f"@***{username[-1:]}"
    return f"@***{username[-3:]}"


# ─── Endpoint 1: init ───────────────────────────────────────────────────

@router.post("", response_model=ForgotInitResponse)
@limiter.limit("5/hour")
async def forgot_init(
    request: Request,
    body: ForgotInitRequest,
    db: AsyncSession = Depends(get_db),
):
    login = body.login.strip()
    login_lc = login.lower()

    user = (await db.execute(
        select(User).where(
            or_(
                User.email == login_lc,
                User.username == login,
            )
        )
    )).scalar_one_or_none()

    # Явные ошибки (по требованию пользователя — мэтч с существующими аккаунтами).
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Аккаунт с таким email или логином не найден.")

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
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "К аккаунту не привязан Telegram. Обратитесь к администратору.")

    # Generate reset_id + code; store hashed
    reset_id = secrets.token_urlsafe(24)
    code = mfa_service._gen_login_code()  # "123456"

    user.password_reset_token_hashed = mfa_service._hash_sha256(reset_id)
    user.password_reset_code_hashed = mfa_service._hash_bcrypt(code)
    user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TTL_MINUTES)
    user.password_reset_attempts = 0

    # Enqueue to TG bot
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


# ─── Endpoint 2: verify + set new password ──────────────────────────────

@router.post("/verify", response_model=ForgotVerifyResponse)
@limiter.limit("10/hour")
async def forgot_verify(
    request: Request,
    body: ForgotVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    reset_hash = mfa_service._hash_sha256(body.reset_id)
    user = (await db.execute(
        select(User).where(User.password_reset_token_hashed == reset_hash)
    )).scalar_one_or_none()

    if not user:
        # Generic — don't leak whether reset_id exists
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный код или истёк срок действия")

    now = datetime.now(timezone.utc)
    if not user.password_reset_expires_at or user.password_reset_expires_at < now:
        # Clear state
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код истёк. Запросите новый.")

    # Verify code (bcrypt) — используем _check_bcrypt, парный к _hash_bcrypt из mfa_service
    # (НЕ core.password.verify_password — там SHA-512 prehash, hashes несовместимы).
    if not mfa_service._check_bcrypt(body.code, user.password_reset_code_hashed or ""):
        user.password_reset_attempts = (user.password_reset_attempts or 0) + 1
        if user.password_reset_attempts >= MAX_CODE_ATTEMPTS:
            _clear_reset_state(user)
            await append_audit_entry(
                db, actor_id=str(user.id), actor_email=user.email,
                action="auth.forgot_password.attempts_exceeded",
                entity_type="auth", ip_address=_client_ip(request), is_critical=True,
            )
            await db.commit()
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Превышено количество попыток. Запросите новый код.")
        await db.commit()
        remaining = MAX_CODE_ATTEMPTS - user.password_reset_attempts
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Неверный код. Осталось попыток: {remaining}")

    # Validate password policy
    try:
        validate_password_policy(body.new_password)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    # Set new password + clean account state
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

    return ForgotVerifyResponse(ok=True, mfa_required=bool(user.mfa_enabled))


def _clear_reset_state(user: User) -> None:
    user.password_reset_token_hashed = None
    user.password_reset_code_hashed = None
    user.password_reset_expires_at = None
    user.password_reset_attempts = 0
