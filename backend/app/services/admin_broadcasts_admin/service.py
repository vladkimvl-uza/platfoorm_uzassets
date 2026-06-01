"""Use cases for Admin Broadcasts (Pack 11.2).

Naming `admin_broadcasts_admin/` to coexist with existing core
`app/services/admin_broadcast_service.py` (compute_next_run_at,
preview_recipients, dispatch_template, acknowledge_notification,
analytics_for_template) — that module owns the dispatch engine.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.admin_broadcast import AdminBroadcastTemplate
from app.schemas.admin_broadcast import (
    AckRead,
    AckSubmit,
    BroadcastAnalytics,
    DispatchListResponse,
    DispatchRead,
    RecipientPreview,
    StickyNotification,
    TemplateCreate,
    TemplateListItem,
    TemplateListResponse,
    TemplateRead,
    TemplateUpdate,
)
from app.services import admin_broadcast_service as core
from app.uow.ports import UnitOfWorkABC


def _normalize_dict_fields(data: dict, fields: tuple[str, ...]) -> dict:
    for field in fields:
        v = data.get(field)
        if v is not None:
            data[field] = v if isinstance(v, dict) else v.model_dump()
    return data


class AdminBroadcastsService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── template CRUD ────────────────────────────────────────────

    async def list_templates(
        self, *, is_active: Optional[bool],
    ) -> TemplateListResponse:
        async with self.uow:
            rows = await self.uow.admin_broadcasts.list_templates(is_active=is_active)
        return TemplateListResponse(
            items=[TemplateListItem.model_validate(r) for r in rows],
            total=len(rows),
        )

    async def get_template(self, template_id: UUID) -> TemplateRead:
        async with self.uow:
            t = await self.uow.admin_broadcasts.get_template(template_id)
            if not t:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            return TemplateRead.model_validate(t)

    async def create_template(
        self, body: TemplateCreate, *, created_by_id: UUID,
    ) -> TemplateRead:
        now = datetime.now(UTC)
        data = _normalize_dict_fields(
            body.model_dump(exclude_unset=True),
            ("schedule_config", "target_filter_expr"),
        )
        async with self.uow:
            r = self.uow.admin_broadcasts
            t = AdminBroadcastTemplate(
                created_at=now, updated_at=now,
                created_by_id=created_by_id, **data,
            )
            t.next_run_at = core.compute_next_run_at(t, after=now)
            r.add(t)
            await r.flush()
            await r.refresh(t)
            return TemplateRead.model_validate(t)

    async def update_template(
        self, template_id: UUID, body: TemplateUpdate,
    ) -> TemplateRead:
        data = _normalize_dict_fields(
            body.model_dump(exclude_unset=True),
            ("schedule_config", "target_filter_expr"),
        )
        async with self.uow:
            r = self.uow.admin_broadcasts
            t = await r.get_template(template_id)
            if not t:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            for k, v in data.items():
                setattr(t, k, v)
            t.updated_at = datetime.now(UTC)
            t.next_run_at = core.compute_next_run_at(t, after=t.updated_at)
            await r.flush()
            await r.refresh(t)
            return TemplateRead.model_validate(t)

    async def delete_template(self, template_id: UUID) -> None:
        async with self.uow:
            r = self.uow.admin_broadcasts
            t = await r.get_template(template_id)
            if not t:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            await r.delete(t)
            await r.flush()

    async def toggle_template(self, template_id: UUID) -> TemplateRead:
        async with self.uow:
            r = self.uow.admin_broadcasts
            t = await r.get_template(template_id)
            if not t:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            t.is_active = not t.is_active
            t.updated_at = datetime.now(UTC)
            t.next_run_at = (
                core.compute_next_run_at(t, after=t.updated_at)
                if t.is_active else None
            )
            await r.flush()
            await r.refresh(t)
            return TemplateRead.model_validate(t)

    # ─── preview / send-now / test-on-self ────────────────────────

    async def preview_recipients(self, template_id: UUID) -> RecipientPreview:
        async with self.uow:
            r = self.uow.admin_broadcasts
            t = await r.get_template(template_id)
            if not t:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            res = await core.preview_recipients(self.uow._session, t)  # type: ignore[attr-defined]
        return RecipientPreview(**res)

    async def send_now(
        self, template_id: UUID, *, triggered_by_id: UUID,
    ) -> DispatchRead:
        async with self.uow:
            r = self.uow.admin_broadcasts
            t = await r.get_template(template_id)
            if not t:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            d = await core.dispatch_template(
                self.uow._session,  # type: ignore[attr-defined]
                template=t, triggered_by_id=triggered_by_id, trigger="manual",
            )
            return DispatchRead.model_validate(d)

    async def test_on_self(
        self, template_id: UUID, *, user_id: UUID,
    ) -> DispatchRead:
        """Send to caller only. Temporarily override targeting fields."""
        async with self.uow:
            r = self.uow.admin_broadcasts
            t = await r.get_template(template_id)
            if not t:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            saved = {
                "target_all": t.target_all,
                "target_user_ids": t.target_user_ids,
                "target_group_codes": t.target_group_codes,
                "target_role_codes": t.target_role_codes,
                "target_filter_expr": t.target_filter_expr,
            }
            t.target_all = False
            t.target_user_ids = [str(user_id)]
            t.target_group_codes = None
            t.target_role_codes = None
            t.target_filter_expr = None
            try:
                d = await core.dispatch_template(
                    self.uow._session,  # type: ignore[attr-defined]
                    template=t, triggered_by_id=user_id, trigger="manual",
                )
            finally:
                for k, v in saved.items():
                    setattr(t, k, v)
                await r.flush()
        return DispatchRead.model_validate(d)

    # ─── dispatches + analytics ───────────────────────────────────

    async def list_dispatches(self, template_id: UUID) -> DispatchListResponse:
        async with self.uow:
            rows = await self.uow.admin_broadcasts.list_dispatches_for_template(
                template_id, limit=100,
            )
        return DispatchListResponse(
            items=[DispatchRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    async def analytics(self, template_id: UUID) -> BroadcastAnalytics:
        async with self.uow:
            r = self.uow.admin_broadcasts
            t = await r.get_template(template_id)
            if not t:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            res = await core.analytics_for_template(
                self.uow._session, t,  # type: ignore[attr-defined]
            )
        return BroadcastAnalytics(**res)

    # ─── recipient-facing ────────────────────────────────────────

    async def my_sticky(self, user_id: UUID) -> list[StickyNotification]:
        async with self.uow:
            rows = await self.uow.admin_broadcasts.list_sticky_for_user(user_id)
        return [StickyNotification.model_validate(r) for r in rows]

    async def acknowledge(
        self,
        notification_id: UUID,
        body: AckSubmit,
        *,
        user,
    ) -> AckRead:
        async with self.uow:
            r = self.uow.admin_broadcasts
            n = await r.get_notification(notification_id)
            if not n:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
            try:
                a = await core.acknowledge_notification(
                    self.uow._session,  # type: ignore[attr-defined]
                    notification=n, user=user,
                    response_text=body.response_text,
                    response_value=body.response_value,
                    response_file=body.response_file,
                )
            except PermissionError as e:
                raise HTTPException(http_status.HTTP_403_FORBIDDEN, str(e))
        return AckRead.model_validate(a)
