"""MFA-aware login flow (Pack 13.0c).

Two endpoints:
  - POST /auth/login-mfa  ╨▓╨ВтАЭ wraps auth_service.authenticate() with MFA gating
  - POST /auth/verify-mfa ╨▓╨ВтАЭ completes the second step (code OR recovery)

Design:
  - We do NOT modify /auth/login or auth_service.authenticate() ╨▓╨ВтАЭ both remain
    unchanged for backward compatibility.
  - When a user has MFA enabled, /auth/login-mfa calls authenticate() (which
    succeeds and creates a UserSession), then immediately REVOKES that session
    and issues a one-shot MFA code via the existing telegram_outbox machinery.
    Tokens are NOT returned at this stage.
  - /auth/verify-mfa accepts either a 6-digit code (with challenge_id) or a
    recovery code (with login). On success it issues a fresh access+refresh
    pair and a new UserSession ╨▓╨ВтАЭ exactly as authenticate() would.

Rate-limited the same way as /auth/login (settings.RATE_LIMIT_AUTH).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core import jwt as app_jwt
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.mfa import MfaLoginChallenge, MfaMethod
from app.models.user import Role, User, UserSession
from app.schemas.auth import LoginRequest, TokenPair
from app.services import auth_service, mfa_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth-mfa"])


# =====================================================================
# Schemas
# =====================================================================

class LoginMfaResponse(BaseModel):
    """Unified shape ╨▓╨ВтАЭ frontend checks `mfa_required` flag.

    Two variants:
      A) mfa_required=False ╨▓╨ВтАЭ full TokenPair fields populated
      B) mfa_required=True  ╨▓╨ВтАЭ challenge_id + method + masked_destination
    """
    mfa_required: bool = False

    # Variant A ╨▓╨ВтАЭ TokenPair fields
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None

    # Variant B ╨▓╨ВтАЭ MFA challenge fields
    challenge_id: Optional[str] = None
    method: Optional[Literal["telegram", "totp", "both"]] = None
    masked_destination: Optional[str] = None
    ttl_minutes: Optional[int] = None


class VerifyMfaIn(BaseModel):
    """Either (challenge_id + code) OR (login + recovery_code)."""
    # Path A ╨▓╨ВтАЭ TG code
    challenge_id: Optional[str] = None
    code: Optional[str] = Field(None, min_length=4, max_length=12)

    # Path B ╨▓╨ВтАЭ recovery code
    login: Optional[str] = Field(None, max_length=255)
    recovery_code: Optional[str] = Field(None, min_length=8, max_length=20)


# =====================================================================
# Helpers
# =====================================================================

def _client_ip(request: Request) -> Optional[str]:
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


def _mask_destination(user: User) -> str:
    """Pretty masked destination for the UI ('@vk***ov' or 'Telegram')."""
    username = getattr(user, "telegram_username", None)
    if not username:
        return "Telegram"
    if len(username) > 4:
        return f"@{username[:2]}***{username[-2:]}"
    return "@***"


async def _load_user_with_roles(db: AsyncSession, user_id) -> Optional[User]:
    """Load a User with roles + permissions eagerly (needed for JWT claims)."""
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


async def _revoke_session_by_refresh(db: AsyncSession, refresh_token: str) -> None:
    """Revoke the UserSession created by authenticate() ╨▓╨ВтАЭ we don't want a
    valid refresh in the DB while MFA is still pending."""
    try:
        claims = app_jwt.decode_token(refresh_token, expected_type="refresh")
    except Exception as e:
        log.warning("Could not decode just-issued refresh for revocation: %s", e)
        return
    jti = claims.get("jti")
    if not jti:
        return
    h = app_jwt.hash_jti(jti)
    result = await db.execute(
        select(UserSession).where(UserSession.refresh_token_hash == h)
    )
    session = result.scalar_one_or_none()
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)


async def _issue_tokens_for_user(
    db: AsyncSession, user: User, ip: Optional[str], user_agent: Optional[str],
) -> tuple[str, str]:
    """Mint a new access + refresh pair and persist UserSession.

    Mirrors the issuance path inside auth_service.authenticate() so the result
    is indistinguishable from a normal (non-MFA) login.
    """
    access = app_jwt.create_access_token(
        subject=str(user.id),
        extra_claims={
            "email": user.email,
            "is_owner": user.is_owner,
            "roles": [r.code for r in user.roles],
        },
    )
    refresh, jti = app_jwt.create_refresh_token(subject=str(user.id))
    # Cap concurrent sessions before adding the new one.
    from app.services.auth_service import _prune_concurrent_sessions
    await _prune_concurrent_sessions(db, user.id)
    db.add(UserSession(
        user_id=user.id,
        refresh_token_hash=app_jwt.hash_jti(jti),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        ip_address=ip,
        user_agent=user_agent,
    ))
    user.last_login_at = datetime.now(timezone.utc)
    if ip:
        user.last_login_ip = ip
    return access, refresh


def _method_str(method) -> Optional[str]:
    if method is None:
        return None
    if hasattr(method, "value"):
        return method.value
    return str(method)


# =====================================================================
# POST /auth/login-mfa  ╨▓╨ВтАЭ MFA-aware login
# =====================================================================

@router.post("/login-mfa", response_model=LoginMfaResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login_mfa(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginMfaResponse:
    """Drop-in replacement for /auth/login with MFA support.

    - On valid credentials AND mfa_enabled=False ╨▓тАатАЩ returns full TokenPair.
    - On valid credentials AND mfa_enabled=True ╨▓тАатАЩ revokes the just-issued
      session, emits a one-shot code via Telegram, returns {mfa_required:true}.
    """
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")[:512]

    # Reuse canonical authenticate() ╨▓╨ВтАЭ handles lockout, audit chain, rehashing
    user, access, refresh = await auth_service.authenticate(
        db,
        login_id=body.login,
        password=body.password,
        ip=ip,
        user_agent=ua,
    )
    # authenticate() commits its own work. We start a fresh implicit transaction below.

    # RAW SQL BYPASS for mfa_enabled тАФ ORM attribute access after authenticate()'s
    # commit returns stale values in async context.
    mfa_row = await db.execute(
        text("SELECT mfa_enabled, mfa_method::text AS mfa_method, "
             "telegram_chat_id_encrypted IS NOT NULL AS tg_linked, "
             "telegram_username FROM users WHERE id = :id"),
        {"id": user.id},
    )
    mfa_data = mfa_row.first()
    _mfa_enabled = bool(mfa_data.mfa_enabled) if mfa_data else False
    _mfa_method_str = (mfa_data.mfa_method or "none") if mfa_data else "none"
    _tg_linked = bool(mfa_data.tg_linked) if mfa_data else False
    log.warning("login-mfa-raw: user=%s mfa_enabled=%s method=%s tg=%s",
                user.email, _mfa_enabled, _mfa_method_str, _tg_linked)

    # Stash for later use in this function
    user._mfa_enabled_raw = _mfa_enabled  # type: ignore
    user._mfa_method_raw = _mfa_method_str  # type: ignore
    user._tg_linked_raw = _tg_linked  # type: ignore

    if not _mfa_enabled:
        # No MFA ╨▓тАатАЩ return tokens as usual
        return LoginMfaResponse(
            mfa_required=False,
            access_token=access,
            refresh_token=refresh,
            token_type="Bearer",
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )

    # MFA required ╨▓тАатАЩ revoke the freshly created session + emit a code challenge
    method_value = _mfa_method_str

    if method_value in ("telegram", "both"):
        if not _tg_linked:
            # MFA flagged on but no destination ╨▓╨ВтАЭ degrade gracefully
            log.warning("User %s has mfa_enabled but no telegram link", user.email)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "╨а╤Т╨а╤Ф╨а╤Ф╨а┬░╨б╤У╨а╨Е╨бтАЪ ╨а┬╖╨а┬░╨бтА░╨а╤С╨бтА░╨бтАШ╨а╨Е 2FA, ╨а╨Е╨а╤Х ╨б╨Г╨а╤Ч╨а╤Х╨б╨Г╨а╤Х╨а┬▒ ╨а╥С╨а╤Х╨б╨Г╨бтАЪ╨а┬░╨а╨Ж╨а╤Ф╨а╤С ╨а╨Е╨а┬╡ ╨а╨Е╨а┬░╨б╨Г╨бтАЪ╨б╨В╨а╤Х╨а┬╡╨а╨Е. "
                "╨а╨О╨а╨Ж╨б╨П╨а┬╢╨а╤С╨бтАЪ╨а┬╡╨б╨Г╨б╨К ╨б╨Г ╨а┬░╨а╥С╨а╤Ш╨а╤С╨а╨Е╨а╤С╨б╨Г╨бтАЪ╨б╨В╨а┬░╨бтАЪ╨а╤Х╨б╨В╨а╤Х╨а╤Ш.",
            )

    await _revoke_session_by_refresh(db, refresh)

    try:
        challenge, _plain_code = await mfa_service.emit_login_challenge(
            db, user, ip=ip, ua=ua,
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    await db.commit()

    return LoginMfaResponse(
        mfa_required=True,
        challenge_id=str(challenge.id),
        method=method_value if method_value in ("telegram", "totp", "both") else "telegram",
        masked_destination=_mask_destination(user),
        ttl_minutes=mfa_service.LOGIN_CODE_TTL_MINUTES,
    )


# =====================================================================
# POST /auth/verify-mfa  ╨▓╨ВтАЭ second step
# =====================================================================

@router.post("/verify-mfa", response_model=TokenPair)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def verify_mfa(
    request: Request,
    body: VerifyMfaIn,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Complete the MFA login flow.

    Path A (Telegram code): provide `challenge_id` + `code`.
    Path B (recovery code): provide `login` + `recovery_code`.
    """
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")[:512]

    user: Optional[User] = None

    # === Path A ╨▓╨ВтАЭ Telegram challenge ===
    if body.challenge_id and body.code:
        ok = await mfa_service.verify_login_challenge(
            db, body.challenge_id, body.code.strip()
        )
        if not ok:
            await db.commit()
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "╨а╤Ь╨а┬╡╨а╨Ж╨а┬╡╨б╨В╨а╨Е╨бтА╣╨атДЦ ╨а╤Ф╨а╤Х╨а╥С ╨а╤С╨а┬╗╨а╤С ╨а╤С╨б╨Г╨бтАЪ╨бтАШ╨а╤Ф ╨б╨Г╨б╨В╨а╤Х╨а╤Ф ╨а╥С╨а┬╡╨атДЦ╨б╨Г╨бтАЪ╨а╨Ж╨а╤С╨б╨П",
            )

        # Load the user via challenge.user_id
        result = await db.execute(
            select(MfaLoginChallenge).where(MfaLoginChallenge.id == body.challenge_id)
        )
        challenge: Optional[MfaLoginChallenge] = result.scalar_one_or_none()
        if challenge is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Challenge ╨а╨Е╨а┬╡ ╨а╨Е╨а┬░╨атДЦ╨а╥С╨а┬╡╨а╨Е")
        user = await _load_user_with_roles(db, challenge.user_id)

    # === Path B ╨▓╨ВтАЭ recovery code ===
    elif body.login and body.recovery_code:
        needle = body.login.strip().lower()
        result = await db.execute(
            select(User)
            .where(or_(User.email.ilike(needle), User.username.ilike(needle)))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        user = result.scalar_one_or_none()
        if user is None or not user.is_active or not getattr(user, "mfa_enabled", False):
            # Constant-time-ish: still consume DB time before erroring
            await db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "╨а╤Ь╨а┬╡╨а╨Ж╨а┬╡╨б╨В╨а╨Е╨бтА╣╨атДЦ recovery-╨а╤Ф╨а╤Х╨а╥С")

        ok = await mfa_service.verify_recovery_code(db, user, body.recovery_code.strip())
        if not ok:
            await db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "╨а╤Ь╨а┬╡╨а╨Ж╨а┬╡╨б╨В╨а╨Е╨бтА╣╨атДЦ recovery-╨а╤Ф╨а╤Х╨а╥С")

    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "╨а╤Я╨а┬╡╨б╨В╨а┬╡╨а╥С╨а┬░╨атДЦ╨бтАЪ╨а┬╡ challenge_id + code ╨а┬Ш╨атА║╨а┬Ш login + recovery_code",
        )

    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "╨а╤Я╨а╤Х╨а┬╗╨б╨К╨а┬╖╨а╤Х╨а╨Ж╨а┬░╨бтАЪ╨а┬╡╨а┬╗╨б╨К ╨а╨Е╨а┬╡ ╨а╨Е╨а┬░╨атДЦ╨а╥С╨а┬╡╨а╨Е ╨а╤С╨а┬╗╨а╤С ╨а╤Х╨бтАЪ╨а╤Ф╨а┬╗╨б╨Л╨бтАб╨бтАШ╨а╨Е",
        )

    access, refresh = await _issue_tokens_for_user(db, user, ip, ua)
    await db.commit()

    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        token_type="Bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )
