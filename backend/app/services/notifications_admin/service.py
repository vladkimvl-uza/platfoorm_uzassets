"""Read-only feed/preferences/types use cases for Notifications.

Naming: `notifications_admin/` to coexist with the existing core
`app/services/notifications_service.py` (notify/broadcast/mark_read/
archive/ws_manager) — that module is used by all other modules.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.notification import NOTIFICATION_TYPES, NotificationPreference
from app.schemas.notification import (
    NotificationListResponse,
    NotificationPreferenceRead,
    NotificationRead,
    NotificationTypeInfo,
    NotificationTypesResponse,
)
from app.uow.ports import UnitOfWorkABC

CATEGORY_MAP = {
    "moderation": "Модерация",
    "mention":    "Взаимодействие",
    "assignment": "Взаимодействие",
    "comment":    "Взаимодействие",
    "deadline":   "Дедлайны",
    "kpi":        "Метрики",
    "audit":      "Безопасность",
    "rbac":       "Безопасность",
    "system":     "Система",
    "data":       "Система",
    "report":     "Система",
}


class NotificationsQueryService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def feed(
        self,
        *,
        user_id: UUID,
        unread_only: bool,
        types: Optional[Sequence[str]],
        priorities: Optional[Sequence[str]],
        include_archived: bool,
        page: int,
        per_page: int,
    ) -> NotificationListResponse:
        async with self.uow:
            rows, total = await self.uow.notifications.list_feed(
                user_id=user_id,
                unread_only=unread_only, types=types, priorities=priorities,
                include_archived=include_archived,
                page=page, per_page=per_page,
            )
            # Reuse core service to keep unread_count formula in one place
            from app.services.notifications_service import unread_count
            uc = await unread_count(self.uow._session, user_id)  # type: ignore[attr-defined]

        return NotificationListResponse(
            items=[NotificationRead.model_validate(r) for r in rows],
            total=total, unread_count=uc,
            page=page, per_page=per_page,
        )

    async def get_one(self, notification_id: UUID, *, user_id: UUID) -> NotificationRead:
        async with self.uow:
            n = await self.uow.notifications.get_for_user(notification_id, user_id=user_id)
        if not n:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Notification not found")
        return NotificationRead.model_validate(n)

    async def list_preferences(self, user_id: UUID) -> list[NotificationPreferenceRead]:
        async with self.uow:
            rows = await self.uow.notifications.list_preferences(user_id)
        return [NotificationPreferenceRead.model_validate(r) for r in rows]

    async def upsert_preferences(
        self,
        *,
        user_id: UUID,
        preferences: list,
    ) -> list[NotificationPreferenceRead]:
        async with self.uow:
            for p in preferences:
                existing = await self.uow.notifications.get_preference(
                    user_id, p.notification_type,
                )
                if existing:
                    if p.channels is not None:
                        existing.channels = p.channels
                    if p.is_muted is not None:
                        existing.is_muted = p.is_muted
                    if p.mute_until is not None:
                        existing.mute_until = p.mute_until
                    if p.digest_mode is not None:
                        existing.digest_mode = p.digest_mode
                else:
                    self.uow.notifications.add(NotificationPreference(
                        user_id=user_id,
                        notification_type=p.notification_type,
                        channels=p.channels or {"in_app": True},
                        is_muted=p.is_muted or False,
                        mute_until=p.mute_until,
                        digest_mode=p.digest_mode or "none",
                    ))
            await self.uow.notifications.flush()
            rows = await self.uow.notifications.list_preferences(user_id)
        return [NotificationPreferenceRead.model_validate(r) for r in rows]

    @staticmethod
    def list_types() -> NotificationTypesResponse:
        items = []
        for code, meta in NOTIFICATION_TYPES.items():
            prefix = code.split(".", 1)[0]
            items.append(NotificationTypeInfo(
                code=code, label=meta["label"], priority=meta["priority"],
                category=CATEGORY_MAP.get(prefix, "Прочее"),
            ))
        cats = sorted({i.category for i in items})
        return NotificationTypesResponse(types=items, categories=cats)
