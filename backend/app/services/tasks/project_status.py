"""Авто-статус проекта из статусов его задач.

Правило владельца (05.08.2026): статус проекта не живёт своей жизнью —
он выводится из задач. Хотя бы одна задача начата → проект «в процессе»;
все задачи рекуррентные → проект той же периодичности; все завершены →
проект завершён. Сама формула — канон `core.progress.derive_project_status`,
здесь только применение к БД.

Вызывается из КАЖДОГО пути записи задач (редактор, модерация, импорт
конструктора, ИИ-инструменты) — статус пересчитывается там, где изменились
задачи, а не по расписанию, поэтому список проектов всегда согласован с
содержимым. У проекта без задач статус остаётся ручным.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.progress import derive_project_status
from app.models.project import Project
from app.models.task import Task

log = logging.getLogger(__name__)


async def recompute_project_status(
    db: AsyncSession, project_id: Optional[UUID],
) -> Optional[tuple[str, str]]:
    """Пересчитать статус проекта по живым задачам. Возвращает (старый, новый)
    при фактической смене, иначе None. НЕ коммитит — живёт в транзакции
    вызывающего, чтобы задача и статус проекта менялись атомарно.
    """
    if project_id is None:
        return None
    project = await db.get(Project, project_id)
    if project is None:
        return None

    statuses = (await db.execute(
        select(Task.status).where(
            Task.project_id == project_id,
            Task.is_archived.is_(False),
        )
    )).scalars().all()

    derived = derive_project_status(statuses)
    if derived is None or derived == project.status:
        return None

    old = project.status
    project.status = derived
    # completed_at проекта ведём как у задач: появился при done, снят при откате.
    if hasattr(project, "completed_at"):
        from datetime import UTC, datetime
        if derived == "done" and not project.completed_at:
            project.completed_at = datetime.now(UTC)
        elif derived != "done" and project.completed_at:
            project.completed_at = None
    log.info("project %s: авто-статус %s -> %s (задач: %d)",
             project_id, old, derived, len(statuses))
    return (old, derived)


async def recompute_many(db: AsyncSession, project_ids) -> int:
    """Пересчитать набор проектов (например, при переносе задачи между
    проектами меняются оба). Возвращает число реально изменённых."""
    changed = 0
    seen = set()
    for pid in project_ids:
        if not pid or pid in seen:
            continue
        seen.add(pid)
        if await recompute_project_status(db, pid):
            changed += 1
    return changed
