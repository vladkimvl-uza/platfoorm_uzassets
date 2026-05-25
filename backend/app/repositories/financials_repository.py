"""Persistence layer for the Financials Reports CRUD endpoints.

Scope: header/lines CRUD for the canonical `financial_reports` table only.
Detailed/NSBU/IFRS/HLF/Portfolio queries are still inlined in the route
pending follow-up extraction.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.financial import FinancialLine, FinancialReport


class FinancialsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── Mutation helpers ─────────────────────────────────────────

    def add(self, obj: Any) -> None:
        self._session.add(obj)

    async def delete(self, obj: Any) -> None:
        await self._session.delete(obj)

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, obj: Any) -> None:
        await self._session.refresh(obj)

    # ─── Reports queries ──────────────────────────────────────────

    async def get_report(self, report_id: UUID) -> Optional[FinancialReport]:
        return (await self._session.execute(
            select(FinancialReport).where(FinancialReport.id == report_id)
        )).scalar_one_or_none()

    async def get_company(self, company_id: UUID) -> Optional[Company]:
        return (await self._session.execute(
            select(Company).where(Company.id == company_id)
        )).scalar_one_or_none()

    async def get_company_code(self, company_id: UUID) -> Optional[str]:
        return (await self._session.execute(
            select(Company.code).where(Company.id == company_id)
        )).scalar_one_or_none()

    async def get_company_brief(self, company_id: UUID) -> Optional[Any]:
        return (await self._session.execute(
            select(Company.code, Company.name_short).where(Company.id == company_id)
        )).first()

    async def find_duplicate_report(
        self, *, company_id: UUID, year: int, quarter: Optional[int],
        standard: str, report_type: str,
    ) -> Optional[FinancialReport]:
        return (await self._session.execute(
            select(FinancialReport).where(
                FinancialReport.company_id == company_id,
                FinancialReport.year == year,
                FinancialReport.quarter == quarter,
                FinancialReport.standard == standard,
                FinancialReport.report_type == report_type,
            )
        )).scalar_one_or_none()

    async def list_reports(
        self,
        *,
        company_code: Optional[str] = None,
        year: Optional[int] = None,
        standard: Optional[str] = None,
        limit: int = 100,
        allowed_company_ids: Optional[set[UUID]] = None,
    ) -> Sequence[Any]:
        q = (
            select(
                FinancialReport,
                Company.code.label("co_code"),
                func.count(FinancialLine.id).label("lines_count"),
            )
            .join(Company, FinancialReport.company_id == Company.id)
            .outerjoin(FinancialLine, FinancialLine.report_id == FinancialReport.id)
            .group_by(FinancialReport.id, Company.code)
        )
        if allowed_company_ids is not None:
            q = q.where(FinancialReport.company_id.in_(allowed_company_ids))
        if company_code:
            q = q.where(func.lower(Company.code) == company_code.lower())
        if year:
            q = q.where(FinancialReport.year == year)
        if standard:
            q = q.where(FinancialReport.standard == standard)
        q = q.order_by(desc(FinancialReport.year), Company.code.asc()).limit(limit)
        return (await self._session.execute(q)).all()

    async def list_report_lines(self, report_id: UUID) -> List[FinancialLine]:
        return list((await self._session.execute(
            select(FinancialLine)
            .where(FinancialLine.report_id == report_id)
            .order_by(
                FinancialLine.sort_order.asc(),
                FinancialLine.line_code.asc(),
            )
        )).scalars().all())

    async def delete_report_lines(self, report_id: UUID) -> None:
        await self._session.execute(
            delete(FinancialLine).where(FinancialLine.report_id == report_id)
        )
