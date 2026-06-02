"""Tasks editor service — create/update/toggle_result/archive.

Side-effects (mention notifications, assignment notifications) делаются после
успешного commit — service возвращает task + dict с metadata о произошедших
изменениях, route ловит и делает hooks.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.task import Task, TaskHistory
from app.schemas.task import TaskCreate, TaskDetail, TaskUpdate
from app.services.tasks._helpers import task_to_brief
from app.uow.ports import UnitOfWorkABC

EXTRA_FIELDS = {
    "consultant", "consultant_comment", "economic_effect",
    "quarters", "direction", "scope",
}
AUDIT_FIELDS = {
    "status", "title", "priority", "assignee_email",
    "assignee_name", "due_date", "num", "board_id",
}


class TasksEditorService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def create_task(
        self,
        payload: TaskCreate,
        *,
        creator_id: UUID,
    ) -> tuple[Task, Optional[str]]:
        """Returns (task, assignee_email_to_notify). Route handles notification call."""
        async with self.uow:
            # Validate board if provided
            if payload.board_id and not await self.uow.tasks.board_exists(payload.board_id):
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Board {payload.board_id} not found",
                )

            extra: dict = {}
            if payload.consultant is not None:
                extra["consultant"] = payload.consultant
            if payload.consultant_comment is not None:
                extra["consultant_comment"] = payload.consultant_comment
            if payload.economic_effect is not None:
                extra["economic_effect"] = payload.economic_effect
            if payload.quarters is not None:
                extra["quarters"] = payload.quarters
            if payload.direction is not None:
                from app.core.direction_normalize import normalize_direction
                extra["direction"] = normalize_direction(payload.direction)
            if payload.scope is not None:
                extra["scope"] = payload.scope

            task = Task(
                title=payload.title,
                description=payload.description,
                num=payload.num,
                status=payload.status,
                priority=payload.priority,
                board_id=payload.board_id,
                company_id=payload.company_id,
                project_id=payload.project_id,
                direction_id=payload.direction_id,
                assignee_email=payload.assignee_email,
                assignee_name=payload.assignee_name,
                start_date=payload.start_date,
                due_date=payload.due_date,
                portfolio_year=payload.portfolio_year,
                tags=payload.tags,
                extra=extra or None,
                creator_id=creator_id,
            )
            self.uow.tasks.add(task)
            await self.uow.tasks.flush()

            self.uow.tasks.add(TaskHistory(
                task_id=task.id, actor_id=creator_id, action="created",
                new_value=f"{task.title}",
            ))

            # Синк consultant → ConsultantAssignment (модуль консультантов).
            if payload.consultant is not None:
                await self._sync_consultant_assignments(task.id, payload.consultant)

            # implicit commit on __aexit__
            await self.uow.tasks.refresh(task)

        return task, payload.assignee_email

    async def update_task(
        self,
        task_id: UUID,
        payload: TaskUpdate,
        *,
        actor_id: UUID,
        scope_company_ids: Optional[list[UUID]] = None,
    ) -> tuple[Task, dict]:
        """Returns (task, info-dict for route to drive side-effects).

        info-dict keys:
            - old_assignee_email: str | None
            - new_assignee_email: str | None (only if changed)
            - description_changed: bool
            - mention_text: str | None
        """
        async with self.uow:
            task = await self.uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")

            if scope_company_ids is not None:
                if task.company_id is None or task.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this task")
                new_company_id = payload.model_dump(exclude_unset=True).get("company_id")
                if new_company_id is not None and new_company_id not in scope_company_ids:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        "Cannot reassign task to a company outside your allowed list",
                    )

            changes = payload.model_dump(exclude_unset=True)
            old_assignee_email = task.assignee_email

            extra_updates = {k: changes.pop(k) for k in list(changes.keys()) if k in EXTRA_FIELDS}

            # Audit log
            for field, new_value in changes.items():
                if field in AUDIT_FIELDS:
                    old_value = getattr(task, field)
                    if str(old_value or "") != str(new_value or ""):
                        self.uow.tasks.add(TaskHistory(
                            task_id=task.id, actor_id=actor_id,
                            action="status_changed" if field == "status" else "field_updated",
                            field_name=field,
                            old_value=str(old_value or ""), new_value=str(new_value or ""),
                        ))

            # Apply column updates
            for field, value in changes.items():
                setattr(task, field, value)

            # Merge JSONB updates
            if extra_updates:
                from app.core.direction_normalize import normalize_direction
                merged = dict(task.extra or {})
                for k, v in extra_updates.items():
                    if v is None:
                        merged.pop(k, None)
                    elif k == "direction":
                        merged[k] = normalize_direction(v)
                    else:
                        merged[k] = v
                task.extra = merged or None

            # Консультант хранится в extra, но модуль консультантов агрегирует из
            # join-таблицы ConsultantAssignment → синкаем её при изменении.
            if "consultant" in extra_updates:
                await self._sync_consultant_assignments(
                    task.id, (task.extra or {}).get("consultant")
                )

            # Auto-completed_at logic
            if changes.get("status") == "done" and not task.completed_at:
                task.completed_at = datetime.now(UTC)
            if "status" in changes and changes["status"] != "done":
                task.completed_at = None

            # Auto-align year to project
            await self._align_year(task, actor_id)
            # Bug fix 2026-05-25: AsyncSessionLocal has autoflush=False, so a
            # bare refresh() here was issuing SELECT on stale DB state and
            # silently dropping every setattr() above (audit_log saw the
            # change but tasks.status never updated). Must flush() FIRST so
            # pending UPDATE hits the DB; then refresh() safely re-loads the
            # row (now matching the new values) to keep `task` usable after
            # the __aexit__ commit closes the session.
            await self.uow.flush()
            await self.uow.tasks.refresh(task)

        info = {
            "old_assignee_email": old_assignee_email,
            "new_assignee_email": changes.get("assignee_email") if "assignee_email" in changes else None,
            "assignee_changed": "assignee_email" in changes,
            "description_changed": "description" in changes,
            "mention_text": changes.get("description") if "description" in changes else None,
        }
        return task, info

    async def _sync_consultant_assignments(
        self, task_id: UUID, consultant_value: object
    ) -> None:
        """Приводит ConsultantAssignment(source='task') в соответствие с
        task.extra['consultant'] (str | list[str] | None).

        Модуль консультантов (/consultants/overview, /consultants/by-company)
        агрегирует ИЗ этой join-таблицы, а не из task.extra — поэтому без синка
        назначенный в редакторе/inline консультант там не появляется.
        Связи source in ('manual','lookup') не трогаем. Должно вызываться внутри
        `async with self.uow:`.
        """
        from app.models.consultant import ConsultantAssignment

        # Значение → список токенов (code/abbr/name_ru)
        if consultant_value is None:
            tokens: list[str] = []
        elif isinstance(consultant_value, str):
            tokens = [consultant_value] if consultant_value.strip() else []
        elif isinstance(consultant_value, (list, tuple)):
            tokens = [str(t) for t in consultant_value if str(t).strip()]
        else:
            tokens = []

        # Резолвим токены → consultant_id (по code/abbr/name_ru, регистронезависимо)
        desired_ids: set = set()
        if tokens:
            all_cons = await self.uow.consultants.list_all(include_inactive=True)
            for tok in tokens:
                t = tok.strip().lower()
                for c in all_cons:
                    if (
                        (c.code and c.code.lower() == t)
                        or (c.abbr and c.abbr.lower() == t)
                        or (c.name_ru and c.name_ru.lower() == t)
                    ):
                        desired_ids.add(c.id)
                        break

        existing = await self.uow.consultants.assignment_rows_for_task(task_id)
        present_ids: set = set()
        for a in existing:
            # Снимаем устаревшие task-производные связи; manual/lookup сохраняем.
            if a.source == "task" and a.consultant_id not in desired_ids:
                await self.uow.consultants.delete(a)
            else:
                present_ids.add(a.consultant_id)
        for cid in desired_ids:
            if cid not in present_ids:
                self.uow.consultants.add(
                    ConsultantAssignment(task_id=task_id, consultant_id=cid, source="task")
                )

    async def toggle_result(
        self,
        task_id: UUID,
        *,
        actor_id: UUID,
        scope_company_ids: Optional[list[UUID]] = None,
    ) -> dict:
        async with self.uow:
            task = await self.uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")
            if scope_company_ids is not None:
                if task.company_id is None or task.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this task")

            old = task.result_at
            task.result_at = None if old else datetime.now(UTC)
            self.uow.tasks.add(TaskHistory(
                task_id=task.id, actor_id=actor_id,
                action="result_cleared" if old else "result_set",
                field_name="result_at",
                old_value=str(old) if old else None,
                new_value=str(task.result_at) if task.result_at else None,
            ))
        return {"result_at": task.result_at.isoformat() if task.result_at else None}

    async def archive_task(
        self,
        task_id: UUID,
        *,
        actor_id: UUID,
        scope_company_ids: Optional[list[UUID]] = None,
    ) -> None:
        async with self.uow:
            task = await self.uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")
            if scope_company_ids is not None:
                if task.company_id is None or task.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this task")
            task.is_archived = True
            self.uow.tasks.add(TaskHistory(
                task_id=task.id, actor_id=actor_id, action="archived",
            ))

    # ─── helpers ──────────────────────────────────────────────────

    async def _align_year(self, task: Task, actor_id: Optional[UUID]) -> None:
        """Silently align task.portfolio_year to project.portfolio_year if mismatched."""
        if not task.project_id:
            return
        project = await self.uow.tasks.get_project(task.project_id)
        if not project or not project.portfolio_year:
            return
        if task.portfolio_year == project.portfolio_year:
            return
        old_year = task.portfolio_year
        task.portfolio_year = project.portfolio_year
        self.uow.tasks.add(TaskHistory(
            task_id=task.id, actor_id=actor_id,
            action="auto_aligned", field_name="portfolio_year",
            old_value=str(old_year) if old_year is not None else None,
            new_value=str(project.portfolio_year),
        ))

    async def hydrate_detail(self, task: Task) -> TaskDetail:
        """Build TaskDetail including comments + author info."""
        async with self.uow:
            board_name = await self.uow.tasks.get_board_name(task.board_id) if task.board_id else None
            company_code = await self.uow.tasks.get_company_code(task.company_id) if task.company_id else None

            base = task_to_brief(task, board_name, company_code)
            extra = task.extra or {}

            comments = await self.uow.tasks.list_recent_comments(task.id)
            comments_list: list[dict] = []
            if comments:
                author_ids = list({c.author_id for c in comments if c.author_id})
                users = await self.uow.tasks.get_users_by_ids(author_ids)
                author_map = {
                    u.id: (
                        getattr(u, "full_name", None) or getattr(u, "name", None) or getattr(u, "email", None),
                        getattr(u, "email", None),
                    )
                    for u in users
                }
                for c in comments:
                    name, email = author_map.get(c.author_id, (None, None))
                    comments_list.append({
                        "id": str(c.id),
                        "author_id": str(c.author_id) if c.author_id else None,
                        "author_name": name,
                        "author_email": email,
                        "body": c.body,
                        "is_edited": c.is_edited,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                    })

        return TaskDetail(
            **base.model_dump(),
            description=task.description,
            scope=extra.get("scope"),
            consultants=extra.get("consultants", []) or [],
            extra=extra,
            legacy_id=task.legacy_id,
            creator_id=task.creator_id,
            start_date=task.start_date,
            completed_at=task.completed_at,
            consultant_comment=extra.get("consultant_comment"),
            economic_effect=extra.get("economic_effect") if isinstance(extra.get("economic_effect"), dict) else None,
            comments=comments_list,
        )
