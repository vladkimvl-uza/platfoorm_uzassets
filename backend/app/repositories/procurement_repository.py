"""Procurement repository — все queries по `procurement_closures` + companies
lookup для enrichment. Никакой бизнес-логики (агрегации/расчётов): только I/O.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

try:
    from app.models.procurement import ProcurementClosure  # type: ignore
    HAS_CLOSURES = True
except ImportError:
    ProcurementClosure = None  # type: ignore
    HAS_CLOSURES = False

from app.models.company import Company


class ProcurementRepository:
    """Data-access for procurement_closures + companies/sectors lookups."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @property
    def closures_available(self) -> bool:
        return HAS_CLOSURES

    # ─── Read closures (filtered + benchmark-only) ────────────────

    async def list_closures(
        self,
        *,
        year: Optional[int] = None,
        company_id: Optional[UUID] = None,
        scope_company_ids: Optional[Sequence[UUID]] = None,
        benchmark_only: bool = True,
    ) -> list:
        """Closures по фильтрам. benchmark_only=True пропускает rows без
        market_avg/unit_price (только rows с реальным benchmark)."""
        if not HAS_CLOSURES or ProcurementClosure is None:
            return []
        q = select(ProcurementClosure)
        if benchmark_only:
            q = q.where(
                ProcurementClosure.market_avg.is_not(None),
                ProcurementClosure.unit_price.is_not(None),
            )
        if year is not None:
            q = q.where(ProcurementClosure.year == year)
        if company_id is not None:
            # Разрез одной компании (её карточка/воркспейс) — показываем закупки всегда, без rollup-фильтра.
            q = q.where(ProcurementClosure.company_id == company_id)
        else:
            # Сводная выборка по портфелю: демо/непрофильные компании не должны искажать портфельные цифры (рейтинг, KPI, средние по секторам).
            q = q.join(Company, Company.id == ProcurementClosure.company_id).where(
                Company.include_in_rollups.is_(True)
            )
            if scope_company_ids is not None:
                q = q.where(ProcurementClosure.company_id.in_(list(scope_company_ids)))
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def list_companies_with_sector(self, ids: Sequence[UUID]) -> list[Company]:
        if not ids:
            return []
        res = await self.session.execute(
            select(Company)
            .options(selectinload(Company.sector))
            .where(Company.id.in_(list(ids)))
            .where(Company.is_active.is_(True))
        )
        return list(res.scalars().all())

    async def available_years(self) -> list[int]:
        if not HAS_CLOSURES or ProcurementClosure is None:
            return []
        res = await self.session.execute(select(ProcurementClosure.year).distinct())
        return sorted({y for (y,) in res.all() if y is not None})

    # ─── Single closure (for editor) ──────────────────────────────

    async def get_closure(self, closure_id: UUID):
        if not HAS_CLOSURES or ProcurementClosure is None:
            return None
        res = await self.session.execute(
            select(ProcurementClosure).where(ProcurementClosure.id == closure_id)
        )
        return res.scalar_one_or_none()

    async def list_closures_by_product(self, product_code: str) -> list:
        if not HAS_CLOSURES or ProcurementClosure is None:
            return []
        res = await self.session.execute(
            select(ProcurementClosure).where(ProcurementClosure.product_code == product_code)
        )
        return list(res.scalars().all())

    async def refresh(self, row) -> None:
        await self.session.refresh(row)

    # ─── Clear closures (admin) ───────────────────────────────────

    async def clear_filtered(
        self,
        *,
        year: Optional[int] = None,
        source: Optional[str] = None,
    ) -> int:
        """Delete closures по year/source. Возвращает количество удалённых."""
        if not HAS_CLOSURES:
            return 0
        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        if year is not None:
            where_clauses.append("year = :year")
            params["year"] = year
        if source:
            where_clauses.append("extra->>'source' = :source")
            params["source"] = source
        if not where_clauses:
            raise ValueError("At least one filter required (year or source)")
        res = await self.session.execute(
            text(
                f"DELETE FROM procurement_closures "
                f"WHERE {' AND '.join(where_clauses)} RETURNING id"
            ),
            params,
        )
        return len(res.fetchall())

    # ─── Bulk import (parametrized SQL) ───────────────────────────

    async def bulk_insert(self, rows: list[dict], batch: int = 500) -> int:
        """Bulk-insert закупок. Принимает dict-rows (готовые к
        parametrized INSERT). Возвращает кол-во вставленных."""
        if not HAS_CLOSURES or not rows:
            return 0
        insert_sql = text("""
            INSERT INTO procurement_closures (
                id, company_id, year, closure_date,
                category_id, product_code, product_name,
                unit_price, market_avg, deviation_pct,
                unit, volume, total_amount, saved_amount,
                supplier_name, supplier_inn,
                contract_id, lot_id, platform, purchase_type, region, sector,
                is_clean, is_dirty, extra,
                created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :company_id, :year, :closure_date,
                :category_id, :product_code, :product_name,
                :unit_price, :market_avg, :deviation_pct,
                :unit, :volume, :total_amount, :saved_amount,
                :supplier_name, :supplier_inn,
                NULL, :lot_id, :platform, :purchase_type, :region, :sector,
                :is_clean, :is_dirty, CAST(:extra AS jsonb),
                NOW(), NOW()
            )
        """)
        inserted = 0
        buf: list[dict] = []
        for r in rows:
            # обратная совместимость: если importer не проставил флаги — считаем чистой
            r.setdefault("is_dirty", False)
            r.setdefault("is_clean", not r["is_dirty"])
            buf.append(r)
            if len(buf) >= batch:
                await self.session.execute(insert_sql, buf)
                inserted += len(buf)
                buf = []
        if buf:
            await self.session.execute(insert_sql, buf)
            inserted += len(buf)
        return inserted

    # ─── Companies map lookups for import ─────────────────────────

    async def get_companies_code_map(self) -> dict[str, UUID]:
        """Lowercase code → company_id, для xarid-imports."""
        res = await self.session.execute(text("SELECT id, code FROM companies"))
        return {(r.code or "").lower(): r.id for r in res.all()}

    async def get_sector_by_company_map(self) -> dict[UUID, str]:
        """company_id → sector.code (через JOIN), для прокидки в closures.sector."""
        res = await self.session.execute(text("""
            SELECT c.id, s.code AS sector_code
            FROM companies c LEFT JOIN sectors s ON s.id = c.sector_id
        """))
        return {r.id: r.sector_code for r in res.all()}
