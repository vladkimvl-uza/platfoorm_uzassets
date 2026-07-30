"""Data access for Companies + Sectors."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company, Sector
from app.models.financial import FinancialLine, FinancialReport
from app.models.governance import GovernanceData
from app.models.user import Group


class CompaniesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── companies ────────────────────────────────────────────────

    async def list_companies(
        self,
        *,
        active_only: bool,
        custom_only: Optional[bool],
        sector_code: Optional[str],
        search: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
        sort_by: str,
        sort_dir: str,
        limit: int,
        offset: int,
        hidden_for_year: Optional[int] = None,
    ) -> tuple[list[Company], int]:
        q = select(Company).options(selectinload(Company.sector))
        if active_only:
            q = q.where(Company.is_active.is_(True))
        if hidden_for_year is not None:
            # Исключаем компании, у которых этот год в hidden_years (NULL — видна).
            q = q.where(or_(
                Company.hidden_years.is_(None),
                ~Company.hidden_years.contains([hidden_for_year]),
            ))
        if custom_only is not None:
            q = q.where(Company.is_custom.is_(custom_only))
        if sector_code:
            q = q.join(Sector, Company.sector_id == Sector.id).where(Sector.code == sector_code.lower())
        if search:
            s = f"%{search.strip().lower()}%"
            q = q.where(or_(
                func.lower(Company.code).like(s),
                func.lower(Company.name_ru).like(s),
                func.lower(Company.name_short).like(s),
                func.lower(Company.name_uz).like(s),
                func.lower(Company.name_uz_cyr).like(s),
                func.lower(Company.name_en).like(s),
            ))
        if scope_company_ids is not None:
            if not scope_company_ids:
                q = q.where(Company.id == None)  # noqa: E711
            else:
                q = q.where(Company.id.in_(scope_company_ids))

        total = (await self.session.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        sort_col_map = {
            "sort_order": Company.sort_order,
            "code":       Company.code,
            "name_ru":    Company.name_ru,
        }
        sort_col = sort_col_map.get(sort_by, Company.sort_order)
        q = q.order_by(
            asc(sort_col) if sort_dir == "asc" else desc(sort_col),
            Company.code,
        )
        q = q.limit(limit).offset(offset)
        rows = (await self.session.execute(q)).scalars().all()
        return list(rows), total

    async def get_by_code(self, code: str) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).where(func.lower(Company.code) == code.lower())
            .options(selectinload(Company.sector))
        )
        return res.scalar_one_or_none()

    async def get_by_code_lite(self, code: str) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).where(func.lower(Company.code) == code.lower())
        )
        return res.scalar_one_or_none()

    # ─── enrichments for list view ────────────────────────────────

    async def latest_financials_by_companies(
        self,
        company_ids: Sequence[UUID],
    ) -> dict[str, tuple[int, Optional[float]]]:
        if not company_ids:
            return {}
        # P0 (аудит фин-источников): line_code в БД — 'revenue' (lowercase),
        # раньше искали 'REVENUE' → latest_revenue был вечно пуст. Плюс дубли
        # detailed-слоя отфильтрованы (is_detailed=False — summary-канон).
        fin_q = (
            select(
                FinancialReport.company_id,
                FinancialReport.year,
                FinancialLine.value,
            )
            .join(FinancialLine, FinancialLine.report_id == FinancialReport.id)
            .where(
                FinancialReport.company_id.in_(company_ids),
                FinancialReport.report_type == "PL",
                FinancialReport.is_detailed.is_(False),
                FinancialLine.line_code == "revenue",
            )
            .order_by(FinancialReport.company_id, desc(FinancialReport.year))
        )
        out: dict[str, tuple[int, Optional[float]]] = {}
        for cid, year, value in (await self.session.execute(fin_q)).all():
            key = str(cid)
            # первый ряд на компанию = самый свежий год (сортировка year DESC);
            # раньше сравнивали сырой UUID с str-ключами → всегда перезапись,
            # и «последний» (самый старый) год побеждал.
            if key not in out:
                out[key] = (year, value)
        return out

    async def latest_gov_scores_by_companies(
        self,
        company_ids: Sequence[UUID],
    ) -> dict[str, int]:
        if not company_ids:
            return {}
        gov_q = (
            select(GovernanceData.company_id, GovernanceData.year, GovernanceData.payload)
            .where(GovernanceData.company_id.in_(company_ids))
            .order_by(GovernanceData.company_id, desc(GovernanceData.year))
        )
        out: dict[str, int] = {}
        for cid, _year, payload in (await self.session.execute(gov_q)).all():
            cid_str = str(cid)
            if cid_str not in out and isinstance(payload, dict):
                score = payload.get("score")
                if isinstance(score, int | float):
                    out[cid_str] = int(score)
        return out

    # ─── company detail subqueries ────────────────────────────────

    async def list_company_financial_reports(self, company_id: UUID):
        q = (
            select(FinancialReport)
            .where(FinancialReport.company_id == company_id)
            .options(selectinload(FinancialReport.lines))
            .order_by(desc(FinancialReport.year),
                      FinancialReport.quarter.asc().nulls_first())
        )
        return list((await self.session.execute(q)).scalars().all())

    async def list_company_governance(self, company_id: UUID):
        q = (
            select(GovernanceData)
            .where(GovernanceData.company_id == company_id)
            .order_by(desc(GovernanceData.year))
        )
        return list((await self.session.execute(q)).scalars().all())

    async def list_company_financial_reports_filtered(
        self,
        company_id: UUID,
        *,
        standard: Optional[str],
        year: Optional[int],
    ):
        q = select(FinancialReport).where(FinancialReport.company_id == company_id)
        if standard:
            q = q.where(FinancialReport.standard == standard)
        if year:
            q = q.where(FinancialReport.year == year)
        return list((await self.session.execute(q)).scalars().all())

    # ─── group lookup for company create ──────────────────────────

    async def group_exists_by_code(self, code: str) -> bool:
        res = await self.session.execute(
            select(Group.id).where(Group.code == code)
        )
        return res.scalar_one_or_none() is not None

    # ─── sectors ──────────────────────────────────────────────────

    async def list_sectors(self):
        return list((await self.session.execute(
            select(Sector).order_by(Sector.sort_order)
        )).scalars().all())

    async def list_sectors_with_counts(self):
        q = (
            select(Sector, func.count(Company.id).label("cnt"))
            .outerjoin(Company,
                       (Company.sector_id == Sector.id) & (Company.is_active.is_(True)))
            .group_by(Sector.id)
            .order_by(Sector.sort_order)
        )
        return (await self.session.execute(q)).all()

    async def get_sector_by_code(self, code: str) -> Optional[Sector]:
        res = await self.session.execute(
            select(Sector).where(Sector.code == code)
        )
        return res.scalar_one_or_none()

    async def count_active_companies_in_sector(self, sector_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count()).select_from(Company)
            .where(Company.sector_id == sector_id, Company.is_active.is_(True))
        )
        return int(res.scalar_one() or 0)

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
