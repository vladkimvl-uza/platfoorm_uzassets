"""Authentication service: login, refresh, logout, password change.

All auth events go to `audit_log` via the HMAC chain — login success/failure,
lockout, password change, refresh, logout."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core import jwt as app_jwt
from app.core import password as pw
from app.core.audit_chain import append_audit_entry
from app.models.user import Role, RoleByEmail, User, UserSession, user_role

log = logging.getLogger(__name__)


# =====================================================================
# Login
# =====================================================================

async def authenticate(
    db: AsyncSession,
    *,
    login_id: str,
    password: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[User, str, str]:
    """Verify credentials, enforce lockout, issue access + refresh tokens.

    Returns: (user, access_token, refresh_token)
    Raises: HTTPException 401 / 423 / 403 with appropriate reasons.

    Note: timing — we always do a bcrypt verify even when the user doesn't
    exist, against a synthetic hash, so 'user not found' and 'wrong password'
    take roughly the same time. Defends against username enumeration.
    """
    # --- Look up user (case-insensitive on email and username) ---
    needle = login_id.strip().lower()
    result = await db.execute(
        select(User)
        .where(or_(
            User.email.ilike(needle),
            User.username.ilike(needle),
        ))
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
        )
    )
    user: Optional[User] = result.scalar_one_or_none()

    # Synthetic hash for timing-equalization on missing user
    SYNTHETIC = "$2b$12$" + "S" * 53

    if user is None:
        # Run a verify against a synthetic hash to keep timing constant
        pw.verify_password(password, SYNTHETIC)
        await _audit(db,
            actor_email=login_id,
            action="login.failed",
            notes="user_not_found",
            ip=ip, user_agent=user_agent,
        )
        await db.commit()
        raise _unauthorized("Неверный логин или пароль")

    # --- Lockout check ---
    if user.locked_until is not None and user.locked_until > _now():
        remaining = int((user.locked_until - _now()).total_seconds() / 60) + 1
        await _audit(db,
            actor_id=str(user.id), actor_email=user.email,
            action="login.blocked_locked",
            notes=f"locked_until={user.locked_until.isoformat()}",
            ip=ip, user_agent=user_agent,
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Аккаунт заблокирован. Попробуйте снова через {remaining} мин.",
        )

    # --- Inactive check ---
    if not user.is_active:
        await _audit(db,
            actor_id=str(user.id), actor_email=user.email,
            action="login.blocked_inactive",
            ip=ip, user_agent=user_agent,
        )
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт отключён")

    # --- Password check ---
    if not pw.verify_password(password, user.password_hash or SYNTHETIC):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

        if user.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            user.locked_until = _now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            await _audit(db,
                actor_id=str(user.id), actor_email=user.email,
                action="account.locked",
                notes=f"after_{user.failed_login_attempts}_failed_attempts",
                ip=ip, user_agent=user_agent,
            )
        else:
            await _audit(db,
                actor_id=str(user.id), actor_email=user.email,
                action="login.failed",
                notes=f"wrong_password,attempt={user.failed_login_attempts}/{settings.LOGIN_MAX_FAILED_ATTEMPTS}",
                ip=ip, user_agent=user_agent,
            )
        await db.commit()
        raise _unauthorized("Неверный логин или пароль")

    # --- Successful login: reset counters, issue tokens ---
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = _now()
    user.last_login_ip = ip

    # If hash needs rehashing (stronger cost factor configured), upgrade silently
    if pw.needs_rehash(user.password_hash):
        user.password_hash = pw.hash_password(password)
        user.password_changed_at = _now()

    # Auto-apply role_by_email rule (фикс H2). Идемпотентно: добавляем
    # отсутствующие роли, заполняем пустые поля scope. Уже выставленные
    # admin'ом вручную значения НЕ перезаписываем.
    try:
        await _apply_role_by_email(db, user)
    except Exception as e:  # noqa: BLE001
        log.warning("auto-apply role_by_email failed for %s: %s", user.email, e)

    access  = app_jwt.create_access_token(
        subject=str(user.id),
        extra_claims={
            "email": user.email,
            "is_owner": user.is_owner,
            "roles": [r.code for r in user.roles],
        },
    )
    refresh, jti = app_jwt.create_refresh_token(subject=str(user.id))

    # Persist refresh token hash so it can be revoked
    db.add(UserSession(
        user_id=user.id,
        refresh_token_hash=app_jwt.hash_jti(jti),
        expires_at=_now() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        ip_address=ip,
        user_agent=user_agent,
    ))

    await _audit(db,
        actor_id=str(user.id), actor_email=user.email,
        action="login.success",
        ip=ip, user_agent=user_agent,
    )
    await db.commit()
    return user, access, refresh


# =====================================================================
# Refresh
# =====================================================================

async def refresh_tokens(
    db: AsyncSession,
    *,
    refresh_token: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[User, str, str]:
    """Verify a refresh token, ROTATE it (revoke old, issue new), return both."""
    from jwt import InvalidTokenError
    try:
        claims = app_jwt.decode_token(refresh_token, expected_type="refresh")
    except InvalidTokenError as e:
        raise _unauthorized(f"Invalid refresh token: {type(e).__name__}")

    user_id = claims.get("sub")
    jti     = claims.get("jti")
    if not user_id or not jti:
        raise _unauthorized("Refresh token missing claims")

    token_hash = app_jwt.hash_jti(jti)

    # Look up the session record
    result = await db.execute(
        select(UserSession).where(UserSession.refresh_token_hash == token_hash)
    )
    session: Optional[UserSession] = result.scalar_one_or_none()
    if session is None:
        # Theft scenario: token was previously revoked but is being reused
        await _audit(db,
            actor_id=user_id, action="refresh.unknown_jti",
            notes="possible_token_replay",
            ip=ip, user_agent=user_agent,
        )
        await db.commit()
        raise _unauthorized("Refresh token unknown or revoked")

    if session.revoked_at is not None:
        # Replay attempt — revoke ALL of this user's sessions as defense in depth
        result = await db.execute(
            select(UserSession).where(
                UserSession.user_id == session.user_id,
                UserSession.revoked_at.is_(None),
            )
        )
        for s in result.scalars().all():
            s.revoked_at = _now()
        await _audit(db,
            actor_id=str(session.user_id),
            action="refresh.replay_detected",
            notes="all_user_sessions_revoked",
            ip=ip, user_agent=user_agent,
        )
        await db.commit()
        raise _unauthorized("Refresh token replay detected — all sessions revoked")

    if session.expires_at < _now():
        raise _unauthorized("Refresh token expired")

    # Load the user
    result = await db.execute(
        select(User)
        .where(User.id == session.user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user: Optional[User] = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _unauthorized("User not found or inactive")

    # ROTATE: revoke old refresh, issue new pair
    session.revoked_at = _now()

    new_access  = app_jwt.create_access_token(
        subject=str(user.id),
        extra_claims={
            "email": user.email,
            "is_owner": user.is_owner,
            "roles": [r.code for r in user.roles],
        },
    )
    new_refresh, new_jti = app_jwt.create_refresh_token(subject=str(user.id))

    db.add(UserSession(
        user_id=user.id,
        refresh_token_hash=app_jwt.hash_jti(new_jti),
        expires_at=_now() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        ip_address=ip,
        user_agent=user_agent,
    ))

    await _audit(db,
        actor_id=str(user.id), actor_email=user.email,
        action="refresh.success",
        ip=ip, user_agent=user_agent,
    )
    await db.commit()
    return user, new_access, new_refresh


# =====================================================================
# Logout
# =====================================================================

async def logout(
    db: AsyncSession,
    *,
    user: User,
    refresh_token: Optional[str],
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Revoke the supplied refresh token (if any). Always succeeds."""
    if refresh_token:
        try:
            from jwt import InvalidTokenError
            try:
                claims = app_jwt.decode_token(refresh_token, expected_type="refresh")
                jti = claims.get("jti")
                if jti:
                    h = app_jwt.hash_jti(jti)
                    result = await db.execute(
                        select(UserSession).where(UserSession.refresh_token_hash == h)
                    )
                    s = result.scalar_one_or_none()
                    if s and s.revoked_at is None:
                        s.revoked_at = _now()
            except InvalidTokenError:
                pass
        except Exception as e:
            log.warning("logout: failed to revoke refresh: %s", e)

    await _audit(db,
        actor_id=str(user.id), actor_email=user.email,
        action="logout",
        ip=ip, user_agent=user_agent,
    )
    await db.commit()


