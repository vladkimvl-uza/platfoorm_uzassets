"""Notify all participants of a task/project when a new comment is added.

Participants = creator + assignee + every prior commenter, minus:
  - the actor (don't notify the author of their own comment)
  - users already notified by mention (they get a richer `mention` notification)

Notification type: `comment.replied` (already mapped to `type_mentions` pref).
The payload mirrors the mention payload so the Telegram «💬 Ответить в чате»
button works identically.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def _collect_task_participants(db: AsyncSession, task) -> set[UUID]:
    """Owner + assignee + every prior commenter of this task."""
    from app.models.task import TaskComment
    out: set[UUID] = set()
    if task.creator_id:
        out.add(task.creator_id)
    if task.assignee_id:
        out.add(task.assignee_id)
    rows = (await db.execute(
        select(TaskComment.author_id)
        .where(TaskComment.task_id == task.id)
        .where(TaskComment.author_id.is_not(None))
        .distinct()
    )).all()
    for (uid,) in rows:
        out.add(uid)
    return out


async def _collect_project_participants(db: AsyncSession, project) -> set[UUID]:
    """Owner + assignee + every prior commenter of this project."""
    from app.models.project import ProjectComment
    out: set[UUID] = set()
    if project.creator_id:
        out.add(project.creator_id)
    if project.assignee_id:
        out.add(project.assignee_id)
    rows = (await db.execute(
        select(ProjectComment.author_id)
        .where(ProjectComment.project_id == project.id)
        .where(ProjectComment.author_id.is_not(None))
        .distinct()
    )).all()
    for (uid,) in rows:
        out.add(uid)
    return out


async def notify_comment_participants(
    db: AsyncSession,
    *,
    entity_type: str,                 # 'task' | 'project'
    entity,                           # Task or Project row
    comment_id,                       # UUID of the just-created comment
    body: str,
    actor_id: Optional[UUID],
    actor_name: Optional[str],
    company_name: Optional[str],
    link_url: Optional[str] = None,
    skip_user_ids: Optional[Iterable[UUID]] = None,
) -> list[UUID]:
    """Fire `comment.replied` notifications to every participant of the entity
    except the actor and anyone in `skip_user_ids` (typically: already mentioned).

    Schedules background TG forwarding for each notification, so callers using
    `commit=False` still get Telegram delivery once the transaction commits.

    Returns the list of user IDs that were notified.
    """
    if entity_type == "task":
        recipients = await _collect_task_participants(db, entity)
    elif entity_type == "project":
        recipients = await _collect_project_participants(db, entity)
    else:
        return []

    skip = set(skip_user_ids or [])
    if actor_id:
        skip.add(actor_id)
    recipients = {uid for uid in recipients if uid not in skip}
    if not recipients:
        return []

    try:
        from app.services.notifications_service import notify
    except ImportError:
        return list(recipients)

    kind_ru = {"task": "задаче", "project": "проекте"}.get(entity_type, "записи")
    entity_title = (getattr(entity, "title", None) or "(без названия)")
    company_part = f" · {company_name}" if company_name else ""
    title = f"{actor_name or 'Кто-то'} оставил комментарий в {kind_ru}: «{entity_title}»{company_part}"

    notification_ids: list[str] = []
    notified: list[UUID] = []
    for uid in recipients:
        try:
            n = await notify(
                db,
                recipient_id=uid,
                type="comment.replied",
                title=title,
                body=body[:600],
                source_module=entity_type,
                source_entity_id=str(entity.id),
                source_user_id=actor_id,
                link_url=link_url,
                priority="normal",
                payload={
                    "actor_name": actor_name,
                    "entity_type": entity_type,
                    "entity_id": str(entity.id),
                    "entity_title": entity_title,
                    "company_name": company_name,
                    "comment_id": str(comment_id) if comment_id else None,
                    "raw_text": body[:1000],
                },
                commit=False,
            )
            if n is not None:
                notification_ids.append(str(n.id))
                notified.append(uid)
        except Exception as e:
            log.warning("comment-participant notify failed for uid=%s: %s", uid, e)
            continue

    if notification_ids:
        try:
            from app.services.telegram_notify_hook_bg import schedule_forward
            for nid in notification_ids:
                schedule_forward(nid)
        except Exception as e:
            log.warning("comment-participant: tg-forward schedule failed: %s", e)

    return notified
