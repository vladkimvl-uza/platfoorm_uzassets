"""Service-account endpoints for the Telegram bot (Pack 13.2).

These let the bot resolve a Telegram chat_id → User, then perform actions
on behalf of that user (approve / reject moderation submissions from inline
keyboard buttons in a Telegram message).

Auth model:
  - Bot signs every request with HMAC(BOT_CALLBACK_SECRET, body) in
    header `X-Bot-Signature`. Backend recomputes and rejects mismatches.
  - All actions are still logged in audit_log with the resolved user as
    the actor (so the trail is identical to in-app actions).

This is intentionally a minimal surface — only the actions that are
exposed as Telegram inline buttons live here.
"""
import hashlib
import hmac
import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.encryption import decrypt
from app.database import get_db
from app.models.user import Role, User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/bot", tags=["bot-callbacks"])

# =====================================================================
# Auth helper
# =====================================================================

def _shared_secret() -> str:
    secret = os.getenv("BOT_CALLBACK_SECRET", "")
    if not secret:
        log.error("BOT_CALLBACK_SECRET is not set — bot callbacks disabled")
    return secret


async def _verify_signature(
    request: Request,
    x_bot_signature: Optional[str] = Header(None, alias="X-Bot-Signature"),
) -> None:
    secret = _shared_secret()
    if not secret or not x_bot_signature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bot signature required")
    body = await request.body()
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_bot_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad bot signature")


# =====================================================================
# Shared lookup — chat_id → User
# =====================================================================

async def _find_user_by_chat_id(db: AsyncSession, chat_id: int) -> Optional[User]:
    """Scan users with a TG link, decrypt and match chat_id.
    Brute scan is acceptable: we never have more than a few hundred linked users.
    """
    result = await db.execute(
        select(User)
        .where(User.telegram_chat_id_encrypted.is_not(None))
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    candidates = result.scalars().all()
    for u in candidates:
        try:
            plain = decrypt(u.telegram_chat_id_encrypted)
            if plain and int(plain) == int(chat_id):
                return u
        except Exception:
            continue
    return None


# =====================================================================
# Schemas
# =====================================================================

class ModerationActionIn(BaseModel):
    chat_id: int
    submission_id: str
    note: Optional[str] = None


class ModerationActionOut(BaseModel):
    ok: bool
    detail: str
    submission_id: str
    new_status: Optional[str] = None


# =====================================================================
# POST /bot/moderation/approve
# =====================================================================

@router.post("/moderation/approve", response_model=ModerationActionOut)
async def bot_moderation_approve(
    request: Request,
    body: ModerationActionIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_signature),
):
    user = await _find_user_by_chat_id(db, body.chat_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram аккаунт не привязан")

    try:
        sub_uuid = UUID(body.submission_id)
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid submission_id")

    try:
        from app.services import moderation_service
        sub = await moderation_service.approve(
            db,
            submission_id=sub_uuid,
            actor=user,
            note=body.note,
        )
        return ModerationActionOut(
            ok=True,
            detail="Принято",
            submission_id=str(sub.id),
            new_status=str(getattr(sub.status, "value", sub.status)) if hasattr(sub, "status") else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.warning("bot moderation approve failed: %s", e, exc_info=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# =====================================================================
# POST /bot/moderation/reject
# =====================================================================

@router.post("/moderation/reject", response_model=ModerationActionOut)
async def bot_moderation_reject(
    request: Request,
    body: ModerationActionIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_signature),
):
    user = await _find_user_by_chat_id(db, body.chat_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram аккаунт не привязан")

    try:
        sub_uuid = UUID(body.submission_id)
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid submission_id")

    try:
        from app.services import moderation_service
        sub = await moderation_service.reject(
            db,
            submission_id=sub_uuid,
            actor=user,
            note=body.note or "Отклонено из Telegram",
        )
        return ModerationActionOut(
            ok=True,
            detail="Отклонено",
            submission_id=str(sub.id),
            new_status=str(getattr(sub.status, "value", sub.status)) if hasattr(sub, "status") else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.warning("bot moderation reject failed: %s", e, exc_info=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# =====================================================================
# Pack 13.3 — Telegram link confirm/deny (two-step linkage)
# =====================================================================

class TgLinkConfirmIn(BaseModel):
    chat_id: int
    token: str
    username: Optional[str] = None


class TgLinkConfirmOut(BaseModel):
    ok: bool
    detail: str
    email: Optional[str] = None


@router.post("/tg-link/confirm", response_model=TgLinkConfirmOut)
async def bot_tg_link_confirm(
    request: Request,
    body: TgLinkConfirmIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_signature),
):
    from app.services import mfa_service
    user = await mfa_service.confirm_link_telegram(
        db,
        token=body.token,
        chat_id=body.chat_id,
        username=body.username or None,
    )
    if user is None:
        from sqlalchemy import select as _select
        from app.services.mfa_service import _hash_sha256 as _h
        from app.models.user import User as _U
        r = await db.execute(
            _select(_U).where(_U.telegram_link_token_hashed == _h(body.token))
        )
        if r.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Токен не найден")
        else:
            raise HTTPException(status.HTTP_410_GONE, "Токен истёк")
    await db.commit()
    return TgLinkConfirmOut(ok=True, detail="linked", email=user.email)


class TgLinkDenyIn(BaseModel):
    chat_id: int
    token: str


class TgLinkDenyOut(BaseModel):
    ok: bool
    detail: str


@router.post("/tg-link/deny", response_model=TgLinkDenyOut)
async def bot_tg_link_deny(
    request: Request,
    body: TgLinkDenyIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_signature),
):
    from sqlalchemy import select as _select
    from app.services.mfa_service import _hash_sha256 as _h
    from app.models.user import User as _U
    h = _h(body.token)
    res = await db.execute(_select(_U).where(_U.telegram_link_token_hashed == h))
    user = res.scalar_one_or_none()
    if user is not None:
        user.telegram_link_token_hashed = None
        user.telegram_link_token_expires_at = None
        await db.commit()
    return TgLinkDenyOut(ok=True, detail="token invalidated")
