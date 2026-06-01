"""Data access for Company Library (MDM)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company
from app.models.company_library import (
    CompanyLibraryTab,
    CompanyLibraryView,
    FieldDefinition,
)


class CompanyLibraryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── companies ────────────────────────────────────────────────

    async def list_companies(
        self, *,
        sector: Optional[str], search: Optional[str],
        limit: int, offset: int,
    ):
        q = select(Company).options(selectinload(Company.sector))
        if sector:
            from app.models.sector import Sector
            q = q.join(Sector, Sector.id == Company.sector_id).where(Sector.code == sector)
        if search:
            needle = f"%{search.lower()}%"
            q = q.where(
                (Company.name_ru.ilike(needle))
                | (Company.name_short.ilike(needle))
                | (Company.inn.ilike(needle))
            )
        q = q.order_by(Company.sort_order, Company.name_ru).limit(limit).offset(offset)
        return list((await self.session.execute(q)).scalars().all())

    async def count_companies(
        self, *, sector: Optional[str], search: Optional[str],
    ) -> int:
        q = select(sa_func.count(Company.id))
        if sector:
            from app.models.sector import Sector
            q = q.join(Sector, Sector.id == Company.sector_id).where(Sector.code == sector)
        if search:
            needle = f"%{search.lower()}%"
            q = q.where(
                (Company.name_ru.ilike(needle))
                | (Company.name_short.ilike(needle))
                | (Company.inn.ilike(needle))
            )
        return int((await self.session.execute(q)).scalar_one() or 0)

    async def get_company_with_sector(self, company_id: UUID) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).where(Company.id == company_id)
            .options(selectinload(Company.sector))
        )
        return res.scalar_one_or_none()

    async def get_company(self, company_id: UUID) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).where(Company.id == company_id)
        )
        return res.scalar_one_or_none()

    async def list_all_companies(self) -> list[Company]:
        return list((await self.session.execute(select(Company))).scalars().all())

    # ─── field definitions ────────────────────────────────────────

    async def list_field_definitions(self) -> list[FieldDefinition]:
        res = await self.session.execute(
            select(FieldDefinition).order_by(
                FieldDefinition.sort_order, FieldDefinition.code,
            )
        )
        return list(res.scalars().all())

    async def list_field_definitions_filtered(
        self, *, scope_type: Optional[str],
    ) -> list[FieldDefinition]:
        q = select(FieldDefinition).order_by(
            FieldDefinition.sort_order, FieldDefinition.code,
        )
        if scope_type:
            q = q.where(FieldDefinition.scope_type == scope_type)
        return list((await self.session.execute(q)).scalars().all())

    async def get_field_definition(self, code: str) -> Optional[FieldDefinition]:
        res = await self.session.execute(
            select(FieldDefinition).where(FieldDefinition.code == code)
        )
        return res.scalar_one_or_none()

    # ─── library views (per-user) ─────────────────────────────────

    async def list_views(self, user_id: UUID) -> list[CompanyLibraryView]:
        res = await self.session.execute(
            select(CompanyLibraryView)
            .where(CompanyLibraryView.user_id == user_id)
            .order_by(
                CompanyLibraryView.is_default.desc(),
                CompanyLibraryView.created_at,
            )
        )
        return list(res.scalars().all())

    async def get_view(self, view_id: UUID) -> Optional[CompanyLibraryView]:
        res = await self.session.execute(
            select(CompanyLibraryView).where(CompanyLibraryView.id == view_id)
        )
        return res.scalar_one_or_none()

    async def list_default_views_other_than(
        self, user_id: UUID, exclude_view_id: Optional[UUID],
    ) -> list[CompanyLibraryView]:
        q = select(CompanyLibraryView).where(
            CompanyLibraryView.user_id == user_id,
            CompanyLibraryView.is_default.is_(True),
        )
        if exclude_view_id is not None:
            q = q.where(CompanyLibraryView.id != exclude_view_id)
        return list((await self.session.execute(q)).scalars().all())

    # ─── library tabs (global) ────────────────────────────────────

    async def list_tabs(self) -> list[CompanyLibraryTab]:
        res = await self.session.execute(
            select(CompanyLibraryTab).order_by(
                CompanyLibraryTab.sort_order, CompanyLibraryTab.code,
            )
        )
        return list(res.scalars().all())

    async def get_tab(self, code: str) -> Optional[CompanyLibraryTab]:
        res = await self.session.execute(
            select(CompanyLibraryTab).where(CompanyLibraryTab.code == code)
        )
        return res.scalar_one_or_none()

    # ─── audit ────────────────────────────────────────────────────

    async def list_audit_for_company(self, company_id: UUID, *, limit: int):
        try:
            from app.models.audit import AuditLog
        except Exception:
            return []
        res = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == str(company_id))
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())

    # ─── prefetch sources ─────────────────────────────────────────

    async def list_financial_reports(self, company_ids):
        try:
            from app.models.financial import FinancialReport
        except Exception:
            return []
        if not company_ids:
            return []
        q = (
            select(FinancialReport)
            .where(FinancialReport.company_id.in_(company_ids))
            .where(FinancialReport.report_type.in_(("PL", "BS")))
            .where(FinancialReport.standard == "IFRS")
        )
        return list((await self.session.execute(q)).scalars().all())

    async def list_financial_lines_for_reports(self, report_ids):
        try:
            from app.models.financial import FinancialLine
        except Exception:
            return []
        if not report_ids:
            return []
        q = select(FinancialLine).where(FinancialLine.report_id.in_(report_ids))
        return list((await self.session.execute(q)).scalars().all())

    async def list_agency_ratings(self, company_ids):
        try:
            from app.models.agency_rating import AgencyRating
        except Exception:
            return []
        if not company_ids:
            return []
        q = (
            select(AgencyRating)
            .where(AgencyRating.company_id.in_(company_ids))
            .order_by(
                AgencyRating.company_id, AgencyRating.agency,
                desc(AgencyRating.rating_date),
            )
        )
        return list((await self.session.execute(q)).scalars().all())

    async def get_latest_ifrs_report(
        self, company_id: UUID, report_type: str,
    ):
        try:
            from app.models.financial import FinancialReport
        except Exception:
            return None
        res = await self.session.execute(
            select(FinancialReport)
            .where(FinancialReport.company_id == company_id)
            .where(FinancialReport.report_type == report_type)
            .where(FinancialReport.standard == "IFRS")
            .order_by(FinancialReport.year.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def get_financial_line(self, report_id, line_code: str):
        try:
            from app.models.financial import FinancialLine
        except Exception:
            return None
        res = await self.session.execute(
            select(FinancialLine).where(
                FinancialLine.report_id == report_id,
                FinancialLine.line_code == line_code,
            )
        )
        return res.scalar_one_or_none()

    async def latest_agency_rating(self, company_id: UUID, agency_name: str):
        try:
            from app.models.agency_rating import AgencyRating
        except Exception:
            return None
        res = await self.session.execute(
            select(AgencyRating).where(
                AgencyRating.company_id == company_id,
                AgencyRating.agency == agency_name,
            ).order_by(AgencyRating.rating_date.desc().nulls_last()).limit(1)
        )
        return res.scalar_one_or_none()

    async def kpi_latest_year_map(self, company_ids):
        try:
            from app.models.bp_kpi import KpiManager
        except Exception:
            return {}
        if not company_ids:
            return {}
        q = (
            select(KpiManager.company_id, sa_func.max(KpiManager.year))
            .where(KpiManager.company_id.in_(company_ids))
            .group_by(KpiManager.company_id)
        )
        return {str(cid): yr for cid, yr in (await self.session.execute(q)).all()}

    async def list_kpi_managers(self, company_ids):
        try:
            from app.models.bp_kpi import KpiManager
        except Exception:
            return []
        if not company_ids:
            return []
        q = select(KpiManager).where(KpiManager.company_id.in_(company_ids))
        return list((await self.session.execute(q)).scalars().all())

    async def list_kpi_indicators(self, manager_ids):
        try:
            from app.models.bp_kpi import KpiIndicator
        except Exception:
            return []
        if not manager_ids:
            return []
        q = select(KpiIndicator).where(KpiIndicator.manager_id.in_(manager_ids))
        return list((await self.session.execute(q)).scalars().all())

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
