"""Side-effect helpers для tasks-routes (вынесены сюда чтобы не загромождать
route файл). Вызываются ПОСЛЕ commit — best-effort нотификации.

При следующей итерации (Sprint B clients layer) переедет в
`clients/notifications.py` с явным `NotificationClientABC`.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.user import User


async def notify_task_assignment(
    db: AsyncSession,
    *,
    task: Task,
    old_email: Optional[str],
    new_email: Optional[str],
    actor: User,
) -> None:
    """Pack 13.2.4: emit `assignment` notification when task gets a new assignee."""
    if not new_email or new_email == old_email:
        return
    res = await db.execute(select(User).where(User.email == new_email))
    target = res.scalar_one_or_none()
    if not target:
        return  # legacy assignee, no user account

    if task.assignee_id != target.id:
        task.assignee_id = target.id
        await db.commit()
        await db.refresh(task)

    from app.services.notifications_service import notify
    body = (task.description or "")[:200] or None
    await notify(
        db,
        recipient_id=target.id,
        type="assignment",
        title=f"Задача назначена: {task.title}",
        body=body,
        source_module="tasks",
        source_entity_id=str(task.id),
        source_user_id=actor.id,
        payload={
            "task_id": str(task.id),
            "task_num": task.num,
            "board_id": str(task.board_id) if task.board_id else None,
            "company_id": str(task.company_id) if task.company_id else None,
        },
        link_url=f"/tasks/{task.id}",
    )


# Человекочитаемые лейблы статусов (синхронны с чипами фронта Tasks.vue).
_STATUS_LABELS = {
    "new": "Не начато",
    "init": "Инициирование",
    "active": "В процессе",
    "review": "На согласовании",
    "done": "Завершено",
    "quarterly": "Ежеквартально",
    "monthly": "Ежемесячно",
    "ongoing": "Постоянно",
    "deferred": "Перенесено",
}


async def notify_task_status_change(
    db: AsyncSession,
    *,
    task: Task,
    old_status: Optional[str],
    new_status: Optional[str],
    actor: User,
) -> None:
    """Уведомить участников задачи (создатель + исполнитель + комментаторы,
    кроме самого инициатора) о смене статуса.

    Раньше смена статуса не порождала никаких уведомлений — наблюдатели
    узнавали об изменении только зайдя в задачу.
    """
    if not new_status or new_status == old_status:
        return

    from app.services.comment_participants_service import _collect_task_participants
    from app.services.notifications_service import notify

    recipients = await _collect_task_participants(db, task)

    # Oversight: смену статуса ВНЕШНИМ пользователем surface-им владельцам
    # (is_owner), даже если у задачи нет creator/assignee — иначе при
    # импортированных задачах (creator_id=NULL) уведомление не дошло бы ни до
    # кого. Для внутренних авторов — только участники задачи, без спама админам.
    if getattr(actor, "is_external", False):
        owner_rows = (await db.execute(
            select(User.id).where(User.is_owner.is_(True), User.is_active.is_(True)),
        )).all()
        recipients.update(uid for (uid,) in owner_rows)

    recipients.discard(actor.id)  # не уведомляем автора изменения
    if not recipients:
        return

    old_lbl = _STATUS_LABELS.get(old_status or "", old_status or "—")
    new_lbl = _STATUS_LABELS.get(new_status or "", new_status or "—")
    actor_name = actor.full_name or actor.email
    is_done = new_status == "done"

    for uid in recipients:
        await notify(
            db,
            recipient_id=uid,
            type="task.status_changed",
            title=f"Статус задачи: {task.title}",
            body=f"{actor_name} · {old_lbl} → {new_lbl}",
            priority="normal",
            source_module="tasks",
            source_entity_id=str(task.id),
            source_user_id=actor.id,
            company_id=task.company_id,
            payload={
                "task_id": str(task.id),
                "task_num": task.num,
                "old_status": old_status,
                "new_status": new_status,
                "is_done": is_done,
                "company_id": str(task.company_id) if task.company_id else None,
            },
            link_url=f"/tasks/{task.id}",
        )
