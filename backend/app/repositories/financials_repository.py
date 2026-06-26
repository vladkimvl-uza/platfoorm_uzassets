"""Persistence layer for the Financials Reports CRUD endpoints.

Scope: header/lines CRUD for the canonical `financial_reports` table only.
Detailed/NSBU/IFRS/HLF/Portfolio queries are still inlined in the route
pending follow-up extraction.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional
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

    async def list_report_lines(self, report_id: UUID) -> list[FinancialLine]:
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

    # ─── HLF / Portfolio helpers ─────────────────────────────────

    async def list_all_companies(self) -> Sequence[Any]:
        return (await self._session.execute(
            select(Company).where(Company.is_active.is_(True))
        )).scalars().all()

    async def find_company_by_code(self, code: str) -> Optional[Company]:
        """Resolve a company by its code ИЛИ по ИНН.

        Интеграторы тянут данные по ИНН — путь `{code}` принимает и код («res»),
        и ИНН («306350099»). Коллизий нет: коды — слаги, ИНН — 9 цифр.
        """
        from sqlalchemy import func
        ident = (code or "").strip()
        return (await self._session.execute(
            select(Company)
            .where(
                (func.lower(Company.code) == ident.lower())
                | (Company.inn == ident)
            )
            .limit(1)
        )).scalars().first()

    async def count_companies(
        self, *, allowed_company_ids: Optional[set[UUID]] = None
    ) -> int:
        from sqlalchemy import func
        q = select(func.count(Company.id))
        if allowed_company_ids is not None:
            q = q.where(Company.id.in_(list(allowed_company_ids)))
        return int((await self._session.execute(q)).scalar() or 0)

    async def list_hlf_blobs(
        self, *, allowed_company_ids: Optional[set[UUID]] = None
    ) -> dict[str, dict]:
        """Return ``{company_code: hlf_dict}`` for active companies that have
        a stored High-Level Financials blob in ``extra["hlf"]``.

        Used by the portfolio summary to inject cash-flow metrics (CFO/CFI/
        CFF/dividends), which live in HLF rather than in ``financial_lines``.
        """
        q = select(Company.code, Company.extra).where(
            Company.is_active.is_(True),
            Company.extra.isnot(None),
            Company.extra.has_key("hlf"),  # noqa: W601 (JSONB ? operator)
        )
        if allowed_company_ids is not None:
            q = q.where(Company.id.in_(list(allowed_company_ids)))
        out: dict[str, dict] = {}
        for code, extra in (await self._session.execute(q)).all():
            if not code or not isinstance(extra, dict):
                continue
            hlf = extra.get("hlf")
            if isinstance(hlf, dict):
                out[code] = hlf
        return out

    async def list_sectors_map(self) -> dict[UUID, str]:
        from app.models.company import Sector
        rows = (await self._session.execute(
            select(Sector.id, Sector.code)
        )).all()
        return {row[0]: row[1] for row in rows}

    async def list_year_registry_rates(self) -> dict[int, dict[str, float]]:
        from app.models.year_registry import YearRegistry
        rows = (await self._session.execute(
            select(
                YearRegistry.year,
                YearRegistry.usd_rate,
                YearRegistry.eur_rate,
            )
        )).all()
        return {
            int(r.year): {
                "USD": float(r.usd_rate) if r.usd_rate is not None else 0.0,
                "EUR": float(r.eur_rate) if r.eur_rate is not None else 0.0,
            }
            for r in rows
        }

    async def query_portfolio_rows(
        self,
        *,
        standard: str,
        year_list: list[int],
        currency: Optional[str],
        allowed_company_ids: Optional[set[UUID]] = None,
    ) -> Sequence[Any]:
        """Return portfolio rows with optional currency filter.

        Caller is responsible for retry logic (case-insensitive,
        no-filter fallback). Pass `currency=None` to drop the filter.
        """
        from sqlalchemy import func as _func
        base = (
            select(
                Company.id.label("co_id"),
                Company.code.label("co_code"),
                Company.name_ru.label("co_name"),
                Company.name_short.label("co_short"),
                FinancialReport.year.label("year"),
                FinancialReport.report_type.label("rtype"),
                FinancialReport.unit_scale.label("scale"),
                FinancialReport.currency.label("rcurrency"),
                Company.sector_id.label("sector_id"),
                FinancialLine.line_code.label("code"),
                FinancialLine.parent_code.label("parent_code"),
                FinancialLine.value.label("val"),
            )
            .join(FinancialReport, FinancialReport.company_id == Company.id)
            .join(FinancialLine, FinancialLine.report_id == FinancialReport.id)
            .where(
                FinancialReport.standard == standard,
                FinancialReport.year.in_(year_list),
                FinancialReport.report_type.in_(["PL", "BS", "CF"]),
            )
        )
        if allowed_company_ids is not None:
            base = base.where(Company.id.in_(allowed_company_ids))
        if currency == "__case_insensitive__":
            # Caller already used canonical filter; retry case-insensitively
            raise ValueError("use currency='upper:X' instead")
        if currency:
            if currency.startswith("upper:"):
                target = currency.split(":", 1)[1]
                base = base.where(
                    _func.upper(FinancialReport.currency) == target
                )
            else:
                base = base.where(FinancialReport.currency == currency)
        return (await self._session.execute(base)).all()
