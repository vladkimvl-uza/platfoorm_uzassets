"""Telegram Web App (Mini App) authentication (Phase C).

Spec:  https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Validation rules:
  1. initData is a URL-encoded string of the form `key=value&key=value&...`.
  2. Extract the `hash` parameter (the rest become the "data check string").
  3. Sort remaining keys alphabetically; join as `\n`-separated `key=value` lines.
  4. secret_key = HMAC-SHA256("WebAppData", bot_token)
  5. expected_hash = HMAC-SHA256(secret_key, data_check_string) — hex
  6. Compare in constant time with the `hash` we extracted.
  7. Check `auth_date` is within reasonable freshness window (24h default).

If valid, parse `user` JSON, lookup local User by encrypted telegram_chat_id,
and issue the standard JWT pair via the same path login uses.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core import jwt as app_jwt
from app.core.audit_chain import append_audit_entry
from app.core.encryption import decrypt
from app.models.user import Role, User, UserSession

log = logging.getLogger(__name__)

# initData is considered stale after this many seconds (Telegram recommends 24h)
INITDATA_MAX_AGE_SECONDS = int(os.getenv("TWA_INITDATA_MAX_AGE_SECONDS", "86400"))


def _bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "TELEGRAM_BOT_TOKEN is not configured on the backend",
        )
    return token


def verify_init_data(init_data: str) -> dict:
    """Verify Telegram initData signature and return the parsed payload.

    Raises HTTPException(401) on bad signature or expired data.
    Returns parsed dict (with `user` field unmarshaled as dict if present).
    """
    if not init_data or "hash=" not in init_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "initData is empty or missing hash")

    # Telegram's spec preserves original encoding when computing the hash, so
    # we use parse_qsl with keep_blank_values=True. Order matters only for
    # construction of the check string (we sort below).
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    data: dict[str, str] = dict(pairs)

    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "initData missing hash")

    # Build data check string: sorted alphabetically by key, joined with \n
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

    secret_key = hmac.new(b"WebAppData", _bot_token().encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "initData signature mismatch")

    # Freshness check
    auth_date_raw = data.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
            if int(time.time()) - auth_date > INITDATA_MAX_AGE_SECONDS:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "initData is stale")
        except (ValueError, TypeError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "initData has invalid auth_date")

    # Parse nested `user` JSON if present
    if "user" in data:
        try:
            data["user"] = json.loads(data["user"])
        except (ValueError, TypeError):
            data["user"] = {}

    return data


async def _find_user_by_tg_chat_id(db: AsyncSession, chat_id: int) -> Optional[User]:
    """Brute-decrypt scan — acceptable since we have <few hundred linked users."""
    result = await db.execute(
        select(User)
        .where(User.telegram_chat_id_encrypted.is_not(None))
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    for u in result.scalars().all():
        try:
            plain = decrypt(u.telegram_chat_id_encrypted)
            if plain and int(plain) == int(chat_id):
                return u
        except Exception:
            continue
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def authenticate_via_initdata(
    db: AsyncSession,
    *,
    init_data: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[User, str, str]:
    """Verify initData → resolve to local User → issue (access, refresh) tokens.

    Same persistence + audit pattern as auth_service.authenticate, minus the
    password and lockout logic (Telegram's signature IS the auth factor).
    """
    payload = verify_init_data(init_data)
    tg_user = payload.get("user") or {}
    tg_chat_id = tg_user.get("id")
    if not isinstance(tg_chat_id, int):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "initData has no user.id")

    user = await _find_user_by_tg_chat_id(db, tg_chat_id)
    if user is None:
        # Audit: TWA login from an unlinked Telegram account
        try:
            await append_audit_entry(
                db,
                action="twa.login.unlinked",
                notes=f"tg_chat_id={tg_chat_id} not linked to any user",
                ip_address=ip,
                user_agent=user_agent,
            )
            await db.commit()
        except Exception:
            await db.rollback()
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Telegram аккаунт не привязан к платформе. Откройте /settings/security в браузере.",
        )

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт отключён")

    # Issue token pair via the same JWT helpers used by /auth/login
    access = app_jwt.create_access_token(
        subject=str(user.id),
        extra_claims={
            "email": user.email,
            "is_owner": user.is_owner,
            "roles": [r.code for r in user.roles],
            "twa": True,  # marker — frontend can disable destructive actions
        },
    )
    refresh, jti = app_jwt.create_refresh_token(subject=str(user.id))

    from app.services.auth_service import _prune_concurrent_sessions
    await _prune_concurrent_sessions(db, user.id)

    db.add(UserSession(
        user_id=user.id,
        refresh_token_hash=app_jwt.hash_jti(jti),
        expires_at=_now() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        ip_address=ip,
        user_agent=(user_agent or "")[:512] or None,
    ))

    user.last_login_at = _now()
    user.last_login_ip = ip

    try:
        await append_audit_entry(
            db,
            actor_id=str(user.id),
            actor_email=user.email,
            action="twa.login.success",
            notes=f"tg_chat_id={tg_chat_id}",
            ip_address=ip,
            user_agent=user_agent,
        )
    except Exception:
        log.warning("audit append failed in twa-login", exc_info=True)

    await db.commit()
    return user, access, refresh
