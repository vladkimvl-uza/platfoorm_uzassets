"""Persistence layer for Directions lookup + admin CRUD (Pack 149)."""
from __future__ import annotations

from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Direction


class DirectionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, obj: Any) -> None:
        self._session.add(obj)

    async def delete(self, obj: Any) -> None:
        await self._session.delete(obj)

    async def refresh(self, obj: Any) -> None:
        await self._session.refresh(obj)

    async def list_all(self) -> Sequence[Direction]:
        return (await self._session.execute(
            select(Direction).order_by(Direction.sort_order, Direction.name_ru)
        )).scalars().all()

    async def get_by_id(self, direction_id: UUID) -> Optional[Direction]:
        return (await self._session.execute(
            select(Direction).where(Direction.id == direction_id)
        )).scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[Direction]:
        return (await self._session.execute(
            select(Direction).where(Direction.code == code)
        )).scalar_one_or_none()

    async def count_tasks_with_code(self, code: str) -> int:
        return int((await self._session.execute(
            text("SELECT count(*) FROM tasks WHERE extra->>'direction' = :c"),
            {"c": code},
        )).scalar() or 0)

    async def count_projects_with_code(self, code: str) -> int:
        return int((await self._session.execute(
            text("SELECT count(*) FROM projects WHERE extra->>'direction' = :c"),
            {"c": code},
        )).scalar() or 0)

    async def reassign_tasks(self, *, from_code: str, to_code: str) -> None:
        await self._session.execute(
            text("UPDATE tasks SET extra = jsonb_set(extra, '{direction}', "
                 "to_jsonb(:t::text)) WHERE extra->>'direction' = :c"),
            {"t": to_code, "c": from_code},
        )

    async def reassign_projects(self, *, from_code: str, to_code: str) -> None:
        await self._session.execute(
            text("UPDATE projects SET extra = jsonb_set(extra, '{direction}', "
                 "to_jsonb(:t::text)) WHERE extra->>'direction' = :c"),
            {"t": to_code, "c": from_code},
        )

    async def strip_tasks(self, code: str) -> None:
        await self._session.execute(
            text("UPDATE tasks SET extra = extra - 'direction' "
                 "WHERE extra->>'direction' = :c"),
            {"c": code},
        )

    async def strip_projects(self, code: str) -> None:
        await self._session.execute(
            text("UPDATE projects SET extra = extra - 'direction' "
                 "WHERE extra->>'direction' = :c"),
            {"c": code},
        )
