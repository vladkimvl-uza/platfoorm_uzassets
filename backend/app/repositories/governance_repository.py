"""Data access for Governance domain."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company, Sector
from app.models.governance import BoardMember, GovernanceData


class GovernanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── companies ────────────────────────────────────────────────

    async def list_companies(
        self,
        *,
        sector_code: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
    ):
        q = select(Company).options(selectinload(Company.sector))
        q = q.where(Company.is_active.is_(True))
        if sector_code:
            q = q.join(Sector, Sector.id == Company.sector_id).where(Sector.code == sector_code)
        if scope_company_ids is not None:
            if not scope_company_ids:
                return []
            q = q.where(Company.id.in_(scope_company_ids))
        return (await self.session.execute(q)).scalars().all()

    async def get_company(
        self,
        company_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ):
        if scope_company_ids is not None and company_id not in scope_company_ids:
            return None
        q = (select(Company).options(selectinload(Company.sector))
             .where(Company.id == company_id))
        return (await self.session.execute(q)).scalar_one_or_none()

    # ─── governance_data ──────────────────────────────────────────

    async def list_governance_data(
        self,
        *,
        year: Optional[int],
        sector_code: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
    ):
        q = select(GovernanceData)
        if year:
            q = q.where(GovernanceData.year == year)
        if sector_code:
            q = (q.join(Company, Company.id == GovernanceData.company_id)
                  .join(Sector, Sector.id == Company.sector_id)
                  .where(Sector.code == sector_code))
        if scope_company_ids is not None:
            if not scope_company_ids:
                return []
            q = q.where(GovernanceData.company_id.in_(scope_company_ids))
        return (await self.session.execute(q)).scalars().all()

    async def get_data_for(self, company_id: UUID, year: int):
        res = await self.session.execute(
            select(GovernanceData).where(and_(
                GovernanceData.company_id == company_id,
                GovernanceData.year == year,
            ))
        )
        return res.scalar_one_or_none()

    async def list_years_for(self, company_id: UUID) -> list[int]:
        res = await self.session.execute(
            select(GovernanceData.year)
            .where(GovernanceData.company_id == company_id)
            .order_by(desc(GovernanceData.year))
        )
        return [r[0] for r in res.all() if r[0]]

    async def all_data_years(self) -> list[int]:
        res = await self.session.execute(
            select(GovernanceData.year).distinct().where(GovernanceData.year.is_not(None))
        )
        return sorted({r[0] for r in res.all() if r[0]}, reverse=True)

    async def sectors_with_counts(self):
        res = await self.session.execute(
            select(Sector.code, func.count(Company.id))
            .join(Sector, Sector.id == Company.sector_id)
            .where(Company.sector_id.is_not(None))
            .group_by(Sector.code)
        )
        return [{"code": r[0], "count": r[1]} for r in res.all()]

    # ─── board members ────────────────────────────────────────────

    async def list_active_board_members(
        self,
        *,
        sector_code: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
    ):
        q = select(BoardMember)
        if sector_code:
            q = (q.join(Company, Company.id == BoardMember.company_id)
                  .join(Sector, Sector.id == Company.sector_id)
                  .where(Sector.code == sector_code))
        if scope_company_ids is not None:
            if not scope_company_ids:
                return []
            q = q.where(BoardMember.company_id.in_(scope_company_ids))
        today = datetime.now(UTC).date()
        q = q.where(
            (BoardMember.term_end_date == None)  # noqa: E711
            | (BoardMember.term_end_date >= today),
        )
        return (await self.session.execute(q)).scalars().all()

    async def list_company_board_members(
        self,
        company_id: UUID,
        *,
        include_past: bool = False,
    ):
        q = select(BoardMember).where(BoardMember.company_id == company_id)
        if not include_past:
            today = datetime.now(UTC).date()
            q = q.where(
                (BoardMember.term_end_date == None)  # noqa: E711
                | (BoardMember.term_end_date >= today),
            )
        q = q.order_by(asc(BoardMember.role_type), asc(BoardMember.full_name))
        return (await self.session.execute(q)).scalars().all()

    async def get_member(self, member_id: UUID) -> Optional[BoardMember]:
        res = await self.session.execute(
            select(BoardMember).where(BoardMember.id == member_id)
        )
        return res.scalar_one_or_none()

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
