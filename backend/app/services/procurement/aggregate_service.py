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
    ProcurementCoverage,
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

        # Совокупный расход компании (лот-дедуп, ВСЕ типы) + разбивка т/у/р — для
        # шапки профиля. Привязываем к строкам рейтинга (sum_ref там = только
        # сопоставимый товарный benchmark, а не полный объём).
        from decimal import Decimal as _D
        co_tot: dict = {}
        for L in lots:
            cid = str(L["company_id"])
            d = co_tot.setdefault(cid, {"total": 0.0, "PRODUCT": 0.0, "SERVICE": 0.0, "WORK": 0.0, "lots": 0})
            d["total"] += L["spend"]
            d[L.get("ptype") if L.get("ptype") in ("PRODUCT", "SERVICE", "WORK") else "PRODUCT"] += L["spend"]
            d["lots"] += 1
        for r in rating:
            d = co_tot.get(str(r.company_id))
            if d:
                r.company_total_spend = _D(str(round(d["total"], 2)))
                r.goods_spend = _D(str(round(d["PRODUCT"], 2)))
                r.services_spend = _D(str(round(d["SERVICE"], 2)))
                r.works_spend = _D(str(round(d["WORK"], 2)))
                r.total_lots = d["lots"]

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
        coverage = _build_coverage(closures, lots, rating, kpis, avail_years)

        # Если есть товары без категории — добавляем мету «Без категории» (id=0),
        # чтобы сетка категорий показала ~45% спенда, ранее невидимого.
        categories = list(CATEGORIES_SEED)
        if any(getattr(c, "id", None) == 0 for c in cat_aggregates):
            categories.append(CategoryMeta(id=0, name="Без категории", short="Без кат.", unit="ед"))

        return ProcurementAggregate(
            year=year,
            sector_code=sector_code,
            has_data=bool(closures),
            coverage=coverage,
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


def _build_coverage(closures, lots, rating, kpis, avail_years) -> ProcurementCoverage:
    """Честный знаменатель экрана.

    Ключевые метрики строятся на сопоставимых позициях, а это малая часть
    спенда; экономия известна не у всех лотов; категория проставлена не везде;
    а весь массив может быть одним кварталом. Пока эти доли не показаны рядом
    с цифрами, экран читается как полная картина закупок портфеля.
    """
    total_spend = float(sum(l["spend"] for l in lots)) if lots else 0.0
    comparable_spend = float(sum(float(r.sum_ref) for r in rating))
    known_lots = sum(1 for l in lots if l.get("saved_known"))
    with_cat = sum(1 for c in closures if getattr(c, "category_id", None))
    dates = [getattr(c, "closure_date", None) for c in closures]
    dates = sorted(d for d in dates if d)
    disclosed = kpis.disclosed_supplier_pct

    return ProcurementCoverage(
        companies_total=len(rating),
        companies_with_data=len({str(l["company_id"]) for l in lots}),
        companies_comparable=sum(1 for r in rating if r.company_deviation is not None),
        closures_total=len(closures),
        lots_total=len(lots),
        spend_total=Decimal(str(round(total_spend, 2))),
        comparable_spend=Decimal(str(round(comparable_spend, 2))),
        comparable_spend_pct=(
            round(comparable_spend / total_spend * 100, 1) if total_spend > 0 else None
        ),
        saving_known_lots_pct=(round(known_lots / len(lots) * 100, 1) if lots else None),
        category_known_pct=(round(with_cat / len(closures) * 100, 1) if closures else None),
        supplier_known_pct=disclosed,
        period_from=str(dates[0]) if dates else None,
        period_to=str(dates[-1]) if dates else None,
        years=list(avail_years or []),
    )


def _empty_aggregate(year, sector_code) -> ProcurementAggregate:
    """Данных нет вовсе. has_data=False, чтобы экран показал пустое состояние,
    а не полосу нулей: раньше «0 сум · 0% · 0 поставщиков» выглядело как факт
    об идеальных закупках."""
    return ProcurementAggregate(
        year=year,
        sector_code=sector_code,
        has_data=False,
        kpis=ProcurementKpis(
            total_companies=0, clean_companies=0,
            total_closures=0, clean_closures=0,
            total_overpay_uzs=Decimal(0),
            above_market_pct=None, median_deviation_pct=None,
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
        # Раньше при отсутствии рынка подставлялась единица (market_avg=1) —
        # и строка получала отклонение в сотни тысяч процентов либо ровно −100%.
        # Нет базы сравнения → отклонения нет.
        market_avg = c.market_avg
        volume = c.volume or Decimal(0)
        dev_pct = (
            float((unit_price - market_avg) / market_avg * 100)
            if market_avg and market_avg > 0 else None
        )
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
