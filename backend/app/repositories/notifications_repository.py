"""Data access for Notification feed / preferences / single-lookup.

Does NOT duplicate the queries in `app/services/notifications_service.py`
(notify, mark_read, mark_all_read, archive, broadcast, unread_count) —
those stay in the core service used by all other modules.
"""
from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationPreference


class NotificationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── feed ─────────────────────────────────────────────────────

    async def list_feed(
        self,
        *,
        user_id: UUID,
        unread_only: bool,
        types: Optional[Sequence[str]],
        priorities: Optional[Sequence[str]],
        include_archived: bool,
        page: int,
        per_page: int,
    ) -> tuple[list[Notification], int]:
        base = select(Notification).where(Notification.recipient_user_id == user_id)
        if not include_archived:
            base = base.where(Notification.is_archived.is_(False))
        if unread_only:
            base = base.where(Notification.is_read.is_(False))
        if types:
            base = base.where(Notification.type.in_(types))
        if priorities:
            base = base.where(Notification.priority.in_(priorities))
        total = (await self.session.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar() or 0
        rows = (await self.session.execute(
            base.order_by(Notification.created_at.desc())
            .limit(per_page).offset((page - 1) * per_page)
        )).scalars().all()
        return list(rows), total

    async def get_for_user(
        self,
        notification_id: UUID,
        *,
        user_id: UUID,
    ) -> Optional[Notification]:
        res = await self.session.execute(
            select(Notification).where(and_(
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
            ))
        )
        return res.scalar_one_or_none()

    # ─── preferences ──────────────────────────────────────────────

    async def list_preferences(self, user_id: UUID):
        rows = (await self.session.execute(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
        )).scalars().all()
        return list(rows)

    async def get_preference(
        self,
        user_id: UUID,
        notification_type: str,
    ) -> Optional[NotificationPreference]:
        res = await self.session.execute(
            select(NotificationPreference).where(and_(
                NotificationPreference.user_id == user_id,
                NotificationPreference.notification_type == notification_type,
            ))
        )
        return res.scalar_one_or_none()

    def add(self, obj) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()
