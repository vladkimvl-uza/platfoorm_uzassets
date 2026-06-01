"""Data access for Notes domain."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.note import Note, NoteLink


class NotesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_with_links(self, note_id: UUID) -> Optional[Note]:
        res = await self.session.execute(
            select(Note).where(Note.id == note_id).options(selectinload(Note.links))
        )
        return res.scalar_one_or_none()

    async def list_notes(
        self,
        *,
        conditions: list,
        pinned_first: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Note], int]:
        count_stmt = select(func.count(Note.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(Note).options(selectinload(Note.links))
        if conditions:
            stmt = stmt.where(and_(*conditions))
        if pinned_first:
            stmt = stmt.order_by(
                Note.is_pinned.desc(),
                Note.event_date.desc().nulls_last(),
                Note.created_at.desc(),
            )
        else:
            stmt = stmt.order_by(
                Note.event_date.desc().nulls_last(),
                Note.created_at.desc(),
            )
        stmt = stmt.limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def tag_counts(
        self,
        *,
        conditions: list,
        limit: Optional[int] = None,
    ):
        stmt = select(
            func.unnest(Note.tags).label("tag"),
            func.count().label("cnt"),
        )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.group_by(text("tag")).order_by(text("cnt DESC"))
        if limit is not None:
            stmt = stmt.limit(limit)
        return (await self.session.execute(stmt)).all()

    async def notes_by_entity(
        self,
        *,
        entity_type: str,
        entity_id: Optional[UUID],
        entity_key: Optional[str],
    ) -> list[Note]:
        link_conditions = [NoteLink.entity_type == entity_type]
        if entity_id is not None:
            link_conditions.append(NoteLink.entity_id == entity_id)
        if entity_key is not None:
            link_conditions.append(NoteLink.entity_key == entity_key)
        sub = (
            select(NoteLink.note_id)
            .where(and_(*link_conditions))
            .distinct()
            .scalar_subquery()
        )
        stmt = (
            select(Note)
            .where(Note.id.in_(sub))
            .options(selectinload(Note.links))
            .order_by(
                Note.is_pinned.desc(),
                Note.event_date.desc().nulls_last(),
                Note.created_at.desc(),
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_links_for(self, note_id: UUID) -> None:
        await self.session.execute(delete(NoteLink).where(NoteLink.note_id == note_id))

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    @staticmethod
    def search_predicates(query: str):
        like = f"%{query.strip()}%"
        return or_(Note.title.ilike(like), Note.body.ilike(like))
