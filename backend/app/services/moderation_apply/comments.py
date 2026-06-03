"""Comments apply handler — модерация комментариев задач/проектов.

Когда правило модерации перехватывает создание комментария (module="comments",
action="comment"), сам комментарий НЕ создаётся сразу — gate_or_apply кладёт
proposed_value = {body, parent_kind, parent_id} в сабмишен. При аппруве этот
handler создаёт комментарий от имени АВТОРА (proposer, не модератора) и
прогоняет те же side-effects, что и обычный роут: уведомления об упоминаниях
и участникам.

proposed_value:
  { "body": str, "parent_kind": "task"|"project", "parent_id": "<uuid>" }
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.project import Project, ProjectComment
from app.models.task import Task, TaskComment
from app.models.user import User
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    pv = sub.proposed_value or {}
    body = pv.get("body")
    kind = pv.get("parent_kind")
    raw_pid = pv.get("parent_id")
    if not body or kind not in ("task", "project") or not raw_pid:
        raise ValueError("invalid comment proposed_value")
    try:
        parent_id = UUID(raw_pid)
    except Exception as e:
        raise ValueError(f"invalid parent_id: {raw_pid}") from e

    # Автор комментария — тот, кто его предложил (а не модератор).
    proposer = await db.get(User, sub.proposer_user_id)
    if proposer is None:
        raise ValueError("proposer user no longer exists")

    # Загружаем родителя (задача/проект) для контекста уведомлений.
    if kind == "project":
        parent = (await db.execute(
            select(Project).where(Project.id == parent_id),
        )).scalar_one_or_none()
        comment = ProjectComment(author_id=proposer.id, body=body, is_edited=False, project_id=parent_id)
    else:
        parent = (await db.execute(
            select(Task).where(Task.id == parent_id),
        )).scalar_one_or_none()
        comment = TaskComment(author_id=proposer.id, body=body, is_edited=False, task_id=parent_id)

    if parent is None:
        raise ValueError(f"{kind} {parent_id} no longer exists")

    db.add(comment)
    await db.flush()

    # company_name для шапки уведомлений
    company_name = None
    if getattr(parent, "company_id", None):
        from app.models.company import Company
        co = (await db.execute(
            select(Company).where(Company.id == parent.company_id),
        )).scalar_one_or_none()
        if co:
            company_name = co.name_short or co.name_ru

    # Side-effects: те же, что в роуте создания комментария.
    from app.services.comment_participants_service import notify_comment_participants
    from app.services.mention_service import notify_mentioned_users

    link_url = f"/{'projects' if kind == 'project' else 'tasks'}/{parent_id}"
    actor_name = proposer.full_name or proposer.email
    mentioned_ids = await notify_mentioned_users(
        db, text=body,
        actor_id=proposer.id, actor_name=actor_name,
        entity_type=kind, entity_id=str(parent_id),
        entity_title=getattr(parent, "title", None) or "(без названия)",
        company_name=company_name,
        comment_id=str(comment.id),
        link_url=link_url,
    )
    await notify_comment_participants(
        db,
        entity_type=kind, entity=parent,
        comment_id=comment.id, body=body,
        actor_id=proposer.id, actor_name=actor_name,
        company_name=company_name,
        link_url=link_url,
        skip_user_ids=mentioned_ids,
    )

    await db.commit()
    return {"action": "comment", "comment_id": str(comment.id), "parent_kind": kind}


register_apply_handler("comments", apply)
