"""Telegram bot callbacks — thin HTTP layer (refactored 2026-05-25).

Auth: every request signed with HMAC(BOT_CALLBACK_SECRET, body) in
`X-Bot-Signature` header. Verified inline; reject mismatches with 401.

Endpoints:
  POST /bot/moderation/approve              — approve via inline button
  POST /bot/moderation/reject               — reject via inline button
  POST /bot/tg-link/confirm                 — confirm /start linkage
  POST /bot/tg-link/deny                    — invalidate link token
  POST /bot/tg-callbacks/mfa-report         — «Это не я» suspicious-MFA flag
  POST /bot/tg-callbacks/kpi/{id}/decision  — KPI approve/reject
  POST /bot/tg-callbacks/procurement/{id}/decision — procurement decision
  POST /bot/tg-callbacks/comment-from-tg    — post comment from TG reply
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.dependencies.bot_callbacks import BotCallbacksServiceDep

log = logging.getLogger(__name__)
router = APIRouter(prefix="/bot", tags=["bot-callbacks"])


# ─── HMAC auth ────────────────────────────────────────────────────

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


# ─── schemas ──────────────────────────────────────────────────────

class ModerationActionIn(BaseModel):
    chat_id: int
    submission_id: str
    note: Optional[str] = None


class ModerationActionOut(BaseModel):
    ok: bool
    detail: str
    submission_id: str
    new_status: Optional[str] = None


class TgLinkConfirmIn(BaseModel):
    chat_id: int
    token: str
    username: Optional[str] = None


class TgLinkConfirmOut(BaseModel):
    ok: bool
    detail: str
    email: Optional[str] = None


class TgLinkDenyIn(BaseModel):
    chat_id: int
    token: str


class TgLinkDenyOut(BaseModel):
    ok: bool
    detail: str


class MfaReportIn(BaseModel):
    chat_id: int
    mfa_token: Optional[str] = None


class MfaReportOut(BaseModel):
    ok: bool
    detail: str


class ModuleDecisionIn(BaseModel):
    chat_id: int
    decision: str  # 'approve' | 'reject'
    note: Optional[str] = None


class ModuleDecisionOut(BaseModel):
    ok: bool
    detail: str
    submission_id: str
    new_status: Optional[str] = None


class CommentFromTgIn(BaseModel):
    chat_id: int
    entity_type: str
    entity_id: str
    body: str


class CommentFromTgOut(BaseModel):
    ok: bool
    comment_id: Optional[str] = None
    detail: Optional[str] = None


# ─── moderation approve/reject ───────────────────────────────────

@router.post("/moderation/approve", response_model=ModerationActionOut)
async def bot_moderation_approve(
    body: ModerationActionIn,
    service: BotCallbacksServiceDep,
    _: None = Depends(_verify_signature),
):
    result = await service.moderation_decision(
        decision="approve",
        chat_id=body.chat_id,
        submission_id=body.submission_id,
        note=body.note,
    )
    return ModerationActionOut(**result)


@router.post("/moderation/reject", response_model=ModerationActionOut)
async def bot_moderation_reject(
    body: ModerationActionIn,
    service: BotCallbacksServiceDep,
    _: None = Depends(_verify_signature),
):
    result = await service.moderation_decision(
        decision="reject",
        chat_id=body.chat_id,
        submission_id=body.submission_id,
        note=body.note,
    )
    return ModerationActionOut(**result)


# ─── tg link confirm / deny ──────────────────────────────────────

@router.post("/tg-link/confirm", response_model=TgLinkConfirmOut)
async def bot_tg_link_confirm(
    body: TgLinkConfirmIn,
    service: BotCallbacksServiceDep,
    _: None = Depends(_verify_signature),
):
    result = await service.tg_link_confirm(
        token=body.token, chat_id=body.chat_id, username=body.username,
    )
    return TgLinkConfirmOut(**result)


@router.post("/tg-link/deny", response_model=TgLinkDenyOut)
async def bot_tg_link_deny(
    body: TgLinkDenyIn,
    service: BotCallbacksServiceDep,
    _: None = Depends(_verify_signature),
):
    result = await service.tg_link_deny(token=body.token)
    return TgLinkDenyOut(**result)


# ─── MFA report ───────────────────────────────────────────────────

@router.post("/tg-callbacks/mfa-report", response_model=MfaReportOut)
async def bot_tg_mfa_report(
    body: MfaReportIn,
    service: BotCallbacksServiceDep,
    _: None = Depends(_verify_signature),
):
    result = await service.mfa_report(
        chat_id=body.chat_id, mfa_token=body.mfa_token,
    )
    return MfaReportOut(**result)


# ─── KPI / procurement decisions ─────────────────────────────────

@router.post("/tg-callbacks/kpi/{submission_id}/decision",
             response_model=ModuleDecisionOut)
async def bot_tg_kpi_decision(
    submission_id: str,
    body: ModuleDecisionIn,
    service: BotCallbacksServiceDep,
    _: None = Depends(_verify_signature),
):
    result = await service.module_submission_decision(
        module="kpi", submission_id=submission_id,
        chat_id=body.chat_id, decision=body.decision, note=body.note,
    )
    return ModuleDecisionOut(**result)


@router.post("/tg-callbacks/procurement/{submission_id}/decision",
             response_model=ModuleDecisionOut)
async def bot_tg_procurement_decision(
    submission_id: str,
    body: ModuleDecisionIn,
    service: BotCallbacksServiceDep,
    _: None = Depends(_verify_signature),
):
    result = await service.module_submission_decision(
        module="procurement", submission_id=submission_id,
        chat_id=body.chat_id, decision=body.decision, note=body.note,
    )
    return ModuleDecisionOut(**result)


# ─── comment-from-tg ──────────────────────────────────────────────

@router.post("/tg-callbacks/comment-from-tg", response_model=CommentFromTgOut)
async def bot_tg_comment_from_tg(
    body: CommentFromTgIn,
    service: BotCallbacksServiceDep,
    _: None = Depends(_verify_signature),
):
    result = await service.comment_from_tg(
        chat_id=body.chat_id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        body=body.body,
    )
    return CommentFromTgOut(**result)