# =====================================================================
# Change password
# =====================================================================

async def change_password(
    db: AsyncSession,
    *,
    user: User,
    current: str,
    new: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Validate, hash, store new password. Enforces history + policy."""
    if not pw.verify_password(current, user.password_hash or ""):
        await _audit(db,
            actor_id=str(user.id), actor_email=user.email,
            action="password.change_failed",
            notes="wrong_current_password",
            ip=ip, user_agent=user_agent,
        )
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущий пароль неверный")

    try:
        pw.validate_password_policy(new)
        pw.check_password_history(new, user.password_history)
    except pw.PasswordPolicyError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message)

    new_hash = pw.hash_password(new)
    user.password_history = pw.push_to_history(user.password_hash, user.password_history) if user.password_hash else []
    user.password_hash = new_hash
    user.password_changed_at = _now()
    user.must_change_password = False

    # Revoke all existing sessions — force re-login everywhere
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
    )
    for s in result.scalars().all():
        s.revoked_at = _now()

    await _audit(db,
        actor_id=str(user.id), actor_email=user.email,
        action="password.changed",
        notes="all_sessions_revoked",
        ip=ip, user_agent=user_agent,
    )
    await db.commit()


# =====================================================================
# RoleByEmail auto-apply (Pack 145 / H2)
# =====================================================================

async def _apply_role_by_email(db: AsyncSession, user: User) -> None:
    """Apply a matching RoleByEmail rule to a freshly-authenticated user.

    Идемпотентно:
      * roles — добавляем только те, которых ещё нет у юзера. Уже
        выставленные admin'ом роли не трогаем.
      * department — заполняем только если у юзера пусто.
      * allowed_sectors / allowed_companies — заполняем только если
        соответствующее поле NULL/empty.

    Не падает на отсутствующих ролях в правиле — просто пропускает
    неизвестные коды (admin мог удалить роль, оставив правило).
    """
    rule = (await db.execute(
        select(RoleByEmail).where(RoleByEmail.email.ilike(user.email))
    )).scalar_one_or_none()
    if rule is None:
        return

    changed = False
    to_add: list[str] = []

    # Roles — add-only diff
    desired_codes = [c for c in (rule.role_codes or []) if c]
    if desired_codes:
        existing_codes = {r.code for r in user.roles}
        to_add = [c for c in desired_codes if c not in existing_codes]
        if to_add:
            roles_q = await db.execute(select(Role).where(Role.code.in_(to_add)))
            for r in roles_q.scalars().all():
                # Append to relationship — SQLAlchemy issues a single INSERT
                # into user_role at flush. Doing both relationship.append AND
                # explicit `user_role.insert()` causes a duplicate-PK error.
                user.roles.append(r)
                changed = True

    # department — fill if empty
    if rule.department and not (user.department and user.department.strip()):
        user.department = rule.department
        changed = True

    # scope arrays — fill if empty
    if rule.allowed_sectors and not user.allowed_sectors:
        user.allowed_sectors = list(rule.allowed_sectors)
        changed = True
    if rule.allowed_companies and not user.allowed_companies:
        user.allowed_companies = list(rule.allowed_companies)
        changed = True

    if changed:
        await _audit(db,
            actor_id=str(user.id), actor_email=user.email,
            action="rbac.rbe.auto_applied",
            notes=f"rule_id={rule.id}, roles_added={to_add}",
        )


# =====================================================================
# Session revocation (shared helper — used by admin actions in rbac_v3)
# =====================================================================

async def revoke_all_sessions(db: AsyncSession, user_id) -> int:
    """Revoke all active refresh tokens for a user.

    Возвращает количество ревокированных сессий (для аудит-логов).
    Caller отвечает за commit.

    Используется при:
      * deactivate_user
      * permanently_delete_user
      * смене ролей через update_user (старые JWT иначе живут до expiry с
        устаревшими ролями в claims)
      * admin reset_password (как в self-service change_password)
    """
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )
    sessions = list(result.scalars().all())
    now = _now()
    for s in sessions:
        s.revoked_at = now
    return len(sessions)


# =====================================================================
# Helpers
# =====================================================================

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer realm="uzassets"'},
    )


async def _audit(
    db: AsyncSession,
    *,
    action: str,
    actor_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    notes: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Append an HMAC-chained entry to the audit log."""
    try:
        await append_audit_entry(
            db,
            actor_id=actor_id,
            actor_email=actor_email,
            action=action,
            entity_type="auth",
            notes=notes,
            ip_address=ip,
            user_agent=user_agent,
        )
    except Exception as e:
        # Never let audit failure break the auth flow — log it loudly instead
        log.error("AUDIT FAILED for action=%s: %s", action, e, exc_info=True)
