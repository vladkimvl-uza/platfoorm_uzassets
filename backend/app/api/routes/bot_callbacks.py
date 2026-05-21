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
        from app.models.moderation import ModerationSubmission
        from app.services import moderation_service
        sub_row = await db.get(ModerationSubmission, sub_uuid)
        if sub_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
        sub = await moderation_service.approve(
            db,
            sub=sub_row,
            user=user,
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
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
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
        from app.models.moderation import ModerationSubmission
        from app.services import moderation_service
        sub_row = await db.get(ModerationSubmission, sub_uuid)
        if sub_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
        sub = await moderation_service.reject(
            db,
            sub=sub_row,
            user=user,
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
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
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


# =====================================================================
# Pack 147 / Phase A — premium Telegram quick-action callbacks
# =====================================================================
# Module-specific inline buttons on notifications. The bot signs requests,
# we resolve chat_id → User, and run the action under that user's identity.
# =====================================================================


# ─── MFA «Это не я» ────────────────────────────────────────────────

class MfaReportIn(BaseModel):
    chat_id: int
    mfa_token: Optional[str] = None


class MfaReportOut(BaseModel):
    ok: bool
    detail: str


@router.post("/tg-callbacks/mfa-report", response_model=MfaReportOut)
async def bot_tg_mfa_report(
    request: Request,
    body: MfaReportIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_signature),
):
    """User reported a suspicious MFA prompt.
    - Records a critical audit_log entry (audit.security_flag)
    - Best-effort: invalidates any in-flight MFA challenge tied to the token
    """
    user = await _find_user_by_chat_id(db, body.chat_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram аккаунт не привязан")

    try:
        from app.services import audit_service
        await audit_service.write_event(
            db,
            actor_id=user.id,
            actor_email=user.email,
            actor_role=(user.roles[0].code if user.roles else None),
            action="security_flag",
            module="auth",
            entity_type="mfa_attempt",
            entity_id=(body.mfa_token or "")[:64] or None,
            notes="Пользователь нажал «Это не я» в Telegram под MFA-кодом",
            meta={"source": "telegram_inline", "mfa_token": (body.mfa_token or "")[:64]},
            is_critical=True,
        )
    except Exception as e:
        log.warning("audit write_event failed in mfa-report: %s", e, exc_info=True)

    # Best-effort: revoke active MFA challenge if mfa_service supports it
    try:
        from app.services import mfa_service
        revoke = getattr(mfa_service, "revoke_active_challenge", None)
        if callable(revoke):
            try:
                await revoke(db, user=user, token=body.mfa_token or "")
            except Exception:
                pass
    except Exception:
        pass

    await db.commit()
    return MfaReportOut(ok=True, detail="reported")


# ─── KPI / Procurement decision ────────────────────────────────────

class ModuleDecisionIn(BaseModel):
    chat_id: int
    decision: str  # 'approve' | 'reject'
    note: Optional[str] = None


class ModuleDecisionOut(BaseModel):
    ok: bool
    detail: str
    submission_id: str
    new_status: Optional[str] = None


async def _module_submission_decision(
    db: AsyncSession,
    *,
    module: str,
    submission_id: str,
    chat_id: int,
    decision: str,
    note: Optional[str],
) -> ModuleDecisionOut:
    user = await _find_user_by_chat_id(db, chat_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram аккаунт не привязан")

    try:
        sub_uuid = UUID(submission_id)
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid submission_id")

    from app.models.moderation import ModerationSubmission
    from app.services import moderation_service

    sub_row = await db.get(ModerationSubmission, sub_uuid)
    if sub_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")

    sub_module = getattr(sub_row, "module", None)
    sub_module_value = getattr(sub_module, "value", sub_module)
    if sub_module_value and str(sub_module_value).lower() != module:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Submission принадлежит модулю «{sub_module_value}», ожидался «{module}»",
        )

    try:
        if decision == "approve":
            sub = await moderation_service.approve(db, sub=sub_row, user=user, note=note)
            detail = "Утверждено"
        elif decision == "reject":
            sub = await moderation_service.reject(
                db, sub=sub_row, user=user,
                note=note or f"Отклонено через Telegram ({module})",
            )
            detail = "Отклонено"
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid decision")
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except Exception as e:
        log.warning("module decision failed (%s/%s): %s", module, decision, e, exc_info=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    new_status = str(getattr(sub.status, "value", sub.status)) if hasattr(sub, "status") else None
    return ModuleDecisionOut(
        ok=True,
        detail=detail,
        submission_id=str(sub.id),
        new_status=new_status,
    )


@router.post("/tg-callbacks/kpi/{submission_id}/decision", response_model=ModuleDecisionOut)
async def bot_tg_kpi_decision(
    submission_id: str,
    request: Request,
    body: ModuleDecisionIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_signature),
):
    return await _module_submission_decision(
        db,
        module="kpi",
        submission_id=submission_id,
        chat_id=body.chat_id,
        decision=body.decision,
        note=body.note,
    )


@router.post("/tg-callbacks/procurement/{submission_id}/decision", response_model=ModuleDecisionOut)
async def bot_tg_procurement_decision(
    submission_id: str,
    request: Request,
    body: ModuleDecisionIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_signature),
):
    return await _module_submission_decision(
        db,
        module="procurement",
        submission_id=submission_id,
        chat_id=body.chat_id,
        decision=body.decision,
        note=body.note,
    )


# =====================================================================
# Comment from Telegram (mention reply flow, Pack 149)
# =====================================================================

class CommentFromTgIn(BaseModel):
    chat_id: int
    entity_type: str         # 'task' | 'project'
    entity_id: str
    body: str


class CommentFromTgOut(BaseModel):
    ok: bool
    comment_id: Optional[str] = None
    detail: Optional[str] = None


@router.post("/tg-callbacks/comment-from-tg", response_model=CommentFromTgOut)
async def bot_tg_comment_from_tg(
    request: Request,
    body: CommentFromTgIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_signature),
):
    """Post a comment to a task/project from a Telegram reply.
    Used by mention-reply flow: user clicks «Ответить в чате», their next
    text message gets posted here as a comment with their user identity.
    """
    if body.entity_type not in ("task", "project"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "entity_type must be 'task' or 'project'")
    if not body.body or not body.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body required")

    user = await _find_user_by_chat_id(db, body.chat_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram chat not linked")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is inactive")

    if body.entity_type == "task":
        from app.models.task import Task, TaskComment
        ent = (await db.execute(select(Task).where(Task.id == body.entity_id))).scalar_one_or_none()
        if not ent or ent.is_archived:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
        # per-company scope
        if ent.company_id:
            from app.core.access import ensure_company_access
            try:
                await ensure_company_access(db, user, ent.company_id)
            except HTTPException as e:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this task")
        c = TaskComment(task_id=ent.id, author_id=user.id, body=body.body.strip(), is_edited=False)
    else:
        from app.models.project import Project
        from app.models.project import ProjectComment
        ent = (await db.execute(select(Project).where(Project.id == body.entity_id))).scalar_one_or_none()
        if not ent or ent.is_archived:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        if ent.company_id:
            from app.core.access import ensure_company_access
            try:
                await ensure_company_access(db, user, ent.company_id)
            except HTTPException:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this project")
        c = ProjectComment(project_id=ent.id, author_id=user.id, body=body.body.strip(), is_edited=False)

    db.add(c)
    await db.flush()

    # Resolve company name for context
    company_name = None
    if ent.company_id:
        from app.models.company import Company
        co = await db.get(Company, ent.company_id)
        if co:
            company_name = co.name_short or co.name_ru

    # Fire @-mention notifications for tagged users
    from app.services.mention_service import notify_mentioned_users
    mentioned_ids = await notify_mentioned_users(
        db, text=c.body,
        actor_id=user.id,
        actor_name=user.full_name or user.email,
        entity_type=body.entity_type,
        entity_id=str(ent.id),
        entity_title=ent.title or "(без названия)",
        company_name=company_name,
        comment_id=str(c.id),
        link_url=f"/{body.entity_type}s/{ent.id}",
    )
    # Fire participant notifications (owner/assignee/prior commenters)
    from app.services.comment_participants_service import notify_comment_participants
    await notify_comment_participants(
        db,
        entity_type=body.entity_type, entity=ent,
        comment_id=c.id, body=c.body,
        actor_id=user.id,
        actor_name=user.full_name or user.email,
        company_name=company_name,
        link_url=f"/{body.entity_type}s/{ent.id}",
        skip_user_ids=mentioned_ids,
    )
    await db.commit()
    log.info("comment-from-tg: %s/%s by %s len=%d", body.entity_type, ent.id, user.email, len(body.body))
    return CommentFromTgOut(ok=True, comment_id=str(c.id))
