"""Notes (Smart Journal) apply handler — deny-by-default Phase 4.

Применяет одобренную правку заметки. Зеркалит POST /notes, PATCH /notes/{id},
PATCH /notes/checklist/{item_id}, DELETE /notes/{id} через NotesService.
NotesService работает на СВОЕЙ UoW/сессии (как companies/projects), поэтому
create — с idempotency-штампом target_entity_id: повтор применения не плодит
дубль.

Атрибуция аудита/назначений — ПРЕДЛОЖИВШИЙ (proposer), не модератор.

Submission shape:
  target_module    = "notes"
  action           = create | edit | delete
  target_entity_id = <note id>      (edit/delete; для create — застолблённый id)
                     <checklist item id> (правка пункта чек-листа)
  proposed_value   =
     create → NoteCreate.model_dump(mode="json")
     edit   → NoteUpdate.model_dump(mode="json", exclude_unset=True)
              ЛИБО {"checklist_item_id","patch"} — точечная правка пункта
     delete → {"note_id"}

ВАЖНО (exclude_unset): NoteUpdate/ChecklistItemPatch применяются сервисом через
model_dump(exclude_unset=True) — «правим только присланные поля». Поэтому гейт
сериализует их с exclude_unset=True, иначе повтор через очередь затирал бы все
неприсланные поля в None (потеря данных).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.notes import ChecklistItemPatch, NoteCreate, NoteUpdate
from app.services.moderation_service import register_apply_handler
from app.services.notes.service import NotesService
from app.uow.impl import UnitOfWork


def _service() -> NotesService:
    return NotesService(uow=UnitOfWork(session_factory=AsyncSessionLocal))


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value)

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user
    author_id = author.id
    service = _service()

    if action in ("create", "created"):
        # Идемпотентность повтора: если прошлый apply уже создал заметку и
        # застолбил её id в target_entity_id, повтор НЕ создаёт дубль.
        if sub.target_entity_id:
            try:
                nid = UUID(sub.target_entity_id)
            except Exception:
                nid = None
            if nid is not None:
                from app.models.note import Note
                exists = (await db.execute(
                    select(Note.id).where(Note.id == nid)
                )).scalar_one_or_none()
                if exists is not None:
                    return {"action": "create", "note_id": str(nid), "idempotent": True}
        payload = NoteCreate.model_validate(pv)
        created = await service.create_note(payload, author_id=author_id)
        sub.target_entity_id = str(created.id)  # застолбить id (коммитит _dispatch_apply)
        return {"action": "create", "note_id": str(created.id)}

    if action in ("edit", "update"):
        # Два edit-роута заметок несут один action="edit". Точечная правка пункта
        # чек-листа помечена дискриминатором checklist_item_id; всё остальное —
        # правка самой заметки.
        item_id_raw = pv.get("checklist_item_id")
        if item_id_raw:
            item_id = UUID(str(item_id_raw))
            patch = ChecklistItemPatch.model_validate(pv.get("patch") or {})
            await service.patch_checklist_item(item_id, patch, actor_id=author_id)
            return {"action": "edit", "checklist_item_id": str(item_id)}
        note_id = UUID(str(pv.get("note_id") or sub.target_entity_id))
        payload = NoteUpdate.model_validate(pv)
        await service.update_note(note_id, payload)
        return {"action": "edit", "note_id": str(note_id)}

    if action == "delete":
        note_id = UUID(str(pv.get("note_id") or sub.target_entity_id))
        await service.delete_note(note_id)
        return {"action": "delete", "note_id": str(note_id)}

    raise ValueError(f"unknown notes action: {action!r}")


register_apply_handler("notes", apply)
