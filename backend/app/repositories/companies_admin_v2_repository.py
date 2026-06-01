"""Data access for Companies+Sectors admin v2 (granular)."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company, CompanyYearOverride, Sector
from app.models.user import Group


class CompaniesAdminV2Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── companies ────────────────────────────────────────────────

    async def get_company_by_code(self, code: str) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).where(Company.code == code)
        )
        return res.scalar_one_or_none()

    async def get_company_id_by_code(self, code: str) -> Optional[UUID]:
        res = await self.session.execute(
            select(Company.id).where(Company.code == code)
        )
        return res.scalar_one_or_none()

    async def get_sector_id_by_code(self, code: str) -> Optional[UUID]:
        res = await self.session.execute(
            select(Sector.id).where(Sector.code == code)
        )
        return res.scalar_one_or_none()

    async def get_sector_code_by_id(self, sector_id: UUID) -> Optional[str]:
        res = await self.session.execute(
            select(Sector.code).where(Sector.id == sector_id)
        )
        return res.scalar_one_or_none()

    async def get_sector_by_id(self, sector_id: UUID) -> Optional[Sector]:
        res = await self.session.execute(
            select(Sector).where(Sector.id == sector_id)
        )
        return res.scalar_one_or_none()

    async def get_parent_code_by_id(self, parent_id: UUID) -> Optional[str]:
        res = await self.session.execute(
            select(Company.code).where(Company.id == parent_id)
        )
        return res.scalar_one_or_none()

    async def get_parent_id_for_cycle_check(self, current_id: UUID) -> Optional[UUID]:
        res = await self.session.execute(
            select(Company.parent_id).where(Company.id == current_id)
        )
        return res.scalar_one_or_none()

    async def count_children(self, parent_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(Company.id)).where(Company.parent_id == parent_id)
        )
        return int(res.scalar() or 0)

    async def count_year_overrides(self, company_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(CompanyYearOverride.id))
            .where(CompanyYearOverride.company_id == company_id)
        )
        return int(res.scalar() or 0)

    async def list_companies(
        self,
        *,
        sector_code: Optional[str],
        status_filter: Optional[str],
        only_active: bool,
        search: Optional[str],
    ):
        q = select(Company)
        conds = []
        if sector_code:
            s_id = await self.get_sector_id_by_code(sector_code)
            if s_id:
                conds.append(Company.sector_id == s_id)
        if status_filter:
            conds.append(Company.status == status_filter)
        if only_active:
            conds.append(Company.is_active.is_(True))
        if search:
            like = f"%{search.lower()}%"
            conds.append(
                func.lower(Company.code).like(like)
                | func.lower(Company.name_ru).like(like)
                | func.lower(Company.name_short).like(like)
            )
        if conds:
            q = q.where(and_(*conds))
        q = q.order_by(
            Company.is_pinned.desc(),
            Company.sort_order, Company.name_ru,
        )
        return list((await self.session.execute(q)).scalars().all())

    async def group_exists_by_code(self, code: str) -> bool:
        res = await self.session.execute(
            select(Group.id).where(Group.code == code)
        )
        return res.scalar_one_or_none() is not None

    # ─── year overrides ───────────────────────────────────────────

    async def list_year_overrides(self, company_id: UUID):
        res = await self.session.execute(
            select(CompanyYearOverride)
            .where(CompanyYearOverride.company_id == company_id)
            .order_by(CompanyYearOverride.year)
        )
        return list(res.scalars().all())

    async def delete_overrides_for_company(self, company_id: UUID) -> None:
        await self.session.execute(
            delete(CompanyYearOverride)
            .where(CompanyYearOverride.company_id == company_id)
        )

    # ─── hierarchy tree ───────────────────────────────────────────

    async def list_all_companies_for_tree(self):
        res = await self.session.execute(
            select(Company).order_by(Company.sort_order, Company.name_ru)
        )
        return list(res.scalars().all())

    async def sector_codes_map(self, ids: Sequence[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        res = await self.session.execute(
            select(Sector.id, Sector.code).where(Sector.id.in_(list(ids)))
        )
        return {sid: code for sid, code in res.all()}

    # ─── sectors ──────────────────────────────────────────────────

    async def list_sectors(self):
        res = await self.session.execute(
            select(Sector).order_by(Sector.sort_order, Sector.name_ru)
        )
        return list(res.scalars().all())

    async def get_sector_by_code(self, code: str) -> Optional[Sector]:
        res = await self.session.execute(
            select(Sector).where(Sector.code == code)
        )
        return res.scalar_one_or_none()

    async def count_companies_in_sector(self, sector_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(Company.id)).where(Company.sector_id == sector_id)
        )
        return int(res.scalar() or 0)

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()
