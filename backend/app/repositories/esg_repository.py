"""Data access for ESG domain."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agency_rating import AgencyRating
from app.models.company import Company, Sector
from app.models.esg import ESGIssue, ESGMaturityCell, ESGMetric, ESGYearTracked


class EsgRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── metrics ──────────────────────────────────────────────────

    async def list_metrics(
        self,
        *,
        year: Optional[int],
        sector_code: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
    ):
        # Деактивированные компании исключаем из портфельного ESG-overview.
        q = (select(ESGMetric)
             .join(Company, Company.id == ESGMetric.company_id)
             .where(Company.is_active.is_(True)))
        if year:
            q = q.where(ESGMetric.year == year)
        if sector_code:
            q = (q.join(Sector, Sector.id == Company.sector_id)
                  .where(Sector.code == sector_code))
        if scope_company_ids is not None:
            if not scope_company_ids:
                return []
            q = q.where(ESGMetric.company_id.in_(scope_company_ids))
        return list((await self.session.execute(q)).scalars().all())

    async def list_company_metrics(self, company_id: UUID, year: int):
        res = await self.session.execute(
            select(ESGMetric)
            .where(and_(ESGMetric.company_id == company_id, ESGMetric.year == year))
            .order_by(ESGMetric.pillar, ESGMetric.metric_code)
        )
        return list(res.scalars().all())

    async def get_metric_for_unique(self, company_id: UUID, year: int, metric_code: str):
        res = await self.session.execute(
            select(ESGMetric).where(and_(
                ESGMetric.company_id == company_id,
                ESGMetric.year == year,
                ESGMetric.metric_code == metric_code,
            ))
        )
        return res.scalar_one_or_none()

    async def get_metric(self, metric_id: UUID):
        res = await self.session.execute(
            select(ESGMetric).where(ESGMetric.id == metric_id)
        )
        return res.scalar_one_or_none()

    async def company_metric_years(self, company_id: UUID) -> list[int]:
        res = await self.session.execute(
            select(ESGMetric.year).distinct()
            .where(ESGMetric.company_id == company_id)
        )
        return sorted({r[0] for r in res.all() if r[0]}, reverse=True)

    async def all_metric_years(self) -> list[int]:
        res = await self.session.execute(
            select(ESGMetric.year).distinct()
            .where(ESGMetric.year.is_not(None))
        )
        return sorted({r[0] for r in res.all() if r[0]}, reverse=True)

    # ─── issues ───────────────────────────────────────────────────

    async def list_issues_for_overview(
        self,
        *,
        sector_code: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
    ):
        q = (select(ESGIssue)
             .join(Company, Company.id == ESGIssue.company_id)
             .where(Company.is_active.is_(True)))
        if sector_code:
            q = (q.join(Sector, Sector.id == Company.sector_id)
                  .where(Sector.code == sector_code))
        if scope_company_ids is not None:
            if not scope_company_ids:
                return []
            q = q.where(ESGIssue.company_id.in_(scope_company_ids))
        return list((await self.session.execute(q)).scalars().all())

    async def list_company_issues(self, company_id: UUID):
        res = await self.session.execute(
            select(ESGIssue).where(ESGIssue.company_id == company_id)
            .order_by(desc(ESGIssue.created_at))
        )
        return list(res.scalars().all())

    async def list_issues_filtered(
        self,
        *,
        company_id: Optional[UUID],
        pillar: Optional[str],
        severity: Optional[str],
        status: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
        limit: int,
    ):
        q = select(ESGIssue)
        if company_id:
            q = q.where(ESGIssue.company_id == company_id)
        if pillar:
            q = q.where(ESGIssue.pillar == pillar)
        if severity:
            q = q.where(ESGIssue.severity == severity)
        if status:
            q = q.where(ESGIssue.status == status)
        if scope_company_ids is not None:
            if not scope_company_ids:
                return []
            q = q.where(ESGIssue.company_id.in_(scope_company_ids))
        q = q.order_by(desc(ESGIssue.created_at)).limit(limit)
        return list((await self.session.execute(q)).scalars().all())

    async def get_issue(self, issue_id: UUID):
        res = await self.session.execute(
            select(ESGIssue).where(ESGIssue.id == issue_id)
        )
        return res.scalar_one_or_none()

    async def planned_rating_company_ids(
        self, *, scope_company_ids: Optional[Sequence[UUID]],
    ) -> set[UUID]:
        """Компании с отметкой «запланировано получение рейтинга» — служебная
        ячейка матрицы зрелости (dimension='rp', stage>=1). Питает planned_count
        доната покрытия (единое окно ESG сохраняет эту отметку)."""
        q = (
            select(ESGMaturityCell.company_id)
            .where(ESGMaturityCell.dimension == "rp", ESGMaturityCell.stage >= 1)
            .distinct()
        )
        if scope_company_ids is not None:
            if not scope_company_ids:
                return set()
            q = q.where(ESGMaturityCell.company_id.in_(scope_company_ids))
        return {cid for (cid,) in (await self.session.execute(q)).all()}

    # ─── companies / sectors ──────────────────────────────────────

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
        return list((await self.session.execute(q)).scalars().all())

    async def get_company_with_sector(
        self,
        company_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ):
        if scope_company_ids is not None and company_id not in scope_company_ids:
            return None
        res = await self.session.execute(
            select(Company).options(selectinload(Company.sector))
            .where(Company.id == company_id)
        )
        return res.scalar_one_or_none()

    async def get_company(self, company_id: UUID):
        res = await self.session.execute(
            select(Company).where(Company.id == company_id)
        )
        return res.scalar_one_or_none()

    async def companies_by_ids(self, ids: Sequence[UUID]):
        if not ids:
            return {}
        res = await self.session.execute(
            select(Company).where(Company.id.in_(ids))
        )
        return {c.id: c for c in res.scalars().all()}

    async def sectors_with_counts(self):
        res = await self.session.execute(
            select(Sector.code, func.count(Company.id))
            .join(Company, Company.sector_id == Sector.id)
            .where(Company.is_active.is_(True))
            .group_by(Sector.code)
        )
        return [{"code": r[0], "count": r[1]} for r in res.all()]

    # ─── ESG agency ratings ───────────────────────────────────────

    async def list_esg_ratings(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ):
        # Деактивированные компании исключаем; рейтинги-сироты (company_id NULL) — оставляем.
        q = (select(AgencyRating)
             .outerjoin(Company, Company.id == AgencyRating.company_id)
             .where(AgencyRating.is_esg == True,  # noqa: E712
                    or_(Company.is_active.is_(True), AgencyRating.company_id.is_(None))))
        if scope_company_ids is not None:
            if not scope_company_ids:
                return []
            q = q.where(AgencyRating.company_id.in_(scope_company_ids))
        return list((await self.session.execute(q)).scalars().all())

    # ─── tracked years ────────────────────────────────────────────

    async def active_tracked_years(self, company_id: UUID) -> list[int]:
        res = await self.session.execute(
            select(ESGYearTracked.year).where(and_(
                ESGYearTracked.company_id == company_id,
                ESGYearTracked.is_active == True,  # noqa: E712
            ))
        )
        return sorted({r[0] for r in res.all()}, reverse=True)

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
