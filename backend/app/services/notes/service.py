"""Use cases for Notes (Smart Journal)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.note import Note, NoteChecklistItem, NoteLink
from app.schemas.notes import (
    ChecklistItemPatch,
    NoteCreate,
    NoteListResponse,
    NoteRead,
    NoteUpdate,
    TagCount,
)
from app.uow.ports import UnitOfWorkABC


class NotesService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── list ─────────────────────────────────────────────────────

    async def list_notes(
        self,
        *,
        company_id: Optional[UUID],
        scoped_company_ids: Optional[Sequence[UUID]],
        kind,
        tag,
        query: Optional[str],
        only_unresolved: bool,
        include_resolved: bool,
        pinned_first: bool,
        limit: int,
        offset: int,
    ) -> NoteListResponse:
        conditions = []
        if company_id is not None:
            conditions.append(Note.company_id == company_id)
        elif scoped_company_ids is not None:
            if not scoped_company_ids:
                return NoteListResponse(items=[], total=0, tag_counts=[])
            conditions.append(Note.company_id.in_(scoped_company_ids))
        if kind:
            conditions.append(Note.kind.in_(kind))
        if tag:
            conditions.append(Note.tags.op("&&")(tag))
        if only_unresolved:
            conditions.append(Note.is_resolved == False)  # noqa: E712
        elif not include_resolved:
            conditions.append(Note.is_resolved == False)  # noqa: E712
        if query:
            from app.repositories.notes_repository import NotesRepository
            conditions.append(NotesRepository.search_predicates(query))

        async with self.uow:
            items, total = await self.uow.notes.list_notes(
                conditions=conditions, pinned_first=pinned_first,
                limit=limit, offset=offset,
            )

            # tag_counts within the same scope (без q/kind/tag, чтобы дать полный набор)
            tag_count_conditions = []
            if company_id is not None:
                tag_count_conditions.append(Note.company_id == company_id)
            elif scoped_company_ids is not None and scoped_company_ids:
                tag_count_conditions.append(Note.company_id.in_(scoped_company_ids))
            tag_rows = await self.uow.notes.tag_counts(conditions=tag_count_conditions)
            tag_counts = [TagCount(tag=row[0], count=row[1]) for row in tag_rows]

        return NoteListResponse(items=items, total=total, tag_counts=tag_counts)

    # ─── tags ─────────────────────────────────────────────────────

    async def list_tags(
        self,
        *,
        company_id: Optional[UUID],
        scoped_company_ids: Optional[Sequence[UUID]],
        limit: int,
    ) -> list[TagCount]:
        conditions = []
        if company_id is not None:
            conditions.append(Note.company_id == company_id)
        elif scoped_company_ids is not None:
            if not scoped_company_ids:
                return []
            conditions.append(Note.company_id.in_(scoped_company_ids))
        async with self.uow:
            rows = await self.uow.notes.tag_counts(conditions=conditions, limit=limit)
        return [TagCount(tag=r[0], count=r[1]) for r in rows]

    # ─── notes-by-entity ──────────────────────────────────────────

    async def notes_by_entity(
        self,
        *,
        entity_type: str,
        entity_id: Optional[UUID],
        entity_key: Optional[str],
    ) -> list[NoteRead]:
        if entity_id is None and entity_key is None:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "either entity_id or entity_key required",
            )
        async with self.uow:
            return await self.uow.notes.notes_by_entity(
                entity_type=entity_type, entity_id=entity_id, entity_key=entity_key,
            )

    # ─── create ───────────────────────────────────────────────────

    async def create_note(
        self,
        payload: NoteCreate,
        *,
        author_id: UUID,
    ) -> NoteRead:
        async with self.uow:
            note = Note(
                user_id=author_id,
                author_id=author_id,
                company_id=payload.company_id,
                entity_type=payload.entity_type,
                entity_id=payload.entity_id,
                kind=payload.kind,
                title=payload.title,
                body=payload.body,
                tags=payload.tags,
                color=payload.color,
                is_pinned=payload.is_pinned,
                event_date=payload.event_date,
                due_date=payload.due_date,
                assignee_id=payload.assignee_id,
                assignee_name=payload.assignee_name,
            )
            self.uow.notes.add(note)
            await self.uow.notes.flush()
            if payload.links:
                for ld in payload.links:
                    self.uow.notes.add(NoteLink(
                        note_id=note.id,
                        entity_type=ld.entity_type,
                        entity_id=ld.entity_id,
                        entity_key=ld.entity_key,
                        entity_label=ld.entity_label,
                    ))
                await self.uow.notes.flush()
            if payload.checklist:
                for pos, ci in enumerate(payload.checklist):
                    self.uow.notes.add(NoteChecklistItem(
                        note_id=note.id,
                        text=ci.text,
                        is_done=ci.is_done,
                        position=ci.position if ci.position else pos,
                        assignee_id=ci.assignee_id,
                        assignee_name=ci.assignee_name,
                        due_date=ci.due_date,
                        done_at=datetime.now(UTC) if ci.is_done else None,
                    ))
                await self.uow.notes.flush()
            note_id = note.id

        return await self._reload(note_id)

    # ─── update ───────────────────────────────────────────────────

    async def get_for_scope_check(self, note_id: UUID) -> Note:
        async with self.uow:
            note = await self.uow.notes.get_with_links(note_id)
        if note is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "note not found")
        return note

    async def update_note(
        self,
        note_id: UUID,
        payload: NoteUpdate,
    ) -> NoteRead:
        data = payload.model_dump(exclude_unset=True)
        links_data = data.pop("links", None)
        checklist_provided = "checklist" in data
        data.pop("checklist", None)

        async with self.uow:
            note = await self.uow.notes.get_with_links(note_id)
            if note is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "note not found")

            if "is_resolved" in data:
                new_val = bool(data["is_resolved"])
                if new_val and not note.is_resolved:
                    note.resolved_at = datetime.now(UTC)
                elif not new_val:
                    note.resolved_at = None
                note.is_resolved = new_val
                data.pop("is_resolved", None)

            for k, v in data.items():
                setattr(note, k, v)

            if links_data is not None:
                await self.uow.notes.delete_links_for(note.id)
                for ld in (payload.links or []):
                    self.uow.notes.add(NoteLink(
                        note_id=note.id,
                        entity_type=ld.entity_type,
                        entity_id=ld.entity_id,
                        entity_key=ld.entity_key,
                        entity_label=ld.entity_label,
                    ))

            if checklist_provided:
                self._diff_checklist(note, payload.checklist or [])

            await self.uow.notes.flush()
            nid = note.id

        return await self._reload(nid)

    def _diff_checklist(self, note: Note, desired) -> None:
        """Привести чек-лист заметки к желаемому состоянию: обновить существующие
        пункты по id, создать новые (без id), удалить отсутствующие. Сохраняет
        done_at/done_by при стабильном статусе, проставляет/снимает при смене."""
        existing = {ci.id: ci for ci in (note.checklist or [])}
        keep_ids = {d.id for d in desired if d.id is not None}
        # удаляем пропавшие
        for ci in list(note.checklist or []):
            if ci.id not in keep_ids:
                note.checklist.remove(ci)
        # upsert
        for pos, d in enumerate(desired):
            position = d.position if d.position else pos
            if d.id is not None and d.id in existing:
                ci = existing[d.id]
                if d.is_done and not ci.is_done:
                    ci.done_at = datetime.now(UTC)
                elif not d.is_done and ci.is_done:
                    ci.done_at = None
                    ci.done_by_id = None
                ci.text = d.text
                ci.is_done = d.is_done
                ci.position = position
                ci.assignee_id = d.assignee_id
                ci.assignee_name = d.assignee_name
                ci.due_date = d.due_date
            else:
                note.checklist.append(NoteChecklistItem(
                    text=d.text,
                    is_done=d.is_done,
                    position=position,
                    assignee_id=d.assignee_id,
                    assignee_name=d.assignee_name,
                    due_date=d.due_date,
                    done_at=datetime.now(UTC) if d.is_done else None,
                ))

    # ─── delete ───────────────────────────────────────────────────

    async def delete_note(self, note_id: UUID) -> None:
        async with self.uow:
            note = await self.uow.notes.get_with_links(note_id)
            if note is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "note not found")
            await self.uow.notes.delete(note)
            await self.uow.notes.flush()

    # ─── checklist item (granular) ────────────────────────────────

    async def checklist_item_context(self, item_id: UUID):
        """Вернуть (company_id, note_id) родительской заметки для scope-check."""
        async with self.uow:
            item = await self.uow.notes.get_checklist_item(item_id)
            if item is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "checklist item not found")
            note = await self.uow.notes.get_with_links(item.note_id)
        return (note.company_id if note else None), item.note_id

    async def patch_checklist_item(
        self,
        item_id: UUID,
        patch: ChecklistItemPatch,
        *,
        actor_id: UUID,
    ) -> tuple[NoteRead, Optional[UUID]]:
        """Точечно обновить пункт. Возвращает (обновлённая заметка,
        id вновь назначенного ответственного или None)."""
        data = patch.model_dump(exclude_unset=True)
        newly_assigned: Optional[UUID] = None
        async with self.uow:
            item = await self.uow.notes.get_checklist_item(item_id)
            if item is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "checklist item not found")

            if "is_done" in data:
                nv = bool(data.pop("is_done"))
                if nv and not item.is_done:
                    item.done_at = datetime.now(UTC)
                    item.done_by_id = actor_id
                elif not nv:
                    item.done_at = None
                    item.done_by_id = None
                item.is_done = nv

            if "assignee_id" in data:
                new_a = data["assignee_id"]
                if new_a and new_a != item.assignee_id and new_a != actor_id:
                    newly_assigned = new_a

            for k, v in data.items():
                setattr(item, k, v)
            await self.uow.notes.flush()
            note_id = item.note_id

        note = await self._reload(note_id)
        return note, newly_assigned

    # ─── internal ─────────────────────────────────────────────────

    async def _reload(self, note_id: UUID) -> NoteRead:
        async with self.uow:
            note = await self.uow.notes.get_with_links(note_id)
            if note is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "note not found")
            return note
