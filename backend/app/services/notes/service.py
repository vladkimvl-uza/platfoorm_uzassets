"""Use cases for Notes (Smart Journal)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.note import Note, NoteLink
from app.schemas.notes import (
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
            await self.uow.notes.flush()
            nid = note.id

        return await self._reload(nid)

    # ─── delete ───────────────────────────────────────────────────

    async def delete_note(self, note_id: UUID) -> None:
        async with self.uow:
            note = await self.uow.notes.get_with_links(note_id)
            if note is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "note not found")
            await self.uow.notes.delete(note)
            await self.uow.notes.flush()

    # ─── internal ─────────────────────────────────────────────────

    async def _reload(self, note_id: UUID) -> NoteRead:
        async with self.uow:
            note = await self.uow.notes.get_with_links(note_id)
            if note is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "note not found")
            return note
