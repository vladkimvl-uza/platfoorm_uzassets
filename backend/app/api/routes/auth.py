"""Auth endpoints: login, refresh, logout, me, change-password.

The auth bucket of slowapi is applied here (10/min by default — much stricter
than the API bucket) to slow down credential-stuffing."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.core.security import get_current_user, _user_permission_codes
from app.database import get_db
from app.models.user import Role, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserPublic,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


# =====================================================================
# Helpers
# =====================================================================

def _client_ip(request: Request) -> Optional[str]:
    """Resolve the client IP, preferring X-Forwarded-For from a trusted proxy."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


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


# =====================================================================
# POST /auth/login
# =====================================================================

@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Username/email + password → JWT access + refresh.

    Rate-limited to RATE_LIMIT_AUTH per IP (default: 10/min).
    Lockout: after LOGIN_MAX_FAILED_ATTEMPTS the account is locked for
    LOGIN_LOCKOUT_MINUTES.
    """
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


# =====================================================================
# POST /auth/refresh
# =====================================================================

@router.post("/refresh", response_model=TokenPair)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Rotate the refresh token. Old refresh is revoked, new pair issued.

    If the same refresh is presented twice (replay), all sessions of that
    user are revoked as a defense-in-depth measure."""
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


# =====================================================================
# POST /auth/logout
# =====================================================================

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    body: LogoutRequest = LogoutRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke the supplied refresh token (or just record the logout)."""
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")[:512]
    await auth_service.logout(
        db, user=user,
        refresh_token=body.refresh_token,
        ip=ip, user_agent=ua,
    )
    return None


# =====================================================================
# GET /auth/me
# =====================================================================

@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(get_current_user)) -> UserPublic:
    """Return the current user — including roles and permissions."""
    return _user_to_public(user)


# =====================================================================
# POST /auth/change-password
# =====================================================================

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change own password. Revokes all existing sessions on success."""
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")[:512]
    await auth_service.change_password(
        db, user=user,
        current=body.current_password,
        new=body.new_password,
        ip=ip, user_agent=ua,
    )
    return None
