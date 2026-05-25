"""Auth endpoints: login, refresh, logout, me, change-password, twa-login.

Thin HTTP shim (refactored 2026-05-25). Logic in `services/auth_user/`.
Core `app.services.auth_service` + `twa_auth_service` NOT touched.

Rate-limit RATE_LIMIT_AUTH applies to login/refresh/change-password/twa-login.
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.database import get_db
from app.dependencies.auth_user import AuthUserServiceDep
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest, LoginRequest, LogoutRequest,
    RefreshRequest, TokenPair, UserPublic,
)
from app.services.auth_user.service import TwaLoginIn


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    body: LoginRequest,
    service: AuthUserServiceDep,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    return await service.login(body, request, db)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh(
    request: Request,
    body: RefreshRequest,
    service: AuthUserServiceDep,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    return await service.refresh(body, request, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    service: AuthUserServiceDep,
    body: LogoutRequest = LogoutRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.logout(body, user, request, db)


@router.get("/me", response_model=UserPublic)
async def me(
    service: AuthUserServiceDep,
    user: User = Depends(get_current_user),
) -> UserPublic:
    return service.me(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    service: AuthUserServiceDep,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.change_password(body, user, request, db)


@router.post("/twa-login", response_model=TokenPair, status_code=status.HTTP_200_OK)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def twa_login(
    request: Request,
    body: TwaLoginIn,
    service: AuthUserServiceDep,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    return await service.twa_login(body, request, db)
