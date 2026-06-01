"""Data access for Moderation dashboard / rules / users (read+CRUD).

Does NOT duplicate the queries that live in `app/services/moderation_service.py`
(state machine: gate/apply/approve/reject) — those stay in the core service.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.moderation import (
    ModerationComment,
    ModerationRule,
    ModerationSubmission,
)
from app.models.user import User


class ModerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── overview counts ──────────────────────────────────────────

    async def count_by_status(self, status: str) -> int:
        res = await self.session.execute(
            select(func.count(ModerationSubmission.id))
            .where(ModerationSubmission.status == status)
        )
        return res.scalar() or 0

    async def count_resolved_since(self, since: datetime, *, status_in: Sequence[str]) -> int:
        res = await self.session.execute(
            select(func.count(ModerationSubmission.id))
            .where(and_(
                ModerationSubmission.resolved_at >= since,
                ModerationSubmission.status.in_(status_in),
            ))
        )
        return res.scalar() or 0

    async def avg_resolution_hours(self, *, days_window: int) -> Optional[float]:
        cutoff = datetime.utcnow() - timedelta(days=days_window)
        res = await self.session.execute(
            select(func.avg(
                func.extract("epoch",
                             ModerationSubmission.resolved_at - ModerationSubmission.created_at)
                / 3600.0
            )).where(and_(
                ModerationSubmission.resolved_at.is_not(None),
                ModerationSubmission.resolved_at >= cutoff,
            ))
        )
        v = res.scalar()
        return float(v) if v is not None else None

    async def count_my_pending(self, user_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(ModerationSubmission.id)).where(and_(
                ModerationSubmission.assigned_moderator_id == user_id,
                ModerationSubmission.status.in_(["pending", "under_review"]),
            ))
        )
        return res.scalar() or 0

    async def count_external_users(self) -> int:
        res = await self.session.execute(
            select(func.count(User.id)).where(User.is_external.is_(True))
        )
        return res.scalar() or 0

    async def count_rules(self, *, active_only: bool = False) -> int:
        q = select(func.count(ModerationRule.id))
        if active_only:
            q = q.where(ModerationRule.is_active.is_(True))
        return (await self.session.execute(q)).scalar() or 0

    async def all_rule_moderator_ids(self) -> set[UUID]:
        rows = (await self.session.execute(
            select(ModerationRule.moderator_primary_id, ModerationRule.moderator_coapprover_id)
        )).all()
        out: set[UUID] = set()
        for r in rows:
            if r[0]:
                out.add(r[0])
            if r[1]:
                out.add(r[1])
        return out

    # ─── submission listings ──────────────────────────────────────

    async def list_submissions(
        self,
        *,
        status_in: Optional[list[str]],
        assigned_moderator_id: Optional[UUID],
        proposer_user_id: Optional[UUID],
        target_module: Optional[str],
        page: int,
        per_page: int,
    ) -> tuple[list[ModerationSubmission], int, dict[str, int]]:
        base = select(ModerationSubmission)
        if status_in:
            base = base.where(ModerationSubmission.status.in_(status_in))
        if assigned_moderator_id is not None:
            base = base.where(ModerationSubmission.assigned_moderator_id == assigned_moderator_id)
        if proposer_user_id is not None:
            base = base.where(ModerationSubmission.proposer_user_id == proposer_user_id)
        if target_module:
            base = base.where(ModerationSubmission.target_module == target_module)

        total = (await self.session.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar() or 0

        # Counts by status — for the dashboard, scoped by proposer if applicable
        # (queue uses full picture; my-submissions scopes to proposer)
        cnt_q = select(ModerationSubmission.status, func.count(ModerationSubmission.id))
        if proposer_user_id is not None:
            cnt_q = cnt_q.where(ModerationSubmission.proposer_user_id == proposer_user_id)
        cnt_q = cnt_q.group_by(ModerationSubmission.status)
        counts = {r[0]: r[1] for r in (await self.session.execute(cnt_q)).all()}

        rows = (await self.session.execute(
            base.order_by(ModerationSubmission.created_at.desc())
            .limit(per_page).offset((page - 1) * per_page)
        )).scalars().all()
        return list(rows), total, counts

    async def get_submission(self, submission_id: UUID) -> Optional[ModerationSubmission]:
        return await self.session.get(ModerationSubmission, submission_id)

    # ─── comments ─────────────────────────────────────────────────

    async def list_comments(
        self,
        submission_id: UUID,
        *,
        include_internal: bool,
    ):
        base = select(ModerationComment).where(ModerationComment.submission_id == submission_id)
        if not include_internal:
            base = base.where(ModerationComment.is_internal.is_(False))
        rows = (await self.session.execute(
            base.order_by(ModerationComment.created_at.asc())
        )).scalars().all()
        return list(rows)

    # ─── rules ────────────────────────────────────────────────────

    async def list_rules(self):
        rows = (await self.session.execute(
            select(ModerationRule)
            .order_by(ModerationRule.sort_order.asc(), ModerationRule.created_at.asc())
        )).scalars().all()
        return list(rows)

    async def get_rule(self, rule_id: UUID) -> Optional[ModerationRule]:
        return await self.session.get(ModerationRule, rule_id)

    # ─── moderator / external user listings ───────────────────────

    async def list_owners(self) -> list[UUID]:
        rows = (await self.session.execute(
            select(User.id).where(User.is_owner.is_(True))
        )).all()
        return [r[0] for r in rows]

    async def users_by_ids(self, ids: Sequence[UUID]):
        if not ids:
            return []
        rows = (await self.session.execute(
            select(User).where(User.id.in_(ids)).order_by(User.full_name.asc())
        )).scalars().all()
        return list(rows)

    async def list_external_users(self):
        rows = (await self.session.execute(
            select(User).where(User.is_external.is_(True))
            .order_by(User.full_name.asc())
        )).scalars().all()
        return list(rows)

    async def get_user(self, user_id: UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
