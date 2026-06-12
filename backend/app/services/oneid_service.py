"""ЕСИ / One ID (Единая система идентификации) — OAuth2/OIDC аутентификация.

Реализует требование O'zMSt 149 п.6.8: вход заявителей через национальную
систему идентификации (id.egov.uz / sso.egov.uz). По образцу
``twa_auth_service``: внешняя identity → локальный User → стандартная пара
JWT через те же помощники, что и /auth/login.

СКАФФОЛД: активен только при ``settings.ONEID_ENABLED=True`` и заданных
client_id/secret. Без этого все операции возвращают 503 — текущий вход
по логину/паролю не затрагивается.

Поток (Authorization Code):
  1. GET /auth/oneid/login → редирект на ONEID_AUTHORIZE_URL c подписанным
     ``state`` (HMAC, TTL) для защиты от CSRF.
  2. One ID аутентифицирует заявителя и редиректит на ONEID_REDIRECT_URI
     с ?code&state.
  3. handle_callback: проверка state → обмен code→access_token →
     запрос userinfo (ПИНФЛ, ФИО, email) → поиск/привязка локального User →
     выпуск (access, refresh) JWT.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core import jwt as app_jwt
from app.core.audit_chain import append_audit_entry
from app.models.user import Role, User, UserSession

log = logging.getLogger(__name__)


# ─────────────────────────── helpers ───────────────────────────

def _require_enabled() -> None:
    if not settings.ONEID_ENABLED:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Вход через One ID отключён (ONEID_ENABLED=false).",
        )
    if not settings.ONEID_CLIENT_ID or not settings.ONEID_CLIENT_SECRET:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "One ID не настроен: отсутствуют ONEID_CLIENT_ID / ONEID_CLIENT_SECRET.",
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _state_key() -> bytes:
    """Стабильный по окружению ключ для подписи state.

    Берём секрет HMAC-цепочки аудита (файл, стабилен между воркерами), иначе
    производный от приватного JWT-ключа. Гарантирует, что state, подписанный
    одним воркером, проверится другим.
    """
    secret = settings.read_audit_hmac_secret()
    if secret:
        return hashlib.sha256(b"oneid-state:" + secret).digest()
    priv = settings.read_jwt_private_key()
    if priv:
        return hashlib.sha256(b"oneid-state:" + priv.encode("utf-8")).digest()
    raise HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Нет стабильного секрета для подписи state One ID.",
    )


def _sign_state() -> str:
    """Создаёт подписанный state: base64url(nonce.ts).hmac."""
    nonce = secrets.token_urlsafe(16)
    ts = str(int(time.time()))
    payload = f"{nonce}.{ts}"
    sig = hmac.new(_state_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}.{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _verify_state(state: str) -> None:
    """Проверяет подпись и TTL state. Бросает 400 при невалидности."""
    try:
        raw = base64.urlsafe_b64decode(state.encode("ascii")).decode("utf-8")
        nonce, ts, sig = raw.split(".")
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Некорректный state One ID.")
    payload = f"{nonce}.{ts}"
    expected = hmac.new(_state_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Подпись state One ID не совпала.")
    if int(time.time()) - int(ts) > settings.ONEID_STATE_TTL_SECONDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "state One ID истёк.")


def build_login_url() -> str:
    """URL для редиректа пользователя на страницу One ID."""
    _require_enabled()
    params = {
        "response_type": "code",
        "client_id": settings.ONEID_CLIENT_ID,
        "redirect_uri": settings.ONEID_REDIRECT_URI,
        "scope": settings.ONEID_SCOPE,
        "state": _sign_state(),
    }
    return f"{settings.ONEID_AUTHORIZE_URL}?{urlencode(params)}"


async def _exchange_code(code: str) -> str:
    """Обмен authorization code на access_token (One ID grant_type)."""
    data = {
        "grant_type": "one_authorization_code",
        "code": code,
        "client_id": settings.ONEID_CLIENT_ID,
        "client_secret": settings.ONEID_CLIENT_SECRET,
        "redirect_uri": settings.ONEID_REDIRECT_URI,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(settings.ONEID_TOKEN_URL, data=data)
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"One ID token endpoint недоступен: {e}")
    if resp.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "One ID отклонил обмен кода.")
    try:
        token = resp.json().get("access_token")
    except Exception:
        token = None
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "One ID не вернул access_token.")
    return token


async def _fetch_userinfo(access_token: str) -> dict:
    """Запрос профиля заявителя из One ID (ПИНФЛ, ФИО, email)."""
    data = {
        "grant_type": "one_access_token_identify",
        "access_token": access_token,
        "client_id": settings.ONEID_CLIENT_ID,
        "client_secret": settings.ONEID_CLIENT_SECRET,
        "scope": settings.ONEID_SCOPE,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(settings.ONEID_TOKEN_URL, data=data)
            payload = resp.json()
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"One ID userinfo недоступен: {e}")
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "One ID вернул некорректный профиль.")
    return payload


def _extract_identity(info: dict) -> dict:
    """Нормализует профиль One ID к {sub, pinfl, full_name, email}."""
    pinfl = str(info.get("pin") or info.get("pinfl") or "").strip() or None
    sub = str(info.get("sub") or info.get("user_id") or pinfl or "").strip() or None
    full_name = (
        info.get("full_name")
        or " ".join(filter(None, [info.get("sur_name"), info.get("first_name"), info.get("mid_name")])).strip()
        or None
    )
    email = (info.get("email") or "").strip().lower() or None
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "One ID не вернул идентификатор субъекта.")
    return {"sub": sub, "pinfl": pinfl, "full_name": full_name, "email": email}


async def _resolve_user(db: AsyncSession, ident: dict) -> Optional[User]:
    """Поиск локального пользователя: по oneid_sub → pinfl → email."""
    conds = [User.oneid_sub == ident["sub"]]
    if ident.get("pinfl"):
        conds.append(User.pinfl == ident["pinfl"])
    if ident.get("email"):
        conds.append(User.email == ident["email"])
    result = await db.execute(
        select(User)
        .where(or_(*conds))
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalars().first()


async def handle_callback(
    db: AsyncSession,
    *,
    code: str,
    state: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[User, str, str]:
    """Полный callback: state → code→token → userinfo → User → (access, refresh)."""
    _require_enabled()
    _verify_state(state)

    access_token = await _exchange_code(code)
    info = await _fetch_userinfo(access_token)
    ident = _extract_identity(info)

    user = await _resolve_user(db, ident)

    if user is None:
        if not settings.ONEID_AUTO_PROVISION:
            try:
                await append_audit_entry(
                    db, action="oneid.login.unlinked",
                    notes=f"sub={ident['sub']} pinfl={ident.get('pinfl')} не привязан",
                    ip_address=ip, user_agent=user_agent,
                )
                await db.commit()
            except Exception:
                await db.rollback()
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Учётная запись One ID не привязана к платформе. Обратитесь к администратору.",
            )
        # Авто-провижининг (по умолчанию OFF): создаём неактивного пользователя
        user = User(
            email=ident.get("email") or f"{ident['sub']}@oneid.local",
            full_name=ident.get("full_name"),
            is_active=False,  # требует активации администратором (least privilege)
            password_hash=None,
        )
        db.add(user)
        await db.flush()

    # Привязка идентификаторов One ID (идемпотентно)
    if not user.oneid_sub:
        user.oneid_sub = ident["sub"]
    if ident.get("pinfl") and not user.pinfl:
        user.pinfl = ident["pinfl"]
    if user.oneid_linked_at is None:
        user.oneid_linked_at = _now()

    if not user.is_active:
        try:
            await append_audit_entry(
                db, action="oneid.login.inactive",
                actor_id=str(user.id), actor_email=user.email,
                notes="вход через One ID на неактивную учётную запись",
                ip_address=ip, user_agent=user_agent,
            )
            await db.commit()
        except Exception:
            await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт отключён или ожидает активации.")

    # Выпуск пары токенов — те же помощники, что и /auth/login
    access = app_jwt.create_access_token(
        subject=str(user.id),
        extra_claims={
            "email": user.email,
            "is_owner": user.is_owner,
            "roles": [r.code for r in user.roles],
            "oneid": True,  # маркер: вход через ЕСИ
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
            db, actor_id=str(user.id), actor_email=user.email,
            action="oneid.login.success",
            notes=f"sub={ident['sub']} pinfl={ident.get('pinfl')}",
            ip_address=ip, user_agent=user_agent,
        )
    except Exception:
        log.warning("audit append failed in oneid-login", exc_info=True)

    await db.commit()
    return user, access, refresh
