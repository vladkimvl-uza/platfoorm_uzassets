"""Authentication service: login, refresh, logout, password change.

All auth events go to `audit_log` via the HMAC chain — login success/failure,
lockout, password change, refresh, logout."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core import jwt as app_jwt
from app.core import password as pw
from app.core.audit_chain import append_audit_entry
from app.models.user import Role, RoleByEmail, User, UserSession

log = logging.getLogger(__name__)


# Cap concurrent active sessions per user. Prevents a compromised account
# from spawning unlimited parallel refresh tokens, and bounds the blast
# radius of "revoke all sessions" administrative action.
MAX_CONCURRENT_SESSIONS = 5


def _session_origin(s: UserSession) -> datetime:
    """Начало «цепочки» сессии (для абсолютного таймаута). Фолбэк — created_at."""
    return getattr(s, "session_started_at", None) or s.created_at


def _idle_window() -> timedelta:
    """Окно бездействия. Не меньше времени жизни access-токена + 5 мин — иначе
    активные пользователи (фронт обновляет токен реактивно по 401) разлогинивались
    бы в момент ротации."""
    minutes = max(settings.SESSION_IDLE_TIMEOUT_MINUTES, settings.JWT_EXPIRE_MINUTES + 5)
    return timedelta(minutes=minutes)


def _device_label(ua: Optional[str]) -> str:
    """Короткая метка устройства из user-agent (для уведомлений)."""
    if not ua:
        return "неизвестное устройство"
    os = ("Windows" if "Windows" in ua else "macOS" if ("Mac OS X" in ua or "Macintosh" in ua)
          else "Android" if "Android" in ua else "iOS" if ("iPhone" in ua or "iPad" in ua)
          else "Linux" if "Linux" in ua else "—")
    br = ("Edge" if "Edg/" in ua else "Opera" if ("OPR/" in ua or "Opera" in ua)
          else "Chrome" if "Chrome/" in ua else "Firefox" if "Firefox/" in ua
          else "Safari" if "Safari/" in ua else "браузер")
    return f"{br} · {os}"


async def _known_login_ips(db: AsyncSession, user_id) -> set[str]:
    res = await db.execute(
        select(UserSession.ip_address).where(UserSession.user_id == user_id).distinct()
    )
    return {r for (r,) in res.all() if r}


async def send_security_alert(db: AsyncSession, user_id, *, title: str, body: str) -> None:
    """Best-effort security-уведомление (in-app + Telegram/email). Без секретов
    в теле (841 п.5.1.2.2). Сбой доставки не ломает основной флоу."""
    try:
        from app.services import notifications_service
        await notifications_service.notify(
            db, recipient_id=user_id, type="security.alert",
            title=title, body=body, priority="high", source_module="security",
        )
    except Exception:
        log.warning("security alert notify failed", exc_info=True)


async def _prune_concurrent_sessions(db: AsyncSession, user_id) -> int:
    """Revoke oldest active sessions for user so the next-added session
    keeps total active <= MAX_CONCURRENT_SESSIONS. Returns count revoked.
    """
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == user_id,
               UserSession.revoked_at.is_(None))
        .order_by(UserSession.created_at.desc())
    )
    sessions = list(result.scalars().all())
    # We're about to add 1 more session → keep at most (MAX-1) of existing.
    keep = MAX_CONCURRENT_SESSIONS - 1
    if len(sessions) <= keep:
        return 0
    now = datetime.now(UTC)
    revoked = 0
    for s in sessions[keep:]:
        s.revoked_at = now
        revoked += 1
    return revoked


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
        try:
            from app.core.observability import incr as _incr
            _incr("auth_login_total", outcome="user_not_found")
        except Exception:
            pass
        raise _unauthorized("Неверный логин или пароль")

    # --- Lockout check ---
    if user.locked_until is not None and user.locked_until > _now():
        # 2026-05-26: timing-equalize — без bcrypt этот ответ ~10× быстрее
        # «wrong password», что палит факт существования аккаунта.
        pw.verify_password(password, SYNTHETIC)
        remaining = int((user.locked_until - _now()).total_seconds() / 60) + 1
        await _audit(db,
            actor_id=str(user.id), actor_email=user.email,
            action="login.blocked_locked",
            notes=f"locked_until={user.locked_until.isoformat()}",
            ip=ip, user_agent=user_agent,
        )
        await db.commit()
        try:
            from app.core.observability import incr as _incr
            _incr("auth_login_total", outcome="locked")
        except Exception:
            pass
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Аккаунт заблокирован. Попробуйте снова через {remaining} мин.",
        )

    # --- Inactive check ---
    if not user.is_active:
        # Same timing-equalize as locked branch above.
        pw.verify_password(password, SYNTHETIC)
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
        try:
            from app.core.observability import incr as _incr
            _incr("auth_login_total", outcome="failed")
        except Exception:
            pass
        raise _unauthorized("Неверный логин или пароль")

    # --- Successful login: reset counters, issue tokens ---
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = _now()
    user.last_strong_auth_at = _now()  # step-up: пароль = сильная аутентификация
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
    except Exception as e:
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

    # Cap concurrent active sessions before adding the new one.
    pruned = await _prune_concurrent_sessions(db, user.id)
    if pruned:
        await _audit(db,
            actor_id=str(user.id), actor_email=user.email,
            action="session.pruned_oldest",
            notes=f"revoked={pruned} (cap={MAX_CONCURRENT_SESSIONS})",
            ip=ip, user_agent=user_agent,
        )

    # Новый IP? (сравниваем с историей ДО добавления текущей сессии). Уведомляем
    # только если уже есть история входов (на первом входе — не шумим).
    _known_ips = await _known_login_ips(db, user.id)
    _new_ip = bool(_known_ips) and ip is not None and ip not in _known_ips

    # Persist refresh token hash so it can be revoked
    db.add(UserSession(
        user_id=user.id,
        refresh_token_hash=app_jwt.hash_jti(jti),
        expires_at=_now() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        session_started_at=_now(),
        ip_address=ip,
        user_agent=user_agent,
    ))

    await _audit(db,
        actor_id=str(user.id), actor_email=user.email,
        action="login.success",
        ip=ip, user_agent=user_agent,
    )
    await db.commit()
    try:
        from app.core.observability import incr as _incr
        _incr("auth_login_total", outcome="success")
    except Exception:
        pass

    # Уведомление о входе с нового IP (841 п.5.1.2.2 — без секретов в теле).
    if _new_ip:
        await send_security_alert(
            db, user.id,
            title="Новый вход в аккаунт",
            body=f"Выполнен вход с нового IP-адреса {ip} · {_device_label(user_agent)}. "
                 f"Если это были не вы — смените пароль и обратитесь к администратору.",
        )

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

    # Idle / absolute session timeouts (O'zMSt 149; 841 5.2). created_at = время
    # последней ротации (idle), session_started_at = старт цепочки (absolute).
    now = _now()
    origin = _session_origin(session)
    if now - origin > timedelta(hours=settings.SESSION_ABSOLUTE_TIMEOUT_HOURS):
        session.revoked_at = now
        await _audit(db, actor_id=str(session.user_id),
                     action="session.absolute_timeout", ip=ip, user_agent=user_agent)
        await db.commit()
        raise _unauthorized("Session expired (absolute timeout)")
    if now - session.created_at > _idle_window():
        session.revoked_at = now
        await _audit(db, actor_id=str(session.user_id),
                     action="session.idle_timeout", ip=ip, user_agent=user_agent)
        await db.commit()
        raise _unauthorized("Session expired (idle timeout)")

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
        session_started_at=origin,  # absolute-таймаут считается от старта цепочки
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
    """Revoke the supplied refresh token AND invalidate user's access tokens.

    2026-05-26: logout теперь убивает и access tokens через
    bump_tokens_invalid_before — иначе они жили до expiry (30 мин).
    """
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

    # Invalidate access tokens — covers other devices/sessions of same user.
    # Tradeoff: log out from device A also logs out devices B, C. Acceptable
    # for security; standard practice (Google, Apple, etc. do the same on
    # explicit logout). Per-device logout would require jti blacklist.
    await bump_tokens_invalid_before(db, user.id)

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

    # Read password history from encrypted column first; fall back to legacy
    # plaintext-JSONB column for users not yet lazy-migrated.
    from app.core.encryption import encrypt_json_list, try_decrypt_json_list
    effective_history = try_decrypt_json_list(user.password_history_enc) \
        if user.password_history_enc else None
    if effective_history is None:
        effective_history = user.password_history

    try:
        pw.validate_password_policy(new)
        pw.check_password_history(new, effective_history)
    except pw.PasswordPolicyError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message)

    new_hash = pw.hash_password(new)
    new_history = pw.push_to_history(user.password_hash, effective_history) \
        if user.password_hash else []
    # Always write encrypted form; clear legacy column so it stops being
    # read-fallback after this point (auto-migration on next password change).
    try:
        user.password_history_enc = encrypt_json_list(new_history)
        user.password_history = None
    except Exception as e:
        # Encryption not configured — log and fall back to legacy so we don't
        # accidentally clear the history.
        log.error("password_history Fernet encrypt failed: %s", e)
        user.password_history = new_history
    user.password_hash = new_hash
    user.password_changed_at = _now()
    user.must_change_password = False

    # Revoke all existing sessions + invalidate access tokens — force
    # re-login everywhere. 2026-05-26: revoke_all_sessions теперь
    # автоматически вызывает bump_tokens_invalid_before, так что одна
    # функция убивает и refresh и access.
    await revoke_all_sessions(db, user.id)

    await _audit(db,
        actor_id=str(user.id), actor_email=user.email,
        action="password.changed",
        notes="all_sessions_revoked",
        ip=ip, user_agent=user_agent,
    )
    await db.commit()
    try:
        from app.core.observability import incr as _incr
        _incr("auth_password_change_total", source="self")
    except Exception:
        pass


# =====================================================================
# RoleByEmail auto-apply / H2)
# =====================================================================

async def _apply_role_by_email(db: AsyncSession, user: User) -> None:
    """Apply a matching RoleByEmail rule to a freshly-authenticated user.

    Идемпотентно:
      * roles — добавляем только те глобальные роли, которых ещё нет у
        юзера (через User.roles). Уже выставленные admin'ом — не трогаем.
      * department — заполняем только если у юзера пусто.
      * allowed_sectors — заполняем только если у юзера пусто.
      * allowed_companies (Pack 147) — каждый company-ref в правиле →
        находим Group(company_id) → добавляем UserGroupRole с дефолтной
        ролью `viewer`. Уже существующие членства не трогаем.

    Не падает на отсутствующих ролях/компаниях — просто пропускает
    неизвестные коды.
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

    # Companies → group memberships
    if rule.allowed_companies:
        from sqlalchemy import select as _select

        from app.models.company import Company
        from app.models.user import Group, UserGroupRole

        viewer_id = (await db.execute(
            _select(Role.id).where(Role.code == "viewer")
        )).scalar_one_or_none()

        if viewer_id is not None:
            # Resolve each ref (UUID-string or company.code) into Company.id
            refs = [str(r).strip() for r in rule.allowed_companies if r]
            co_q = await db.execute(
                _select(Company.id).where(
                    (Company.id.cast(sa.String).in_(refs))
                    | (sa.func.lower(Company.code).in_([r.lower() for r in refs]))
                )
            )
            company_ids = list(co_q.scalars().all())
            if company_ids:
                # Find groups bound to these companies
                grp_q = await db.execute(
                    _select(Group.id, Group.company_id)
                    .where(Group.company_id.in_(company_ids))
                )
                groups = list(grp_q.all())
                # Existing memberships to skip
                existing_q = await db.execute(
                    _select(UserGroupRole.group_id)
                    .where(UserGroupRole.user_id == user.id)
                )
                existing_groups = {row for row in existing_q.scalars().all()}

                for grp_id, _co_id in groups:
                    if grp_id in existing_groups:
                        continue
                    db.add(UserGroupRole(
                        user_id=user.id, group_id=grp_id, role_id=viewer_id,
                    ))
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

