"""Read-only use cases for Moderation dashboard.

Naming: `moderation_admin/` (not `moderation/`) to avoid colliding with the
existing core `app/services/moderation_service.py` which owns the
gate_or_apply / approve / reject state machine.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from app.schemas.moderation import (
    ModerationOverview,
    SubmissionListItem,
    SubmissionListResponse,
)
from app.uow.ports import UnitOfWorkABC


class ModerationQueryService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def overview(self, *, user_id: UUID) -> ModerationOverview:
        today = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        async with self.uow:
            r = self.uow.moderation
            pending     = await r.count_by_status("pending")
            under_rev   = await r.count_by_status("under_review")
            resolved    = await r.count_resolved_since(today, status_in=["approved", "rejected"])
            approved    = await r.count_resolved_since(today, status_in=["approved"])
            rejected    = await r.count_resolved_since(today, status_in=["rejected"])
            avg_h       = await r.avg_resolution_hours(days_window=7)
            my_pending  = await r.count_my_pending(user_id)
            external    = await r.count_external_users()
            rules_act   = await r.count_rules(active_only=True)
            rules_total = await r.count_rules()
            # Счётчик на вкладке «Модераторы» брался из полей правил, а
            # конструктор правил удалён 03.08.2026 — таблица пустая, и вкладка
            # показывала 0 при непустом списке. Источник теперь тот же, что у
            # самого списка.
            from app.services import moderation_authority
            mod_ids     = await moderation_authority.moderator_ids(self.uow.session)

        return ModerationOverview(
            pending=pending, under_review=under_rev,
            resolved_today=resolved,
            approved_today=approved,
            rejected_today=rejected,
            avg_resolution_hours=avg_h,
            my_pending_count=my_pending,
            moderators_count=len(mod_ids),
            external_users_count=external,
            rules_active_count=rules_act,
            rules_total_count=rules_total,
        )

    async def list_queue(
        self,
        *,
        status_in: Optional[list[str]],
        assigned_to: Optional[str],
        module: Optional[str],
        proposer_user_id: Optional[UUID],
        page: int,
        per_page: int,
        actor_id: UUID,
    ) -> SubmissionListResponse:
        # Resolve assigned_to ("me" -> actor_id, "<uuid>" -> UUID)
        assigned_moderator_id: Optional[UUID] = None
        if assigned_to == "me":
            assigned_moderator_id = actor_id
        elif assigned_to:
            assigned_moderator_id = UUID(assigned_to)

        async with self.uow:
            rows, total, counts = await self.uow.moderation.list_submissions(
                status_in=status_in,
                assigned_moderator_id=assigned_moderator_id,
                proposer_user_id=proposer_user_id,
                target_module=module,
                page=page, per_page=per_page,
            )
        return SubmissionListResponse(
            items=[SubmissionListItem.model_validate(r) for r in rows],
            total=total, counts_by_status=counts,
            page=page, per_page=per_page,
        )

    async def list_my_submissions(
        self,
        *,
        actor_id: UUID,
        status_in: Optional[list[str]],
        page: int,
        per_page: int,
    ) -> SubmissionListResponse:
        async with self.uow:
            rows, total, counts = await self.uow.moderation.list_submissions(
                status_in=status_in,
                assigned_moderator_id=None,
                proposer_user_id=actor_id,
                target_module=None,
                page=page, per_page=per_page,
            )
        return SubmissionListResponse(
            items=[SubmissionListItem.model_validate(r) for r in rows],
            total=total, counts_by_status=counts,
            page=page, per_page=per_page,
        )

    # ─── moderator / external users (for sub-tabs) ────────────────

    async def list_moderators(self) -> list[dict]:
        """Модераторы = владельцы + держатели права moderation.review.

        Раньше список собирался из полей правил (primary/co-approver), поэтому
        после удаления конструктора правил он бы опустел. Источник теперь один —
        RBAC, тот же, что открывает саму очередь.
        """
        from app.services import moderation_authority
        async with self.uow:
            rows = await moderation_authority.moderator_ids(self.uow.session)
            users = await self.uow.moderation.users_by_ids(list(rows))
            # Снять можно с любого, включая владельца, — но владельца снимает
            # только владелец. Фронт по этому признаку решает, показывать ли
            # кнопку, чтобы не предлагать действие, которое вернёт 403.
            owner_only = {str(u.id) for u in users if u.is_owner}
        return [
            {
                "id": str(u.id), "email": u.email, "full_name": u.full_name,
                "is_owner": u.is_owner, "is_active": u.is_active,
                "job_title": u.job_title, "department": u.department,
                "owner_only_removal": str(u.id) in owner_only,
            }
            for u in users
        ]

    async def list_removed_moderators(self) -> list[dict]:
        """Кого сняли с модерации персональным отзывом права.

        Нужен, чтобы снятие было обратимым: вернуть право сеткой «Доступ к
        модулям» нельзя (кода `moderation.review` в ней нет), и без этого
        списка человек исчезал бы со страницы навсегда.
        """
        from sqlalchemy import text as _text

        from app.services import moderation_authority
        async with self.uow:
            rows = (await self.uow.session.execute(_text("""
                SELECT g.user_id, g.created_at
                  FROM user_permission_grant g
                 WHERE g.permission_code = :review_code
                   AND g.grant_type = :gtype_deny
                   AND (g.expires_at IS NULL OR g.expires_at > now())
                 ORDER BY g.created_at DESC
            """), moderation_authority.PARAMS)).all()
            by_id = {str(uid): created for uid, created in rows}
            users = await self.uow.moderation.users_by_ids(
                [uid for uid, _ in rows]
            )
        return [
            {
                "id": str(u.id), "email": u.email, "full_name": u.full_name,
                "is_owner": u.is_owner, "is_active": u.is_active,
                "job_title": u.job_title, "department": u.department,
                "removed_at": (
                    by_id.get(str(u.id)).isoformat()
                    if by_id.get(str(u.id)) else None
                ),
            }
            for u in users
        ]

    async def list_external_users(self) -> list[dict]:
        async with self.uow:
            users = await self.uow.moderation.list_external_users()
        return [
            {
                "id": str(u.id), "email": u.email, "full_name": u.full_name,
                "is_external": u.is_external,
                "bypass_moderation": u.bypass_moderation,
                "external_org_name": u.external_org_name,
                "moderation_bypass_modules": u.moderation_bypass_modules or [],
                "is_active": u.is_active,
                "job_title": u.job_title,
            }
            for u in users
        ]
