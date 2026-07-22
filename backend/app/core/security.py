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

from datetime import UTC, datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

    # ─── API key path ───────────────────────────────
    if token.startswith(("uza_pk_live_", "uza_pk_test_")):
        from app.core.rate_limit import _real_client_ip
        from app.services.api_key_service import ApiKeyAuthError, record_call, verify_token
        # Use trusted-proxy-aware resolver: when nginx forwards a request,
        # request.client.host is nginx's IP, NOT the actual client. The
        # IP allowlist must check the real client IP via X-Forwarded-For
        # (validated against the trusted proxy CIDR list).
        client_ip = _real_client_ip(request) or None
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

    # 2026-05-26: JWT revocation — reject tokens issued before user's cutoff.
    # Bumped on logout / change_password / MFA force-disable / role change /
    # deactivate. Single per-user comparison vs blacklist-per-jti — no extra
    # query because user is already loaded.
    if user.tokens_invalid_before:
        iat = claims.get("iat")
        if iat is not None:
            from datetime import datetime
            iat_dt = datetime.fromtimestamp(int(iat), tz=UTC)
            if iat_dt < user.tokens_invalid_before:
                raise _unauthorized("Token revoked")

    # ─── Force password change enforcement ─────────────────────────
    # Either explicit flag set by admin (or self via reset) OR computed from
    # password_changed_at + PASSWORD_MAX_AGE_DAYS (90d default).
    # Always allow self-service password change + introspection + logout.
    _ALLOWED_PATHS = (
        "/auth/change-password",
        "/auth/logout",
        "/auth/me",
        "/auth/refresh",
        "/mfa/",
    )
    path = request.url.path
    needs_change = bool(user.must_change_password)
    if not needs_change and user.password_changed_at:
        from app.config import settings as _s
        max_age_days = getattr(_s, "PASSWORD_MAX_AGE_DAYS", 90)
        if max_age_days > 0:
            from datetime import datetime, timedelta
            cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
            if user.password_changed_at < cutoff:
                needs_change = True
                # Persist the requirement so client sees it on next /auth/me
                if not user.must_change_password:
                    user.must_change_password = True
                    try: await db.commit()
                    except Exception: await db.rollback()
    if needs_change and not any(path.startswith(p) for p in _ALLOWED_PATHS):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "password_change_required",
                "message": "Требуется смена пароля. Воспользуйтесь /auth/change-password.",
            },
            headers={"WWW-Authenticate": 'Bearer error="password_change_required"'},
        )

    # Stash on request.state for rate-limiter and audit middleware
    request.state.user = user
    return user


# =====================================================================
# Permission helpers
# =====================================================================

def _user_permission_codes(user: User) -> set[str]:
    """Flatten all permission codes the user has via their roles."""
    perms: set[str] = set()
    for role in user.roles:
        perms.update(p.code for p in role.permissions)
    return perms


def _user_role_codes(user: User) -> set[str]:
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
    """Полная проверка с учётом всех источников прав (Pack 147).

    Порядок (deny из группы перебивает любой grant, кроме super-admin):
      1. owner или role `admin` (глобальная User.roles) → True (bypass).
      2. Если у юзера через GroupPermissionGrant стоит активный `deny`
         на этот code → False.
      3. Иначе True, если есть хотя бы один grant из любого источника:
           * permission в роли из user_group_role (Pack 147),
           * permission в собственных user.roles,
           * GroupPermissionGrant.grant_type='grant' (не истёкший).
      4. Иначе False.
    """
    if is_super_admin(user):
        return True

    from app.models.rbac_v3 import GroupPermissionGrant, UserPermissionGrant
    from app.models.user import Permission, Role, UserGroupRole

    now = datetime.now(UTC)

    # --- (1.5) Прямые per-user гранты (overlay сетки «Доступ к модулям»).
    # deny на user-уровне перебивает любой grant роли/группы; grant — даёт право.
    has_user_grant = False
    try:
        ug_q = await db.execute(
            select(UserPermissionGrant.grant_type, UserPermissionGrant.expires_at)
            .where(
                UserPermissionGrant.user_id == user.id,
                UserPermissionGrant.permission_code == code,
            )
        )
        for grant_type, expires_at in ug_q.all():
            if expires_at is not None and expires_at < now:
                continue
            if grant_type == "deny":
                return False  # user-level deny overrides everything below
            if grant_type == "grant":
                has_user_grant = True
    except Exception:
        # таблица может ещё не существовать до self-heal — деградируем безопасно
        has_user_grant = False

    # --- (2)(3) Group permission grants — чтобы deny отработал ДО grant-источников.
    grants_q = await db.execute(
        select(GroupPermissionGrant.grant_type, GroupPermissionGrant.expires_at)
        .join(UserGroupRole, UserGroupRole.group_id == GroupPermissionGrant.group_id)
        .where(
            UserGroupRole.user_id == user.id,
            GroupPermissionGrant.permission_code == code,
        )
    )
    grants = list(grants_q.all())

    has_group_grant = False
    for grant_type, expires_at in grants:
        if expires_at is not None and expires_at < now:
            continue
        if grant_type == "deny":
            return False  # deny overrides any grant below
        if grant_type == "grant":
            has_group_grant = True

    if has_user_grant or has_group_grant:
        return True

    # --- (3a) Per-group roles role permissions via user_group_role.
    ugr_perm_exists = await db.execute(
        select(Permission.id)
        .join(Role.permissions)
        .join(UserGroupRole, UserGroupRole.role_id == Role.id)
        .where(UserGroupRole.user_id == user.id, Permission.code == code)
        .limit(1)
    )
    if ugr_perm_exists.first() is not None:
        return True

    # --- (3b) Global User.roles permissions.
    if code in _user_permission_codes(user):
        return True
    return False


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
        # API key scope restriction
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


def require_recent_auth(max_minutes: int = 10):
    """Step-up (841 п.5.2.4): требует «сильную» аутентификацию (пароль/MFA/re-auth)
    не старше max_minutes. Иначе 403 detail='step_up_required' — фронт показывает
    повторную аутентификацию и ретраит запрос."""
    from datetime import UTC, datetime, timedelta

    async def _dep(user: User = Depends(get_current_user)) -> User:
        sa = getattr(user, "last_strong_auth_at", None)
        if sa is None or (datetime.now(UTC) - sa) > timedelta(minutes=max_minutes):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="step_up_required",
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
