"""FastAPI dependencies for authentication and RBAC.

Usage in route handlers:
    @router.get("/secret")
    async def secret(user = Depends(get_current_user)):
        return {"hi": user.email}

    @router.post("/admin/users", dependencies=[Depends(require_permission("users.create"))])
    async def create_user(...):
        ...

    @router.post("/contracts/{id}/approve", dependencies=[Depends(require_role("procurement_owner"))])
    async def approve(...):
        ...

Permission resolution (Pack 144 / fix C1):
  * is_owner OR role `admin` → bypass.
  * Иначе берётся объединение прав из ролей и group_permission_grant (grant),
    минус group_permission_grant (deny). Истёкшие grants игнорируются.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from jwt import InvalidTokenError

from app.core import jwt as app_jwt
from app.database import get_db
from app.models.user import Role, User


# Bearer scheme — auto_error=False so we can return 401 with our own message
_bearer = HTTPBearer(auto_error=False, bearerFormat="JWT")


# =====================================================================
# Core: extract current user from Authorization: Bearer <jwt>
# =====================================================================

async def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the access token, load the user (with roles + permissions).

    Accepts BOTH:
      - JWT access tokens (legacy / user sessions)
      - API key tokens with prefix `uza_pk_live_` or `uza_pk_test_` (Pack 12.0)

    For API key tokens, the linked service account user is returned and
    `request.state.api_key` is populated. The scope check for the endpoint's
    required permission is enforced by require_permission().

    Raises 401 on missing/invalid/expired token, 403 on inactive/locked user.
    """
    if creds is None or not creds.credentials:
        raise _unauthorized("Missing Authorization header")

    token = creds.credentials

    # ─── Pack 12.0: API key path ───────────────────────────────
    if token.startswith(("uza_pk_live_", "uza_pk_test_")):
        from app.services.api_key_service import ApiKeyAuthError, verify_token, record_call
        client_ip = request.client.host if request.client else None
        try:
            api_key, sa_user = await verify_token(db, token, client_ip=client_ip)
        except ApiKeyAuthError as e:
            raise _unauthorized(f"API key: {e.code}")

        # Фикс L5: даже валидный API-ключ должен отказывать, если связанный
        # service account деактивирован.
        if not sa_user.is_active:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Service account is disabled",
            )

        # Update telemetry (non-fatal if it fails)
        try:
            await record_call(db, api_key, client_ip=client_ip, success=True)
            await db.commit()
        except Exception:
            await db.rollback()

        request.state.user = sa_user
        request.state.api_key = api_key
        request.state.auth_method = "api_key"
        return sa_user

    # ─── JWT path (original) ───────────────────────────────────
    try:
        claims = app_jwt.decode_token(token, expected_type="access")
    except InvalidTokenError as e:
        raise _unauthorized(f"Invalid token: {type(e).__name__}")

    user_id = claims.get("sub")
    if not user_id:
        raise _unauthorized("Token missing subject")

    # Eager-load roles + permissions so RBAC checks don't hit DB again
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user: Optional[User] = result.scalar_one_or_none()

    if user is None:
        raise _unauthorized("User not found")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    # Stash on request.state for rate-limiter and audit middleware
    request.state.user = user
    return user


# =====================================================================
# Permission helpers
# =====================================================================

def _user_permission_codes(user: User) -> Set[str]:
    """Flatten all permission codes the user has via their roles."""
    perms: Set[str] = set()
    for role in user.roles:
        perms.update(p.code for p in role.permissions)
    return perms


def _user_role_codes(user: User) -> Set[str]:
    return {r.code for r in user.roles}


def is_super_admin(user: User) -> bool:
    """Owner или носитель роли `admin` — глобальный bypass.

    Единая точка для проверки "is this user effectively a superuser?".
    Используется везде, где раньше дублировалась логика
    `user.is_owner or "admin" in role_codes`. Фронт должен зеркалить эту
    же логику (см. rbacV3.ts::deriveAccessMap).
    """
    if user.is_owner:
        return True
    return "admin" in _user_role_codes(user)


def _has_permission(user: User, code: str) -> bool:
    """Synchronous role-only check.

    Не учитывает group_permission_grant. Используется в местах, где требуется
    быстрая проверка без обращения к БД (например, _require_admin внутри RBAC
    админ-роутов, где у юзера уже загружены роли). Для боевых endpoint'ов
    используйте `require_permission` (Depends).
    """
    if is_super_admin(user):
        return True
    return code in _user_permission_codes(user)


