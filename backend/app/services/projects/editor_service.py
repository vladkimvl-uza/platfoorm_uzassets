"""Mutation use cases for Projects domain."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.project import Project
from app.schemas.project import (
    ProjectCreate,
    ProjectDetail,
    ProjectUpdate,
)
from app.services.projects._helpers import (
    EXTRA_FIELDS,
    project_to_brief,
    serialize_comment,
)
from app.uow.ports import UnitOfWorkABC


class ProjectsEditorService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── create ───────────────────────────────────────────────────

    async def create_project(
        self,
        payload: ProjectCreate,
        *,
        creator_id: UUID,
    ) -> tuple[Project, dict[str, Any]]:
        raw = payload.model_dump(exclude_none=True)
        extra: dict = {}
        for k in list(raw.keys()):
            if k in EXTRA_FIELDS:
                extra[k] = raw.pop(k)
        if extra.get("direction"):
            from app.core.direction_normalize import normalize_direction
            extra["direction"] = normalize_direction(extra["direction"])

        async with self.uow:
            p = Project(**raw, extra=(extra or None), creator_id=creator_id)
            self.uow.projects.add(p)
            await self.uow.projects.flush()
            await self.uow.projects.refresh(p)
            pid = p.id

        return await self._fetch_and_hydrate(pid), {}

    # ─── update ───────────────────────────────────────────────────

    async def update_project(
        self,
        project_id: UUID,
        payload: ProjectUpdate,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> tuple[Project, dict[str, Any]]:
        """Returns (project, info) where info contains side-effect signals."""
        changes = payload.model_dump(exclude_unset=True)
        extra_updates = {k: changes.pop(k) for k in list(changes.keys()) if k in EXTRA_FIELDS}
        description_changed = "description" in changes and changes["description"]

        async with self.uow:
            p = await self.uow.projects.get(project_id)
            if not p:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")

            if scope_company_ids is not None:
                if p.company_id is None or p.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")
                new_company_id = changes.get("company_id")
                if new_company_id is not None and new_company_id not in scope_company_ids:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        "Cannot reassign project to a company outside your allowed list",
                    )

            for field, value in changes.items():
                setattr(p, field, value)

            # Статус проекта с задачами — производный (решение владельца
            # 05.08.2026): выводится из статусов задач. Ручную установку не
            # отклоняем ошибкой, а сразу пересчитываем поверх — ответ вернёт
            # фактический статус, и редактор его покажет. У проекта без задач
            # статус остаётся ручным (recompute вернёт None и ничего не тронет).
            if "status" in changes:
                from app.services.tasks.project_status import (
                    recompute_project_status,
                )
                await recompute_project_status(self.uow.session, p.id)

            if extra_updates:
                from app.core.direction_normalize import normalize_direction
                merged = dict(p.extra or {})
                for k, v in extra_updates.items():
                    if v is None:
                        merged.pop(k, None)
                    elif k == "direction":
                        merged[k] = normalize_direction(v)
                    else:
                        merged[k] = v
                p.extra = merged or None

            if changes.get("status") == "done" and not p.completed_at:
                p.completed_at = datetime.now(UTC)
            if "status" in changes and changes["status"] != "done":
                p.completed_at = None

            await self.uow.projects.flush()
            await self.uow.projects.refresh(p)
            pid = p.id
            title = p.title or "(без названия)"

        info = {
            "description_changed": description_changed,
            "description_text": changes.get("description"),
            "project_id": pid,
            "project_title": title,
        }
        return p, info

    # ─── toggle / archive ─────────────────────────────────────────

    async def toggle_result(
        self,
        project_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> dict[str, Any]:
        async with self.uow:
            p = await self.uow.projects.get(project_id)
            if not p:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
            if scope_company_ids is not None:
                if p.company_id is None or p.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")
            old = p.result_at
            p.result_at = None if old else datetime.now(UTC)
            await self.uow.projects.flush()
            result_at = p.result_at
        return {"result_at": result_at.isoformat() if result_at else None}

    async def archive_project(
        self,
        project_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> None:
        async with self.uow:
            p = await self.uow.projects.get(project_id)
            if not p:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
            if scope_company_ids is not None:
                if p.company_id is None or p.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")
            p.is_archived = True
            await self.uow.projects.flush()

    # ─── hydrate detail ───────────────────────────────────────────

    async def hydrate_detail(self, project_id: UUID) -> ProjectDetail:
        return await self._fetch_and_hydrate(project_id)

    async def _fetch_and_hydrate(self, project_id: UUID) -> ProjectDetail:
        async with self.uow:
            row = await self.uow.projects.get_with_joined(project_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
            p = row.Project

            cb = await self.uow.projects.child_task_counts_bulk([p.id])
            c = cb.get(p.id, {"total": 0, "done": 0, "sum": 0.0})
            base = project_to_brief(
                p, row.board_name, row.company_code, row.company_name,
                tasks_total=c["total"], tasks_done=c["done"], tasks_sum=c.get("sum", 0.0),
            )
            extra = p.extra or {}

            cmt_objs = await self.uow.projects.list_comments(p.id)
            author_ids = list({c.author_id for c in cmt_objs if c.author_id})
            users = await self.uow.projects.get_users_by_ids(author_ids)
            author_map = {
                u.id: (
                    getattr(u, "full_name", None) or getattr(u, "name", None) or getattr(u, "email", None),
                    getattr(u, "email", None),
                )
                for u in users
            }
            comments_list = [
                serialize_comment(c, *author_map.get(c.author_id, (None, None)))
                for c in cmt_objs
            ]

        return ProjectDetail(
            **base.model_dump(),
            description=p.description,
            scope=extra.get("scope"),
            consultants=extra.get("consultants", []) or [],
            extra=extra,
            legacy_id=p.legacy_id,
            creator_id=p.creator_id,
            start_date=p.start_date,
            completed_at=p.completed_at,
            consultant_comment=extra.get("consultant_comment"),
            economic_effect=extra.get("economic_effect")
            if isinstance(extra.get("economic_effect"), dict) else None,
            comments=comments_list,
        )
