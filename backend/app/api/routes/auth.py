"""Auth endpoints: login, refresh, logout, me, change-password, twa-login.

Thin HTTP shim (refactored 2026-05-25). Logic in `services/auth_user/`.
Core `app.services.auth_service` + `twa_auth_service` NOT touched.

Rate-limit RATE_LIMIT_AUTH applies to login/refresh/change-password/twa-login.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.database import get_db
from app.dependencies.auth_user import AuthUserServiceDep
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    UpdateMeRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserPublic,
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
    """Authenticate with email + password. Returns RS256-signed access + refresh JWT pair.

    Rate-limited per IP. If user has MFA enabled, returns `mfa_required: true`
    instead of tokens — caller must then POST /auth/login-mfa with the code."""
    return await service.login(body, request, db)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh(
    request: Request,
    body: RefreshRequest,
    service: AuthUserServiceDep,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Exchange a valid refresh token for a new access+refresh pair.

    Refresh tokens are single-use: the returned new refresh token replaces the
    old one, and the old one is invalidated."""
    return await service.refresh(body, request, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    service: AuthUserServiceDep,
    body: LogoutRequest = LogoutRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Invalidate the current user's tokens by bumping `tokens_invalid_before`.

    Any access/refresh token issued before this moment is rejected. Use
    `body.all_devices=true` to invalidate every session globally."""
    await service.logout(body, user, request, db)


@router.get("/me", response_model=UserPublic)
async def me(
    service: AuthUserServiceDep,
    user: User = Depends(get_current_user),
) -> UserPublic:
    """Return profile for the currently authenticated user (id, email, roles, flags).

    Used by the frontend on app load to hydrate the auth store."""
    return service.me(user)


@router.patch("/me", response_model=UserPublic)
async def update_me(
    body: UpdateMeRequest,
    service: AuthUserServiceDep,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    """Самостоятельное редактирование своего профиля: ФИО, должность,
    телефон, отдел. Email/роли/доступы менять нельзя — только админ."""
    from sqlalchemy import select
    u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    data = body.model_dump(exclude_unset=True)
    # Фото (data-URL) — отдельно: проверяем размер и формат, "" = удалить.
    if "avatar_url" in data:
        av = (data.pop("avatar_url") or "").strip()
        if av and not av.startswith("data:image/"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Некорректный формат фото")
        if len(av) > 300_000:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Фото слишком большое (уменьшите изображение)")
        u.avatar_url = av or None
    for f in ("full_name", "job_title", "phone", "department"):
        if f in data:
            v = data[f]
            setattr(u, f, (v.strip() if isinstance(v, str) and v.strip() else (v if v else None)))
    await db.commit()
    await db.refresh(u)
    return service.me(u)


@router.post("/me/welcome-seen", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_welcome(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Отметить, что приветственное окно первого входа показано (больше не
    показывать)."""
    from sqlalchemy import select
    u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    if not u.welcome_seen:
        u.welcome_seen = True
        await db.commit()


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    service: AuthUserServiceDep,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change password for the current user. Requires the old password.

    On success, also bumps `tokens_invalid_before` — other sessions are
    invalidated and the caller must re-login."""
    await service.change_password(body, user, request, db)


@router.post("/twa-login", response_model=TokenPair, status_code=status.HTTP_200_OK)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def twa_login(
    request: Request,
    body: TwaLoginIn,
    service: AuthUserServiceDep,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Telegram Web App auto-login: verifies `initData` HMAC against bot token,
    finds the linked user by `telegram_user_id`, and returns a regular JWT pair.

    Bypasses MFA — the Telegram link itself is the second factor."""
    return await service.twa_login(body, request, db)
