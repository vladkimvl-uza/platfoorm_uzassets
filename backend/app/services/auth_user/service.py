"""Auth use-cases — thin wrapper over `app.services.auth_service` (core).

Core auth_service NOT touched. Endpoints encapsulated:
  POST /auth/login              login + lockout + rehash
  POST /auth/refresh            rotate refresh; replay → revoke all sessions
  POST /auth/logout             revoke refresh
  GET  /auth/me                 current user (roles + permissions)
  POST /auth/change-password    own pw + revoke all sessions
  POST /auth/twa-login          Telegram WebApp initData → JWT pair
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import _user_permission_codes
from app.models.user import User
from app.repositories.rbac_v3_repository import RbacV3Repository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserPublic,
)
from app.services import auth_service, twa_auth_service

log = logging.getLogger(__name__)


class TwaLoginIn(BaseModel):
    init_data: str


def _client_ip(request: Request) -> Optional[str]:
    """Trusted-proxy-aware client IP resolution."""
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


def _is_privileged(user: User) -> bool:
    """Owner или роль admin — для них MFA обязательна."""
    if getattr(user, "is_owner", False):
        return True
    return any((getattr(r, "code", "") or "").lower() == "admin" for r in (user.roles or []))


def _user_to_public(user: User, permissions: list[str] | None = None) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        mfa_setup_required=_is_privileged(user) and not getattr(user, "mfa_enabled", False),
        username=user.username,
        full_name=user.full_name,
        is_owner=user.is_owner,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        organization_id=user.organization_id,
        department=user.department,
        job_title=user.job_title,
        phone=getattr(user, "phone", None),
        avatar_url=getattr(user, "avatar_url", None),
        linkedin_url=getattr(user, "linkedin_url", None),
        website_url=getattr(user, "website_url", None),
        telegram_username=getattr(user, "telegram_username", None),
        # Язык интерфейса из профиля: без него /auth/me всегда отдавал бы дефолт
        # 'ru', и сохранённый выбор языка не применялся бы при входе на новом
        # устройстве (PATCH /auth/me его пишет, а читать было нечему).
        ui_locale=getattr(user, "ui_locale", None) or "ru",
        last_login_at=user.last_login_at,
        welcome_seen=getattr(user, "welcome_seen", False),
        roles=[r.code for r in user.roles],
        permissions=sorted(permissions if permissions is not None else _user_permission_codes(user)),
    )


@dataclass
class AuthUserService:
    async def login(
        self, body: LoginRequest, request: Request, db: AsyncSession,
    ) -> TokenPair:
        ip = _client_ip(request)
        ua = request.headers.get("user-agent", "")[:512]
        user, access, refresh = await auth_service.authenticate(
            db,
            login_id=body.login,
            password=body.password,
            ip=ip,
            user_agent=ua,
        )
        # Security (ИБ-аудит, CRITICAL): /auth/login НЕ выдаёт токены пользователям
        # с включённой MFA — иначе обход второго фактора прямым POST. Такие юзеры
        # обязаны идти через /auth/login-mfa (фронт использует именно его; этот
        # эндпоинт фронтом не вызывается). Fail-closed.
        if getattr(user, "mfa_enabled", False):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Для аккаунта включена двухфакторная аутентификация — "
                "вход выполняется через /auth/login-mfa.",
            )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            token_type="Bearer",
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )

    async def refresh(
        self, body: RefreshRequest, request: Request, db: AsyncSession,
    ) -> TokenPair:
        ip = _client_ip(request)
        ua = request.headers.get("user-agent", "")[:512]
        user, access, new_refresh = await auth_service.refresh_tokens(
            db,
            refresh_token=body.refresh_token,
            ip=ip,
            user_agent=ua,
        )
        return TokenPair(
            access_token=access,
            refresh_token=new_refresh,
            token_type="Bearer",
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )

    async def logout(
        self,
        body: LogoutRequest,
        user: User,
        request: Request,
        db: AsyncSession,
    ) -> None:
        ip = _client_ip(request)
        ua = request.headers.get("user-agent", "")[:512]
        await auth_service.logout(
            db, user=user,
            refresh_token=body.refresh_token,
            ip=ip, user_agent=ua,
        )

    async def me(self, user: User, db: AsyncSession) -> UserPublic:
        try:
            # SAVEPOINT, а НЕ голый try: любая ошибка SQL переводит транзакцию в
            # aborted-состояние, и следующий SELECT в этом же HTTP-запросе
            # (_enrich_org в /auth/me и PATCH /me) падает с InFailedSqlTransaction.
            # Полный db.rollback() тут не годится: он экспарит ВСЕ ORM-объекты
            # сессии (в т.ч. загруженный get_current_user `user`), и первое же
            # обращение к user.id / user.roles / user.organization_id в async-коде
            # даёт MissingGreenlet — то есть fallback снова не срабатывает.
            # Откат до savepoint чинит транзакцию и не трогает identity map.
            async with db.begin_nested():
                permissions = await RbacV3Repository(db).effective_permission_codes(user.id)
        except Exception as e:
            # Решение владельца (29.07.2026): FAIL-CLOSED. Прежний fallback отдавал
            # набор из одних глобальных ролей — он не знает ролей в группах и
            # грантов, а главное НЕ ВЫЧИТАЕТ deny: отозванное право возвращалось в
            # интерфейс при любом сбое запроса, и тот же набор служил потолком прав
            # для проверок назначения. Лучше выкинуть пользователя из интерфейса
            # с явной ошибкой, чем тихо выдать ему отозванный доступ.
            log.error(
                "effective_permission_codes failed for user %s — /auth/me "
                "отвечает 503 (fail-closed, права не выдаются)", user.id,
                exc_info=True,
            )
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Не удалось вычислить права доступа. Повторите попытку позже; "
                "если ошибка повторяется — обратитесь к администратору.",
            ) from e
        return _user_to_public(user, permissions)

    async def change_password(
        self,
        body: ChangePasswordRequest,
        user: User,
        request: Request,
        db: AsyncSession,
    ) -> None:
        ip = _client_ip(request)
        ua = request.headers.get("user-agent", "")[:512]
        await auth_service.change_password(
            db, user=user,
            current=body.current_password,
            new=body.new_password,
            ip=ip, user_agent=ua,
        )

    async def twa_login(
        self, body: TwaLoginIn, request: Request, db: AsyncSession,
    ) -> TokenPair:
        ip = _client_ip(request)
        ua = request.headers.get("user-agent", "")[:512]
        user, access, refresh = await twa_auth_service.authenticate_via_initdata(
            db,
            init_data=body.init_data,
            ip=ip,
            user_agent=ua,
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            token_type="Bearer",
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )
