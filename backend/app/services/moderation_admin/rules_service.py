"""Moderation Rules CRUD + user flags + comments-listing helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.moderation import ModerationRule
from app.schemas.moderation import (
    CommentRead, RuleCreate, RuleListResponse, RuleRead, RuleUpdate,
)
from app.uow.ports import UnitOfWorkABC


def _normalize_conditions(data: dict) -> dict:
    """Convert trigger_conditions list of pydantic models → plain dicts."""
    if data.get("trigger_conditions"):
        data["trigger_conditions"] = [
            c if isinstance(c, dict) else c.model_dump()
            for c in data["trigger_conditions"]
        ]
    return data


class ModerationRulesService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def list_rules(self) -> RuleListResponse:
        async with self.uow:
            rows = await self.uow.moderation.list_rules()
        return RuleListResponse(
            items=[RuleRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    async def get_rule(self, rule_id: UUID) -> RuleRead:
        async with self.uow:
            r = await self.uow.moderation.get_rule(rule_id)
        if not r:
            raise HTTPException(404, "Not found")
        return RuleRead.model_validate(r)

    async def create_rule(self, body: RuleCreate, *, created_by_id: UUID) -> RuleRead:
        now = datetime.now(timezone.utc)
        data = _normalize_conditions(body.model_dump(exclude_unset=True))
        async with self.uow:
            r = ModerationRule(
                created_at=now, updated_at=now,
                created_by_id=created_by_id, version=1, **data,
            )
            self.uow.moderation.add(r)
            await self.uow.moderation.flush()
            await self.uow.moderation.refresh(r)
            return RuleRead.model_validate(r)

    async def update_rule(self, rule_id: UUID, body: RuleUpdate) -> RuleRead:
        data = _normalize_conditions(body.model_dump(exclude_unset=True))
        async with self.uow:
            r = await self.uow.moderation.get_rule(rule_id)
            if not r:
                raise HTTPException(404, "Not found")
            for k, v in data.items():
                setattr(r, k, v)
            r.version += 1
            r.updated_at = datetime.now(timezone.utc)
            await self.uow.moderation.flush()
            await self.uow.moderation.refresh(r)
            return RuleRead.model_validate(r)

    async def delete_rule(self, rule_id: UUID) -> None:
        async with self.uow:
            r = await self.uow.moderation.get_rule(rule_id)
            if not r:
                raise HTTPException(404, "Not found")
            await self.uow.moderation.delete(r)
            await self.uow.moderation.flush()

    async def toggle_rule(self, rule_id: UUID) -> RuleRead:
        async with self.uow:
            r = await self.uow.moderation.get_rule(rule_id)
            if not r:
                raise HTTPException(404, "Not found")
            r.is_active = not r.is_active
            r.updated_at = datetime.now(timezone.utc)
            await self.uow.moderation.flush()
            await self.uow.moderation.refresh(r)
            return RuleRead.model_validate(r)

    # ─── user flags (external / bypass) ───────────────────────────

    async def patch_user_flags(self, user_id: UUID, body: dict) -> dict:
        async with self.uow:
            u = await self.uow.moderation.get_user(user_id)
            if not u:
                raise HTTPException(404, "Not found")
            for f in ("is_external", "bypass_moderation"):
                if f in body and isinstance(body[f], bool):
                    setattr(u, f, body[f])
            if "external_org_name" in body:
                u.external_org_name = body["external_org_name"]
            await self.uow.moderation.flush()
            await self.uow.moderation.refresh(u)
            return {
                "id": str(u.id),
                "is_external": u.is_external,
                "bypass_moderation": u.bypass_moderation,
                "external_org_name": u.external_org_name,
            }

    # ─── comments listing (read-only) ─────────────────────────────

    async def list_comments(
        self,
        submission_id: UUID,
        *,
        include_internal: bool,
    ) -> list[CommentRead]:
        async with self.uow:
            rows = await self.uow.moderation.list_comments(
                submission_id, include_internal=include_internal,
            )
        return [CommentRead.model_validate(r) for r in rows]

    # ─── submission lookups for route's access checks ─────────────

    async def get_submission_for_access(self, submission_id: UUID):
        async with self.uow:
            return await self.uow.moderation.get_submission(submission_id)
