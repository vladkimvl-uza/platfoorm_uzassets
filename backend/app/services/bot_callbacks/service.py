"""Use cases for Telegram bot callbacks.

Core services NOT touched:
- `moderation_service` (approve/reject)
- `mfa_service` (confirm_link_telegram, _hash_sha256, revoke_active_challenge)
- `audit_service`, `mention_service`, `comment_participants_service`
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.project import ProjectComment
from app.models.task import TaskComment
from app.uow.ports import UnitOfWorkABC

log = logging.getLogger(__name__)


class BotCallbacksService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── moderation approve/reject ────────────────────────────────

    async def moderation_decision(
        self,
        *,
        decision: str,            # 'approve' | 'reject'
        chat_id: int,
        submission_id: str,
        note: Optional[str],
        default_reject_note: str = "Отклонено из Telegram",
    ) -> dict:
        from app.services import moderation_service
        async with self.uow:
            user = await self.uow.bot_callbacks.find_user_by_chat_id(chat_id)
            if user is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Telegram аккаунт не привязан",
                )
            try:
                sub_uuid = UUID(submission_id)
            except (ValueError, TypeError):
                raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid submission_id")
            sub_row = await self.uow.bot_callbacks.get_submission(sub_uuid)
            if sub_row is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Submission not found")
            session = self.uow._session  # type: ignore[attr-defined]
            try:
                if decision == "approve":
                    sub = await moderation_service.approve(
                        session, sub=sub_row, user=user, note=note,
                    )
                    detail = "Принято"
                else:
                    sub = await moderation_service.reject(
                        session, sub=sub_row, user=user,
                        note=note or default_reject_note,
                    )
                    detail = "Отклонено"
            except HTTPException:
                raise
            except PermissionError as e:
                raise HTTPException(http_status.HTTP_403_FORBIDDEN, str(e))
            except ValueError as e:
                raise HTTPException(http_status.HTTP_409_CONFLICT, str(e))
            except Exception as e:
                log.warning("bot moderation %s failed: %s", decision, e, exc_info=True)
                raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(e))

            return {
                "ok": True, "detail": detail,
                "submission_id": str(sub.id),
                "new_status": (
                    str(getattr(sub.status, "value", sub.status))
                    if hasattr(sub, "status") else None
                ),
            }

    # ─── module-specific decision (kpi/procurement) ───────────────

    async def module_submission_decision(
        self,
        *,
        module: str, submission_id: str, chat_id: int,
        decision: str, note: Optional[str],
    ) -> dict:
        from app.services import moderation_service
        async with self.uow:
            user = await self.uow.bot_callbacks.find_user_by_chat_id(chat_id)
            if user is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Telegram аккаунт не привязан",
                )
            try:
                sub_uuid = UUID(submission_id)
            except (ValueError, TypeError):
                raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid submission_id")
            sub_row = await self.uow.bot_callbacks.get_submission(sub_uuid)
            if sub_row is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Submission not found")

            sub_module = getattr(sub_row, "module", None)
            sub_module_value = getattr(sub_module, "value", sub_module)
            if sub_module_value and str(sub_module_value).lower() != module:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Submission принадлежит модулю «{sub_module_value}», ожидался «{module}»",
                )

            session = self.uow._session  # type: ignore[attr-defined]
            try:
                if decision == "approve":
                    sub = await moderation_service.approve(session, sub=sub_row, user=user, note=note)
                    detail = "Утверждено"
                elif decision == "reject":
                    sub = await moderation_service.reject(
                        session, sub=sub_row, user=user,
                        note=note or f"Отклонено через Telegram ({module})",
                    )
                    detail = "Отклонено"
                else:
                    raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid decision")
            except HTTPException:
                raise
            except PermissionError as e:
                raise HTTPException(http_status.HTTP_403_FORBIDDEN, str(e))
            except ValueError as e:
                raise HTTPException(http_status.HTTP_409_CONFLICT, str(e))
            except Exception as e:
                log.warning("module decision failed (%s/%s): %s", module, decision, e, exc_info=True)
                raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(e))

            new_status = (
                str(getattr(sub.status, "value", sub.status))
                if hasattr(sub, "status") else None
            )
            return {
                "ok": True, "detail": detail,
                "submission_id": str(sub.id),
                "new_status": new_status,
            }

    # ─── tg link confirm/deny ─────────────────────────────────────

    async def tg_link_confirm(
        self, *, token: str, chat_id: int, username: Optional[str],
    ) -> dict:
        from app.services import mfa_service
        from app.services.mfa_service import _hash_sha256
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            user = await mfa_service.confirm_link_telegram(
                session, token=token, chat_id=chat_id, username=username or None,
            )
            if user is None:
                # Check if token exists at all (404) or expired (410)
                hashed = _hash_sha256(token)
                existing = await self.uow.bot_callbacks.find_user_by_link_token_hash(hashed)
                if existing is None:
                    raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Токен не найден")
                else:
                    raise HTTPException(http_status.HTTP_410_GONE, "Токен истёк")
        return {"ok": True, "detail": "linked", "email": user.email}

    async def tg_link_deny(self, *, token: str) -> dict:
        from app.services.mfa_service import _hash_sha256
        hashed = _hash_sha256(token)
        async with self.uow:
            user = await self.uow.bot_callbacks.find_user_by_link_token_hash(hashed)
            if user is not None:
                user.telegram_link_token_hashed = None
                user.telegram_link_token_expires_at = None
                await self.uow.bot_callbacks.flush()
        return {"ok": True, "detail": "token invalidated"}

    # ─── MFA report «Это не я» ────────────────────────────────────

    async def mfa_report(self, *, chat_id: int, mfa_token: Optional[str]) -> dict:
        async with self.uow:
            user = await self.uow.bot_callbacks.find_user_by_chat_id(chat_id)
            if user is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Telegram аккаунт не привязан",
                )
            session = self.uow._session  # type: ignore[attr-defined]

            try:
                from app.services import audit_service
                await audit_service.write_event(
                    session,
                    actor_id=user.id, actor_email=user.email,
                    actor_role=(user.roles[0].code if user.roles else None),
                    action="security_flag", module="auth",
                    entity_type="mfa_attempt",
                    entity_id=(mfa_token or "")[:64] or None,
                    notes="Пользователь нажал «Это не я» в Telegram под MFA-кодом",
                    meta={"source": "telegram_inline", "mfa_token": (mfa_token or "")[:64]},
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
                        await revoke(session, user=user, token=mfa_token or "")
                    except Exception:
                        pass
            except Exception:
                pass

        return {"ok": True, "detail": "reported"}

    # ─── comment-from-tg ──────────────────────────────────────────

    async def comment_from_tg(
        self, *,
        chat_id: int, entity_type: str, entity_id: str, body: str,
    ) -> dict:
        if entity_type not in ("task", "project"):
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "entity_type must be 'task' or 'project'",
            )
        body = (body or "").strip()
        if not body:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "body required")

        async with self.uow:
            r = self.uow.bot_callbacks
            user = await r.find_user_by_chat_id(chat_id)
            if not user:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Telegram chat not linked")
            if not user.is_active:
                raise HTTPException(http_status.HTTP_403_FORBIDDEN, "User is inactive")

            session = self.uow._session  # type: ignore[attr-defined]

            if entity_type == "task":
                ent = await r.get_task(entity_id)
                if not ent or ent.is_archived:
                    raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")
                if ent.company_id:
                    from app.core.access import ensure_company_access
                    try:
                        await ensure_company_access(session, user, ent.company_id)
                    except HTTPException:
                        raise HTTPException(
                            http_status.HTTP_403_FORBIDDEN, "No access to this task",
                        )
                c = TaskComment(
                    task_id=ent.id, author_id=user.id,
                    body=body, is_edited=False,
                )
            else:
                ent = await r.get_project(entity_id)
                if not ent or ent.is_archived:
                    raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
                if ent.company_id:
                    from app.core.access import ensure_company_access
                    try:
                        await ensure_company_access(session, user, ent.company_id)
                    except HTTPException:
                        raise HTTPException(
                            http_status.HTTP_403_FORBIDDEN, "No access to this project",
                        )
                c = ProjectComment(
                    project_id=ent.id, author_id=user.id,
                    body=body, is_edited=False,
                )

            r.add(c)
            await r.flush()

            company_name = None
            if ent.company_id:
                co = await r.get_company(ent.company_id)
                if co:
                    company_name = co.name_short or co.name_ru

            link_url = f"/{entity_type}s/{ent.id}"
            from app.services.mention_service import notify_mentioned_users
            mentioned_ids = await notify_mentioned_users(
                session, text=c.body,
                actor_id=user.id,
                actor_name=user.full_name or user.email,
                entity_type=entity_type, entity_id=str(ent.id),
                entity_title=ent.title or "(без названия)",
                company_id=getattr(ent, "company_id", None),
                company_name=company_name,
                comment_id=str(c.id),
                link_url=link_url,
            )
            from app.services.comment_participants_service import notify_comment_participants
            await notify_comment_participants(
                session,
                entity_type=entity_type, entity=ent,
                comment_id=c.id, body=c.body,
                actor_id=user.id,
                actor_name=user.full_name or user.email,
                company_name=company_name,
                link_url=link_url,
                skip_user_ids=mentioned_ids,
            )

            comment_id_str = str(c.id)
            log.info(
                "comment-from-tg: %s/%s by %s len=%d",
                entity_type, ent.id, user.email, len(body),
            )

        return {"ok": True, "comment_id": comment_id_str}