async def bump_tokens_invalid_before(db: AsyncSession, user_id) -> None:
    """Mark all JWT access tokens issued <= now as revoked for this user.

    2026-05-26: complements revoke_all_sessions() (which only kills refresh
    tokens). Access tokens stay valid for up to 30 min after refresh-revoke
    without this — read by get_current_user().tokens_invalid_before check.

    Caller is responsible for commit.
    """
    from app.models.user import User as _User
    await db.execute(
        sa.update(_User)
        .where(_User.id == user_id)
        .values(tokens_invalid_before=_now())
    )


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

    2026-05-26: автоматически вызывает bump_tokens_invalid_before чтобы
    access-tokens (а не только refresh) тоже инвалидировались.
    """
    await bump_tokens_invalid_before(db, user_id)
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
# Active sessions (self-service): list / revoke one / revoke others
# 841 п.5.2.2.3 — пользователь видит и завершает свои активные сессии.
# =====================================================================

async def _active_sessions(db: AsyncSession, user_id) -> list[UserSession]:
    res = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > _now(),
        )
        .order_by(UserSession.created_at.desc())
    )
    return list(res.scalars().all())


def _pick_current(sessions: list[UserSession], ip: Optional[str], ua: Optional[str]):
    """Best-effort «текущая» сессия: самая свежая с совпадающими IP+UA, иначе
    просто самая свежая (sessions уже отсортированы desc)."""
    for s in sessions:
        if s.ip_address == ip and s.user_agent == ua:
            return s
    return sessions[0] if sessions else None


async def list_active_sessions(
    db: AsyncSession, user_id, *, ip: Optional[str] = None, ua: Optional[str] = None,
) -> list[dict]:
    sessions = await _active_sessions(db, user_id)
    current = _pick_current(sessions, ip, ua)
    cur_id = current.id if current else None
    return [{
        "id": str(s.id),
        "ip_address": s.ip_address,
        "user_agent": s.user_agent,
        "created_at": s.created_at,
        "started_at": _session_origin(s),
        "current": s.id == cur_id,
    } for s in sessions]


async def revoke_session(db: AsyncSession, user_id, session_id) -> bool:
    res = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )
    s = res.scalar_one_or_none()
    if s is None:
        return False
    s.revoked_at = _now()
    await _audit(db, actor_id=str(user_id), action="session.revoked_self",
                 notes=f"session={session_id}")
    await db.commit()
    return True


async def revoke_other_sessions(
    db: AsyncSession, user_id, *, ip: Optional[str] = None, ua: Optional[str] = None,
) -> int:
    sessions = await _active_sessions(db, user_id)
    current = _pick_current(sessions, ip, ua)
    cur_id = current.id if current else None
    now = _now()
    n = 0
    for s in sessions:
        if s.id != cur_id:
            s.revoked_at = now
            n += 1
    if n:
        await _audit(db, actor_id=str(user_id), action="session.revoked_others",
                     notes=f"count={n}")
    await db.commit()
    return n


# =====================================================================
# Helpers
# =====================================================================

def _now() -> datetime:
    return datetime.now(tz=UTC)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer realm="uzassets"'},
    )


_CRITICAL_AUTH_ACTIONS = {
    "password.changed",
    "refresh.replay_detected",
    "refresh.unknown_jti",
    "login.locked",
    "session.pruned_oldest",
}


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
            is_critical=action in _CRITICAL_AUTH_ACTIONS,
        )
    except Exception as e:
        # Never let audit failure break the auth flow — log it loudly instead
        log.error("AUDIT FAILED for action=%s: %s", action, e, exc_info=True)
