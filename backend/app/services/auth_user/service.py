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

from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import _user_permission_codes
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest, LoginRequest, LogoutRequest,
    RefreshRequest, TokenPair, UserPublic,
)
from app.services import auth_service, twa_auth_service


class TwaLoginIn(BaseModel):
    init_data: str


def _client_ip(request: Request) -> Optional[str]:
    """Trusted-proxy-aware client IP resolution."""
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


def _user_to_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_owner=user.is_owner,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        organization_id=user.organization_id,
        department=user.department,
        job_title=user.job_title,
        last_login_at=user.last_login_at,
        roles=[r.code for r in user.roles],
        permissions=sorted(_user_permission_codes(user)),
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

    def me(self, user: User) -> UserPublic:
        return _user_to_public(user)

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
