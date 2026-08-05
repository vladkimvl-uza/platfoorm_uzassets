"""Tasks apply handler (Pack 148-followup B1).

Dispatches by sub.action:
  - "create" / "created"                      → mirrors POST /tasks
  - "update" / "status_change" / "edit"       → mirrors PATCH /tasks/{id}

NB: роут PATCH /tasks шлёт action="status_change" при смене статуса (и
"update" иначе) — оба применяются одинаково (патч proposed_value на задачу).
Без этого аппрув статус-сабмишена падал бы с 'unknown tasks action'.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.task import Task, TaskHistory
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.moderation_service import register_apply_handler

# Fields that live in Task.extra JSONB instead of as model columns.
_EXTRA_FIELDS = ("consultant", "consultant_comment", "economic_effect",
                 "quarters", "direction", "scope")


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()

    if action in ("create", "created"):
        payload = TaskCreate.model_validate(sub.proposed_value)
        extra: dict = {}
        for f in _EXTRA_FIELDS:
            v = getattr(payload, f, None)
            if v is not None:
                if f == "direction":
                    from app.core.direction_normalize import normalize_direction
                    v = normalize_direction(v)
                extra[f] = v
        task = Task(
            title=payload.title, description=payload.description, num=payload.num,
            status=payload.status, priority=payload.priority,
            board_id=payload.board_id, company_id=payload.company_id,
            project_id=payload.project_id, direction_id=payload.direction_id,
            assignee_email=payload.assignee_email, assignee_name=payload.assignee_name,
            start_date=payload.start_date, due_date=payload.due_date,
            portfolio_year=payload.portfolio_year, tags=payload.tags,
            extra=extra or None,
            creator_id=user.id,  # moderator who approved is recorded as creator
        )
        db.add(task)
        await db.flush()
        db.add(TaskHistory(
            task_id=task.id, actor_id=user.id, action="created",
            new_value=f"{task.title}",
        ))
        # Авто-статус проекта — тем же правилом, что и прямой редактор.
        from app.services.tasks.project_status import recompute_project_status
        await recompute_project_status(db, task.project_id)
        await db.commit()
        return {"action": "create", "task_id": str(task.id)}

    if action in ("update", "status_change", "edit"):
        if not sub.target_entity_id:
            raise ValueError("missing target_entity_id for update")
        try:
            tid = UUID(sub.target_entity_id)
        except Exception as e:
            raise ValueError(f"invalid task id: {sub.target_entity_id}") from e
        task = (await db.execute(
            select(Task).where(Task.id == tid)
        )).scalar_one_or_none()
        if task is None:
            raise ValueError(f"Task {tid} no longer exists")

        payload = TaskUpdate.model_validate(sub.proposed_value)
        changes = payload.model_dump(exclude_unset=True)
        old_project_id = task.project_id

        # Split legacy-specific fields → extra JSONB
        extra = dict(task.extra or {})
        extra_dirty = False
        for f in _EXTRA_FIELDS:
            if f in changes:
                v = changes.pop(f)
                if f == "direction":
                    # Тот же нормализатор, что в прямом редакторе, — иначе
                    # одобренная заявка внешнего автора писала сырую метку и
                    # плодила регистровые дубли направлений.
                    from app.core.direction_normalize import normalize_direction
                    v = normalize_direction(v)
                extra[f] = v
                extra_dirty = True
        if extra_dirty:
            task.extra = extra or None

        for field, value in changes.items():
            setattr(task, field, value)

        await db.flush()
        # Авто-статус проекта (обоих — если задачу перенесли между проектами).
        from app.services.tasks.project_status import recompute_many
        await recompute_many(db, {old_project_id, task.project_id})
        await db.commit()
        return {"action": "update", "task_id": str(tid)}

    raise ValueError(f"unknown tasks action: {action!r}")


register_apply_handler("tasks", apply)
