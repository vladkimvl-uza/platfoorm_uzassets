"""Procurement aggregate service — read-only `get_aggregate` use-case.

Получает scope (year, sector, company_id) → возвращает полный
`ProcurementAggregate` (KPIs + rating + product breakdown + closures).
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.schemas.procurement_analysis import (
    CategoryMeta,
    ClosureRow,
    ProcurementAggregate,
    ProcurementKpis,
    ProcurementMeta,
)
from app.services.procurement._aggregators import (
    CATEGORIES_SEED,
    aggregate_concentration,
    aggregate_methods,
    aggregate_platforms,
    aggregate_products,
    aggregate_rating,
    aggregate_suppliers,
    aggregate_works_services,
    color_for_sector,
    compute_kpis,
    dedup_lots,
    norm_product_type,
    sector_family,
)
from app.uow.ports import UnitOfWorkABC


class ProcurementAggregateService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def get_aggregate(
        self,
        *,
        year: Optional[int] = None,
        sector_code: Optional[str] = None,
        company_id: Optional[UUID] = None,
        scope_company_ids: Optional[list[UUID]] = None,
    ) -> ProcurementAggregate:
        """Build ProcurementAggregate per filters. Empty scope/no-model → empty result."""
        async with self.uow:
            if not self.uow.procurement.closures_available:
                return _empty_aggregate(year, sector_code)

            # Empty scope (user без allowed companies) → пустой результат сразу
            if scope_company_ids is not None and len(scope_company_ids) == 0:
                return _empty_aggregate(year, sector_code)

            closures = await self.uow.procurement.list_closures(
                year=year,
                company_id=company_id,
                scope_company_ids=scope_company_ids,
                benchmark_only=True,
            )

            # Enrich with company name/sector — best-effort
            if closures:
                co_ids = list({c.company_id for c in closures})
                companies = await self.uow.procurement.list_companies_with_sector(co_ids)
                co_map = {str(c.id): c for c in companies}
                for c in closures:
                    co = co_map.get(str(c.company_id))
                    if co:
                        c.company_name = getattr(co, "name_short", None) or getattr(co, "name_ru", None) or "—"
                        sec = getattr(co, "sector", None)
                        c.company_sector = getattr(sec, "code", None) if sec else None

            avail_years = await self.uow.procurement.available_years()

        # Живой фильтр по сектору (раньше был мёртвым echo-параметром)
        if sector_code:
            fam = sector_family(sector_code)
            closures = [c for c in closures if sector_family(getattr(c, "company_sector", None)) == fam]

        closures = list(closures)

        # Pure aggregations (вне `async with`, без I/O)
        rating = aggregate_rating(closures)
        products_by_code, cat_aggregates = aggregate_products(closures)
        lots = dedup_lots(closures)
        total_spend = sum(l["spend"] for l in lots)
        undisclosed = sum(l["spend"] for l in lots if l["supplier_key"] == "(не указан)")
        supplier_count = len({l["supplier_key"] for l in lots if l["supplier_key"] != "(не указан)"})

        suppliers_top, suppliers_cross, suppliers_expensive, cross_share_pct = aggregate_suppliers(
            lots, closures, products_by_code, total_spend
        )
        methods = aggregate_methods(lots, total_spend)
        platforms = aggregate_platforms(lots, total_spend)
        concentration = aggregate_concentration(lots)
        works_services = aggregate_works_services(lots)
        kpis = compute_kpis(
            rating, closures, lots, products_by_code,
            undisclosed_spend=undisclosed, supplier_count=supplier_count,
            cross_supplier_pct=cross_share_pct,
        )
        purchases = _build_purchases(closures)

        # Если есть товары без категории — добавляем мету «Без категории» (id=0),
        # чтобы сетка категорий показала ~45% спенда, ранее невидимого.
        categories = list(CATEGORIES_SEED)
        if any(getattr(c, "id", None) == 0 for c in cat_aggregates):
            categories.append(CategoryMeta(id=0, name="Без категории", short="Без кат.", unit="ед"))

        return ProcurementAggregate(
            year=year,
            sector_code=sector_code,
            kpis=kpis,
            categories=categories,
            category_aggregates=cat_aggregates,
            products_by_code=products_by_code,
            rating=rating,
            purchases=purchases,
            suppliers_top=suppliers_top,
            suppliers_cross=suppliers_cross,
            suppliers_expensive=suppliers_expensive,
            supplier_concentration=concentration,
            methods=methods,
            platforms=platforms,
            works_services=works_services,
            available_years=avail_years,
            sectors=[
                {"code": "mining", "label": "Горно-металлургический"},
                {"code": "oilgas", "label": "Нефтегаз"},
                {"code": "energy", "label": "Энергетика"},
                {"code": "transport", "label": "Транспорт и связь"},
                {"code": "chemistry", "label": "Химия"},
                {"code": "other", "label": "Прочие"},
            ],
            meta=ProcurementMeta(source="procurementContracts"),
            generated_at=datetime.now(UTC),
        )


def _empty_aggregate(year, sector_code) -> ProcurementAggregate:
    return ProcurementAggregate(
        year=year,
        sector_code=sector_code,
        kpis=ProcurementKpis(
            total_companies=0, clean_companies=0,
            total_closures=0, clean_closures=0,
            total_overpay_uzs=Decimal(0),
            above_market_pct=0.0, median_deviation_pct=0.0,
        ),
        categories=CATEGORIES_SEED,
        rating=[], purchases=[], available_years=[], sectors=[],
        generated_at=datetime.now(UTC),
    )


def _build_purchases(closures, cap: int = 15000) -> list[ClosureRow]:
    """Materialise ClosureRow DTOs (cap at 15k для performance)."""
    out: list[ClosureRow] = []
    for c in closures[:cap]:
        unit_price = c.unit_price or Decimal(0)
        market_avg = c.market_avg or Decimal(1)
        volume = c.volume or Decimal(0)
        dev_pct = float((unit_price - market_avg) / market_avg * 100) if market_avg else 0.0
        out.append(ClosureRow(
            id=c.id,
            company_id=c.company_id,
            company_name=getattr(c, "company_name", None),
            company_color=color_for_sector(getattr(c, "company_sector", None)),
            company_sector=getattr(c, "company_sector", None),
            category_id=c.category_id,
            category_name=getattr(c, "category_name", "") or "—",
            category_unit=getattr(c, "unit", None) or "ед",
            product_code=getattr(c, "product_code", None),
            sub_product_code=getattr(c, "sub_product_code", None),
            product_name=getattr(c, "product_name", None),
            product_type=norm_product_type((getattr(c, "extra", None) or {}).get("product_type"), getattr(c, "unit", None)),
            supplier=getattr(c, "supplier_name", None),
            supplier_inn=getattr(c, "supplier_inn", None),
            unit_price=Decimal(unit_price),
            market_avg=Decimal(market_avg),
            volume=Decimal(volume),
            deviation_pct=dev_pct,
            deviation_abs=Decimal(unit_price - market_avg) * Decimal(volume),
            spread_pct=getattr(c, "spread_pct", None),
            is_dirty=getattr(c, "is_dirty", False),
            contract_date=getattr(c, "contract_date", None),
            year=getattr(c, "year", None),
            conclusion_text=getattr(c, "conclusion_text", None),
            conclusion_status=getattr(c, "conclusion_status", None),
            conclusion_date=getattr(c, "conclusion_date", None),
            conclusion_author_name=getattr(c, "conclusion_author_name", None),
        ))
    return out
