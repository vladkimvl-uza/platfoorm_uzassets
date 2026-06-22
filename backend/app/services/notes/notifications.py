"""Side-effect helpers для notes-routes: уведомления о назначении ответственного.

Вызываются ПОСЛЕ того как сервис закоммитил заметку — best-effort
(никогда не ломают основной запрос). Назначение ответственного на заметку
или на пункт чек-листа порождает in-app + email/telegram уведомление
(тип `assignment`, как у задач).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.user import User
from app.schemas.notes import NoteRead

_KIND_LABELS = {
    "event": "Событие",
    "decision": "Решение",
    "task": "Задача",
    "risk": "Риск",
    "observation": "Наблюдение",
}


async def _company_link(db: AsyncSession, company_id: Optional[UUID]) -> Optional[str]:
    if company_id is None:
        return None
    code = (await db.execute(
        select(Company.code).where(Company.id == company_id),
    )).scalar_one_or_none()
    if not code:
        return None
    return f"/companies/{code}/workspace?tab=notes"


def _note_title(note: NoteRead) -> str:
    if note.title:
        return note.title
    body = (note.body or "").strip()
    return (body[:60] + "…") if len(body) > 60 else (body or "Заметка")


async def notify_note_assignment(
    db: AsyncSession,
    *,
    note: NoteRead,
    actor: User,
    recipient_id: UUID,
) -> None:
    """Уведомить нового ответственного за заметку."""
    if recipient_id == actor.id:
        return
    from app.services.notifications_service import notify

    kind_lbl = _KIND_LABELS.get(note.kind, "Запись")
    actor_name = actor.full_name or actor.email
    link = await _company_link(db, note.company_id)
    await notify(
        db,
        recipient_id=recipient_id,
        type="assignment",
        title=f"Вы ответственный: {_note_title(note)}",
        body=f"{actor_name} назначил(а) вас ответственным · {kind_lbl}",
        source_module="notes",
        source_entity_id=str(note.id),
        source_user_id=actor.id,
        company_id=note.company_id,
        payload={"note_id": str(note.id), "kind": note.kind},
        link_url=link,
    )


async def notify_checklist_assignment(
    db: AsyncSession,
    *,
    note: NoteRead,
    item_text: str,
    actor: User,
    recipient_id: UUID,
) -> None:
    """Уведомить нового ответственного за пункт чек-листа."""
    if recipient_id == actor.id:
        return
    from app.services.notifications_service import notify

    actor_name = actor.full_name or actor.email
    short = (item_text[:80] + "…") if len(item_text) > 80 else item_text
    link = await _company_link(db, note.company_id)
    await notify(
        db,
        recipient_id=recipient_id,
        type="assignment",
        title=f"Пункт назначен на вас: {short}",
        body=f"{actor_name} · в заметке «{_note_title(note)}»",
        source_module="notes",
        source_entity_id=str(note.id),
        source_user_id=actor.id,
        company_id=note.company_id,
        payload={"note_id": str(note.id), "checklist": True},
        link_url=link,
    )


def diff_new_checklist_assignees(
    before: Optional[object],
    after: NoteRead,
    actor_id: UUID,
) -> list[tuple[UUID, str]]:
    """Вернуть (assignee_id, item_text) для пунктов чек-листа, у которых
    ответственный появился/сменился относительно `before` (ORM-заметка) и не
    совпадает с автором изменения."""
    old_by_id: dict = {}
    if before is not None:
        for ci in (getattr(before, "checklist", None) or []):
            old_by_id[ci.id] = ci.assignee_id
    out: list[tuple[UUID, str]] = []
    for ci in after.checklist:
        aid = ci.assignee_id
        if not aid or aid == actor_id:
            continue
        prev = old_by_id.get(ci.id)
        if prev != aid:  # новый пункт (prev=None) или сменился ответственный
            out.append((aid, ci.text))
    return out
