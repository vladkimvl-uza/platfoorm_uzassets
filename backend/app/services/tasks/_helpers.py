"""Pure-function helpers для Tasks services: ORM → DTO mapping."""
from __future__ import annotations

from typing import Optional

from app.core.progress import is_task_overdue, task_pct
from app.models.task import Task
from app.schemas.task import TaskBrief


def task_to_brief(
    t: Task,
    board_name: Optional[str] = None,
    company_code: Optional[str] = None,
) -> TaskBrief:
    """ORM Task → TaskBrief DTO (verbatim port from legacy _task_to_brief).

    2026-05-26: добавлены linked_year / linked_task_id / project_id —
    без них «Перенос FY+1» сохранялся в DB, но при rehydrate UI получал
    null → пользователь видел «не сохранилось». Также project_id нужен
    для роутинга в editor «Открыть проект».
    """
    is_overdue = is_task_overdue(t.status, t.due_date)
    extra = t.extra or {}
    return TaskBrief(
        id=t.id, num=t.num, title=t.title,
        status=t.status, priority=t.priority,
        board_id=t.board_id, board_name=board_name,
        company_id=t.company_id, company_code=company_code,
        assignee_email=t.assignee_email, assignee_name=t.assignee_name, assignee_id=t.assignee_id,
        due_date=t.due_date, portfolio_year=t.portfolio_year,
        project_id=t.project_id,
        linked_year=t.linked_year,
        linked_task_id=t.linked_task_id,
        is_project=False, progress_percent=(task_pct(t.status, t.extra) or 0),
        sort_order=getattr(t, "sort_order", 0) or 0,
        is_overdue=is_overdue, tags=t.tags,
        # Legacy-specific (from extra JSONB)
        quarters=extra.get("quarters") if isinstance(extra.get("quarters"), dict) else None,
        consultant=extra.get("consultant"),
        direction=extra.get("direction"),
        created_at=t.created_at, updated_at=t.updated_at,
        # «Результат»: без проброса result_at toggle сохранялся в БД, но rehydrate
        # возвращал null → после обновления кнопка снова просила результат.
        result_at=t.result_at,
    )
