"""Auth endpoints: login, refresh, logout, me, change-password, twa-login.

Thin HTTP shim (refactored 2026-05-25). Logic in `services/auth_user/`.
Core `app.services.auth_service` + `twa_auth_service` NOT touched.

Rate-limit RATE_LIMIT_AUTH applies to login/refresh/change-password/twa-login.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
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


async def _enrich_org(pub: UserPublic, user: User, db: AsyncSession) -> UserPublic:
    """Заполнить company/sector/org_profile_set в UserPublic из organization_id."""
    pub.org_profile_set = bool(getattr(user, "org_profile_set", False))
    org_id = getattr(user, "organization_id", None)
    if org_id:
        from sqlalchemy import select

        from app.models.company import Company, Sector
        row = (await db.execute(
            select(Company.name_ru, Sector.name_ru.label("sector"))
            .outerjoin(Sector, Sector.id == Company.sector_id)
            .where(Company.id == org_id)
        )).first()
        if row:
            pub.company = row.name_ru
            pub.sector = row.sector
    return pub


@router.get("/me", response_model=UserPublic)
async def me(
    service: AuthUserServiceDep,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    """Return profile for the currently authenticated user (id, email, roles, flags).

    Used by the frontend on app load to hydrate the auth store."""
    return await _enrich_org(service.me(user), user, db)


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
    # Соцссылки — нормализуем (https:// если без схемы), "" = удалить.
    for f in ("linkedin_url", "website_url"):
        if f in data:
            raw = (data[f] or "").strip()
            if not raw:
                setattr(u, f, None)
                continue
            if len(raw) > 512:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка слишком длинная")
            if not raw.lower().startswith(("http://", "https://")):
                raw = "https://" + raw
            setattr(u, f, raw)
    # Компания: юзер задаёт ОДИН раз (first-time). Повторно — игнор (только админ).
    if "organization_id" in data and data["organization_id"] and not u.org_profile_set:
        u.organization_id = data["organization_id"]
        u.org_profile_set = True
    await db.commit()
    await db.refresh(u)
    return await _enrich_org(service.me(u), u, db)


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


def _req_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/sessions")
async def list_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Активные сессии текущего пользователя (страница безопасности, 841 5.2.2.3)."""
    from app.services import auth_service
    return await auth_service.list_active_sessions(
        db, user.id, ip=_req_ip(request), ua=request.headers.get("user-agent"))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_one_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Завершить конкретную свою сессию."""
    import uuid

    from app.services import auth_service
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad session id")
    if not await auth_service.revoke_session(db, user.id, sid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")


@router.post("/sessions/revoke-others")
async def revoke_other_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Завершить все сессии, кроме текущей."""
    from app.services import auth_service
    n = await auth_service.revoke_other_sessions(
        db, user.id, ip=_req_ip(request), ua=request.headers.get("user-agent"))
    return {"revoked": n}


class ReauthRequest(BaseModel):
    password: str


@router.post("/reauth", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def reauth(
    request: Request,
    body: ReauthRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Step-up re-auth (841 п.5.2.4): повторный ввод пароля → обновляет
    last_strong_auth_at, разблокируя чувствительные операции на короткое окно."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.core import password as pw
    u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    if not u.password_hash or not pw.verify_password(body.password, u.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный пароль")
    u.last_strong_auth_at = datetime.now(UTC)
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