async def has_effective_permission(
    db: AsyncSession,
    user: User,
    code: str,
) -> bool:
    """Полная проверка с учётом всех источников прав (Pack 147):

      1. owner или role `admin` (глобальная User.roles) → True (bypass).
      2. Если у юзера через UserGroupRole — какая-то role даёт этот code → True.
      3. Если у юзера через GroupPermissionGrant стоит `deny` на этот code → False.
      4. Если через GroupPermissionGrant — `grant` (не истёкший) → True.
      5. Если в собственных user.roles permissions есть code → True.
      6. Иначе False.

    NB: shortcut на admin/owner отрабатывает ДО любых deny — это by-design,
    чтобы поломанная группа не закрыла доступ системному админу.
    """
    if is_super_admin(user):
        return True

    # Импорт внутри функции, чтобы избежать циклов при импорте.
    from app.models.rbac_v3 import GroupPermissionGrant
    from app.models.user import Group, Permission, Role, UserGroupRole
    from sqlalchemy import exists

    now = datetime.now(timezone.utc)

    # --- (2) Per-group roles (Pack 147): role permissions from user_group_role.
    ugr_perm_exists = await db.execute(
        select(Permission.id)
        .join(Role.permissions)
        .join(UserGroupRole, UserGroupRole.role_id == Role.id)
        .where(UserGroupRole.user_id == user.id, Permission.code == code)
        .limit(1)
    )
    if ugr_perm_exists.first() is not None:
        return True

    # --- (3) (4) Group permission grants (overrides + denies).
    grants_q = await db.execute(
        select(GroupPermissionGrant.grant_type, GroupPermissionGrant.expires_at)
        .join(Group, Group.id == GroupPermissionGrant.group_id)
        .join(Group.users)
        .where(
            User.id == user.id,
            GroupPermissionGrant.permission_code == code,
        )
    )
    grants = list(grants_q.all())

    has_group_grant = False
    for grant_type, expires_at in grants:
        if expires_at is not None and expires_at < now:
            continue
        if grant_type == "deny":
            return False
        if grant_type == "grant":
            has_group_grant = True

    if code in _user_permission_codes(user):
        return True
    return has_group_grant


def require_permission(code: str):
    """Dependency factory: ensure the current user has the named permission.

    Учитывает:
      * `is_owner=True` и роль `admin` → bypass;
      * permissions через роли;
      * group_permission_grant (grant) с уважением expires_at;
      * group_permission_grant (deny) — отзывает право, даже если оно есть в роли.

    Pack 12.0: для API-key вдобавок проверяется, что код входит в `scopes` ключа.
    """

    async def _dep(
        request: Request,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if not await has_effective_permission(db, user, code):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Permission required: {code}",
            )
        # API key scope restriction (Pack 12.0)
        api_key = getattr(request.state, "api_key", None)
        if api_key is not None:
            from app.services.api_key_service import check_scope
            if not check_scope(api_key, code):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    f"API key scope missing: {code}",
                )
        return user

    return _dep


def require_any_permission(*codes: str):
    """Dependency factory: at least one of the codes must be present."""
    code_list = list(codes)

    async def _dep(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        for c in code_list:
            if await has_effective_permission(db, user, c):
                return user
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"At least one permission required: {', '.join(code_list)}",
        )

    return _dep


# =====================================================================
# Role helpers
# =====================================================================

def require_role(*role_codes: str):
    """Dependency factory: require user to have at least one of the given roles.

    `is_owner=True` and role `admin` bypass the check."""
    role_list = list(role_codes)

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if is_super_admin(user):
            return user
        user_roles = _user_role_codes(user)
        if not any(r in user_roles for r in role_list):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role required: one of [{', '.join(role_list)}]",
            )
        return user
    return _dep


def require_owner():
    """Dependency: only the platform owner may proceed."""
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if not user.is_owner:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Owner-only operation",
            )
        return user
    return _dep


# =====================================================================
# Optional: get user but allow anonymous (returns None instead of 401)
# =====================================================================

async def get_optional_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if creds is None:
        return None
    try:
        return await get_current_user(request, creds, db)
    except HTTPException:
        return None


# =====================================================================
# Internal
# =====================================================================

def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer realm="uzassets"'},
    )
