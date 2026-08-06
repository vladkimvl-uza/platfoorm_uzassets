"""MFA-aware login orchestration (Pack 13.0c).

Does NOT take a UnitOfWork — multi-step flow piggybacks on `auth_service.
authenticate()` which manages its own commit, then opens a fresh transaction
on the same session. Service operates directly on `AsyncSession`.

Both core helpers (`auth_service`, `mfa_service`) remain untouched. This
module only owns the wiring between them: revoke the just-issued session on
MFA-required users, emit a challenge, then on verify mint a fresh pair.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_, select, text
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.schemas.auth_mfa import LoginMfaResponse, VerifyMfaIn
from app.config import settings
from app.core import jwt as app_jwt
from app.models.mfa import MfaLoginChallenge
from app.models.user import Role, User, UserSession
from app.schemas.auth import LoginRequest, TokenPair
from app.services import auth_service, mfa_service

log = logging.getLogger(__name__)


def _mask_destination(user: User) -> str:
    username = getattr(user, "telegram_username", None)
    if not username:
        return "Telegram"
    if len(username) > 4:
        return f"@{username[:2]}***{username[-2:]}"
    return "@***"


def _dev_mfa_bypass_active() -> bool:
    """DEV_DISABLE_MFA env opt-out — refuses to activate in prod."""
    return (
        (os.getenv("DEV_DISABLE_MFA") or "").lower() in ("1", "true", "yes", "on")
        and not getattr(settings, "is_production", False)
    )


def _trusted_ip_hours() -> int:
    """Окно «доверенного IP» в часах: при входе с того же IP в пределах окна
    второй фактор повторно не спрашивается. 0 → фича выключена.
    Настраивается env MFA_TRUSTED_IP_HOURS (по умолчанию 12)."""
    try:
        return max(0, int(os.getenv("MFA_TRUSTED_IP_HOURS", "12") or "12"))
    except ValueError:
        return 12


@dataclass
class AuthMfaService:
    """Stateless orchestrator. Methods take `AsyncSession` because the
    flow straddles auth_service's own transaction commit."""

    async def login_mfa(
        self,
        db: AsyncSession,
        body: LoginRequest,
        *,
        ip: Optional[str],
        ua: str,
    ) -> LoginMfaResponse:
        user, access, refresh = await auth_service.authenticate(
            db,
            login_id=body.login,
            password=body.password,
            ip=ip,
            user_agent=ua,
        )
        # authenticate() commits its own work. New implicit tx below.

        mfa_row = await db.execute(
            text(
                "SELECT mfa_enabled, mfa_method::text AS mfa_method, "
                "telegram_chat_id_encrypted IS NOT NULL AS tg_linked, "
                "telegram_username FROM users WHERE id = :id"
            ),
            {"id": user.id},
        )
        mfa_data = mfa_row.first()
        mfa_enabled = bool(mfa_data.mfa_enabled) if mfa_data else False
        mfa_method = (mfa_data.mfa_method or "none") if mfa_data else "none"
        tg_linked = bool(mfa_data.tg_linked) if mfa_data else False
        log.warning(
            "login-mfa-raw: user=%s mfa_enabled=%s method=%s tg=%s",
            user.email, mfa_enabled, mfa_method, tg_linked,
        )

        dev_bypass = _dev_mfa_bypass_active()
        if dev_bypass and mfa_enabled:
            log.warning(
                "DEV_DISABLE_MFA active — bypassing MFA for %s (dev only)",
                user.email,
            )

        if not mfa_enabled or dev_bypass:
            return LoginMfaResponse(
                mfa_required=False,
                access_token=access,
                refresh_token=refresh,
                token_type="Bearer",
                expires_in=settings.JWT_EXPIRE_MINUTES * 60,
            )

        # Доверенный IP в пределах таймаута → второй фактор повторно не спрашиваем.
        if ip and _trusted_ip_hours() > 0 and await self._is_trusted_ip(db, user.id, ip):
            log.info("MFA skipped for %s — trusted IP within timeout", user.email)
            return LoginMfaResponse(
                mfa_required=False,
                access_token=access,
                refresh_token=refresh,
                token_type="Bearer",
                expires_in=settings.JWT_EXPIRE_MINUTES * 60,
            )

        # Telegram-канал удалён (05.08.2026), а другого способа доставки кода
        # не было — TOTP в enum есть, но не реализован. Поэтому включённый
        # где-то ещё 2FA НЕ должен запирать вход: пропускаем и гасим флаг,
        # чтобы человек не остался без доступа (раньше здесь был 500).
        if mfa_method in ("telegram", "both") or not tg_linked:
            log.warning(
                "MFA у %s включён, но канал доставки удалён — вход без второго "
                "фактора, флаг снят", user.email,
            )
            try:
                await db.execute(
                    text("UPDATE users SET mfa_enabled = false, "
                         "mfa_method = 'none' WHERE id = :uid"),
                    {"uid": str(user.id)},
                )
                await db.commit()
            except Exception:
                await db.rollback()
            return LoginMfaResponse(
                mfa_required=False,
                access_token=access,
                refresh_token=refresh,
                token_type="Bearer",
                expires_in=settings.JWT_EXPIRE_MINUTES * 60,
            )

        await self._revoke_session_by_refresh(db, refresh)

        try:
            challenge, _plain_code = await mfa_service.emit_login_challenge(
                db, user, ip=ip, ua=ua,
            )
        except ValueError as e:
            await db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        await db.commit()

        return LoginMfaResponse(
            mfa_required=True,
            challenge_id=str(challenge.id),
            method=mfa_method if mfa_method in ("telegram", "totp", "both") else "telegram",
            masked_destination=_mask_destination(user),
            ttl_minutes=mfa_service.LOGIN_CODE_TTL_MINUTES,
        )

    async def verify_mfa(
        self,
        db: AsyncSession,
        body: VerifyMfaIn,
        *,
        ip: Optional[str],
        ua: str,
    ) -> TokenPair:
        user: Optional[User] = None

        if body.challenge_id and body.code:
            ok = await mfa_service.verify_login_challenge(
                db, body.challenge_id, body.code.strip()
            )
            if not ok:
                await db.commit()
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    "Неверный код или истёк срок действия",
                )
            challenge: Optional[MfaLoginChallenge] = (
                await db.execute(
                    select(MfaLoginChallenge).where(
                        MfaLoginChallenge.id == body.challenge_id
                    )
                )
            ).scalar_one_or_none()
            if challenge is None:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, "Challenge не найден"
                )
            user = await self._load_user_with_roles(db, challenge.user_id)

        elif body.login and body.recovery_code:
            needle = body.login.strip().lower()
            user = (
                await db.execute(
                    select(User)
                    .where(or_(User.email.ilike(needle), User.username.ilike(needle)))
                    .options(selectinload(User.roles).selectinload(Role.permissions))
                )
            ).scalar_one_or_none()
            if (
                user is None
                or not user.is_active
                or not getattr(user, "mfa_enabled", False)
            ):
                await db.commit()
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, "Неверный recovery-код"
                )
            ok = await mfa_service.verify_recovery_code(
                db, user, body.recovery_code.strip()
            )
            if not ok:
                await db.commit()
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, "Неверный recovery-код"
                )
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Передайте challenge_id + code ИЛИ login + recovery_code",
            )

        if user is None or not user.is_active:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Пользователь не найден или отключён",
            )

        access, refresh = await self._issue_tokens_for_user(db, user, ip, ua)
        # Успешный второй фактор → запоминаем IP как доверенный на время таймаута.
        if ip and _trusted_ip_hours() > 0:
            await self._remember_trusted_ip(db, user.id, ip)
        await db.commit()

        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            token_type="Bearer",
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )

    # ─── Internal helpers ─────────────────────────────────────────

    @staticmethod
    async def _is_trusted_ip(db: AsyncSession, user_id, ip: str) -> bool:
        """True, если у юзера есть непросроченная запись доверенного IP."""
        row = await db.execute(
            text(
                "SELECT 1 FROM mfa_trusted_ips "
                "WHERE user_id = :u AND ip = :ip AND expires_at > now() LIMIT 1"
            ),
            {"u": user_id, "ip": ip},
        )
        return row.first() is not None

    @staticmethod
    async def _remember_trusted_ip(db: AsyncSession, user_id, ip: str) -> None:
        """Запомнить IP как доверенный на MFA_TRUSTED_IP_HOURS часов (upsert)."""
        hrs = _trusted_ip_hours()
        if hrs <= 0:
            return
        await db.execute(
            text(
                "INSERT INTO mfa_trusted_ips (user_id, ip, expires_at) "
                "VALUES (:u, :ip, now() + make_interval(hours => :hrs)) "
                "ON CONFLICT (user_id, ip) DO UPDATE SET expires_at = EXCLUDED.expires_at"
            ),
            {"u": user_id, "ip": ip, "hrs": hrs},
        )

    @staticmethod
    async def _load_user_with_roles(
        db: AsyncSession, user_id
    ) -> Optional[User]:
        result = await db.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _revoke_session_by_refresh(
        db: AsyncSession, refresh_token: str
    ) -> None:
        try:
            claims = app_jwt.decode_token(refresh_token, expected_type="refresh")
        except Exception as e:
            log.warning("Could not decode just-issued refresh for revocation: %s", e)
            return
        jti = claims.get("jti")
        if not jti:
            return
        h = app_jwt.hash_jti(jti)
        session = (
            await db.execute(
                select(UserSession).where(UserSession.refresh_token_hash == h)
            )
        ).scalar_one_or_none()
        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)

    @staticmethod
    async def _issue_tokens_for_user(
        db: AsyncSession, user: User, ip: Optional[str], user_agent: Optional[str],
    ) -> tuple[str, str]:
        access = app_jwt.create_access_token(
            subject=str(user.id),
            extra_claims={
                "email": user.email,
                "is_owner": user.is_owner,
                "roles": [r.code for r in user.roles],
            },
        )
        refresh, jti = app_jwt.create_refresh_token(subject=str(user.id))
        from app.services.auth_service import _prune_concurrent_sessions
        await _prune_concurrent_sessions(db, user.id)
        db.add(UserSession(
            user_id=user.id,
            refresh_token_hash=app_jwt.hash_jti(jti),
            expires_at=datetime.now(UTC)
                + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
            session_started_at=datetime.now(UTC),
            ip_address=ip,
            user_agent=user_agent,
        ))
        user.last_login_at = datetime.now(UTC)
        user.last_strong_auth_at = datetime.now(UTC)  # MFA = сильная аутентификация
        if ip:
            user.last_login_ip = ip
        return access, refresh
