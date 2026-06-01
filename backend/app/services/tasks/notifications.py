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
