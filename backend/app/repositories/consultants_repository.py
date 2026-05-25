"""Data access for Consultants."""
from __future__ import annotations

from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board import Board
from app.models.company import Company, Direction, Sector
from app.models.consultant import Consultant, ConsultantAssignment
from app.models.task import Task


class ConsultantsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── consultants ──────────────────────────────────────────────

    async def list_active(self) -> list[Consultant]:
        res = await self.session.execute(
            select(Consultant)
            .where(Consultant.is_active == True)  # noqa: E712
            .order_by(Consultant.sort_order, Consultant.name_ru)
        )
        return list(res.scalars().all())

    async def list_all(self, *, include_inactive: bool) -> list[Consultant]:
        q = select(Consultant)
        if not include_inactive:
            q = q.where(Consultant.is_active == True)  # noqa: E712
        q = q.order_by(Consultant.sort_order, Consultant.name_ru)
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def get(self, consultant_id: UUID) -> Optional[Consultant]:
        res = await self.session.execute(
            select(Consultant).where(Consultant.id == consultant_id)
        )
        return res.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[Consultant]:
        res = await self.session.execute(
            select(Consultant).where(Consultant.code == code)
        )
        return res.scalar_one_or_none()

    async def count_assignments(self, consultant_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(ConsultantAssignment.id))
            .where(ConsultantAssignment.consultant_id == consultant_id)
        )
        return int(res.scalar() or 0)

    async def get_by_ids(self, ids: Sequence[UUID]) -> dict[Any, Consultant]:
        if not ids:
            return {}
        res = await self.session.execute(
            select(Consultant).where(Consultant.id.in_(list(ids)))
        )
        return {c.id: c for c in res.scalars().all()}

    # ─── tasks + assignments ──────────────────────────────────────

    async def available_task_years(self) -> list[int]:
        res = await self.session.execute(
            select(Task.portfolio_year).distinct()
            .where(Task.portfolio_year.is_not(None))
        )
        return sorted({r[0] for r in res.all() if r[0]}, reverse=True)

    async def list_active_tasks(
        self,
        *,
        year: Optional[int],
    ) -> list:
        q = (
            select(
                Task.id, Task.num, Task.title, Task.status, Task.due_date,
                Task.direction_id, Task.board_id, Task.portfolio_year,
                Task.is_archived,
            )
            .where(Task.is_archived == False)  # noqa: E712
        )
        if year:
            q = q.where(Task.portfolio_year == year)
        return list((await self.session.execute(q)).all())

    async def list_company_active_tasks(
        self,
        company_id: UUID,
        *,
        year: Optional[int],
    ) -> list:
        q = (
            select(
                Task.id, Task.num, Task.title, Task.status, Task.due_date,
                Task.portfolio_year,
            )
            .where(Task.company_id == company_id)
            .where(Task.is_archived == False)  # noqa: E712
        )
        if year:
            q = q.where(Task.portfolio_year == year)
        return list((await self.session.execute(q)).all())

    async def list_assignments_for_tasks(
        self,
        task_ids: Sequence[Any],
        *,
        include_source: bool = False,
    ):
        if not task_ids:
            return []
        cols = [ConsultantAssignment.task_id, ConsultantAssignment.consultant_id]
        if include_source:
            cols.append(ConsultantAssignment.source)
        res = await self.session.execute(
            select(*cols).where(ConsultantAssignment.task_id.in_(list(task_ids)))
        )
        return list(res.all())

    # ─── boards + sector colours ──────────────────────────────────

    async def boards_with_company(self, board_ids: Sequence[Any]):
        if not board_ids:
            return []
        res = await self.session.execute(
            select(Board.id, Board.name, Board.company_id)
            .where(Board.id.in_(list(board_ids)))
        )
        return list(res.all())

    async def company_sector_colors(
        self,
        company_ids: Sequence[Any],
    ) -> dict[Any, str]:
        if not company_ids:
            return {}
        res = await self.session.execute(
            select(Company.id, Sector.code, Sector.color_hex)
            .join(Sector, Sector.id == Company.sector_id)
            .where(Company.id.in_(list(company_ids)))
        )
        return {cid: scolor or "#888" for cid, _scode, scolor in res.all()}

    async def get_company(self, company_id: UUID) -> Optional[UUID]:
        res = await self.session.execute(
            select(Company.id).where(Company.id == company_id)
        )
        return res.scalar_one_or_none()

    # ─── directions ───────────────────────────────────────────────

    async def list_directions(self):
        res = await self.session.execute(
            select(Direction.id, Direction.code, Direction.name_ru)
        )
        return list(res.all())

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
