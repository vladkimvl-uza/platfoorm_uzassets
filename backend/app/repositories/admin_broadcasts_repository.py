"""Data access for Admin Broadcasts (Pack 11.2).

Mostly thin wrappers — heavy lifting in app/services/admin_broadcast_service.py.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_broadcast import (
    AdminBroadcastDispatch,
    AdminBroadcastTemplate,
)
from app.models.notification import Notification


class AdminBroadcastsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── templates ────────────────────────────────────────────────

    async def list_templates(self, *, is_active: Optional[bool]):
        q = select(AdminBroadcastTemplate)
        if is_active is not None:
            q = q.where(AdminBroadcastTemplate.is_active.is_(is_active))
        q = q.order_by(AdminBroadcastTemplate.created_at.desc())
        return list((await self.session.execute(q)).scalars().all())

    async def get_template(self, template_id: UUID) -> Optional[AdminBroadcastTemplate]:
        return await self.session.get(AdminBroadcastTemplate, template_id)

    # ─── dispatches ───────────────────────────────────────────────

    async def list_dispatches_for_template(self, template_id: UUID, *, limit: int = 100):
        res = await self.session.execute(
            select(AdminBroadcastDispatch)
            .where(AdminBroadcastDispatch.template_id == template_id)
            .order_by(AdminBroadcastDispatch.dispatched_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())

    # ─── sticky notifications (recipient view) ────────────────────

    async def list_sticky_for_user(self, user_id: UUID):
        res = await self.session.execute(
            select(Notification).where(and_(
                Notification.recipient_user_id == user_id,
                Notification.is_sticky.is_(True),
                Notification.acknowledged_at.is_(None),
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.now(UTC),
                ),
                Notification.is_archived.is_(False),
            )).order_by(Notification.created_at.asc())
        )
        return list(res.scalars().all())

    async def get_notification(self, notification_id: UUID) -> Optional[Notification]:
        return await self.session.get(Notification, notification_id)

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
