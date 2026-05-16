"""Procurement Analysis routes — backend for the BETA tab.

Endpoint: GET /procurement/aggregate

Returns the full paCompute() result: KPIs + rating + per-category breakdown.

NOTE: This route depends on `ProcurementClosure` model existing. If your DB
doesn't have closures populated yet, the endpoint returns empty arrays
(safe — the frontend handles empty state gracefully).
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.access import allowed_company_ids, ensure_company_access, has_unrestricted_view
from app.database import get_db
from app.models.user import User
from app.schemas.procurement_analysis import (
    CategoryDeviation,
    CategoryMeta,
    ClosureRow,
    CompanyRatingRow,
    ProcurementAggregate,
    ProcurementKpis,
)

# Try to import ProcurementClosure model; if missing, endpoint returns empty
try:
    from app.models.procurement import ProcurementClosure  # type: ignore
    HAS_CLOSURES_MODEL = True
except ImportError:
    HAS_CLOSURES_MODEL = False
    ProcurementClosure = None  # type: ignore

# Try to import Company model
try:
    from app.models.company import Company  # type: ignore
except ImportError:
    Company = None  # type: ignore

router = APIRouter(prefix="/procurement", tags=["procurement-analysis"])


# =====================================================================
# 15 fixed procurement categories — verbatim from monolith
# =====================================================================

CATEGORIES_SEED: List[CategoryMeta] = [
    CategoryMeta(id=1,  name="Электротехника и кабельная продукция",  short="Электротехника"),
    CategoryMeta(id=2,  name="Металлопрокат и металлоизделия",        short="Металлопрокат"),
    CategoryMeta(id=3,  name="Трубы и фитинги",                       short="Трубы"),
    CategoryMeta(id=4,  name="Топливо и ГСМ",                         short="ГСМ"),
    CategoryMeta(id=5,  name="Химическое сырьё",                      short="Химия"),
    CategoryMeta(id=6,  name="Запчасти и комплектующие",              short="Запчасти"),
    CategoryMeta(id=7,  name="Строительные материалы",                short="Стройматериалы"),
    CategoryMeta(id=8,  name="Спецодежда и СИЗ",                      short="СИЗ"),
    CategoryMeta(id=9,  name="Канцтовары и расходные материалы",      short="Канцтовары"),
    CategoryMeta(id=10, name="ИТ-оборудование и ПО",                  short="IT"),
    CategoryMeta(id=11, name="Транспортные услуги",                   short="Транспорт"),
    CategoryMeta(id=12, name="Услуги связи",                          short="Связь"),
    CategoryMeta(id=13, name="Ремонтные услуги",                      short="Ремонт"),
    CategoryMeta(id=14, name="Консалтинг и аудит",                    short="Консалтинг"),
    CategoryMeta(id=15, name="Прочие услуги и работы",                short="Прочее"),
]


# =====================================================================
# Helpers (port from monolith paCompute)
# =====================================================================

def _color_for_sector(sector: Optional[str]) -> str:
    pal = {
        "mining":    "#7F77DD",
        "oilgas":    "#1D9E75",
        "energy":    "#EF9F27",
        "transport": "#378ADD",
        "other":     "#888780",
    }
    return pal.get((sector or "other").lower(), "#888780")


def _aggregate_rating(closures: list) -> List[CompanyRatingRow]:
    """Group closures by company × category, compute weighted-avg deviations,
    rank companies by company_deviation ascending (lower = better)."""
    if not closures:
        return []

    by_company: Dict[str, Dict] = {}

    for c in closures:
        co_id = str(c.company_id)
        if co_id not in by_company:
            by_company[co_id] = {
                "company_id": c.company_id,
                "company_name": getattr(c, "company_name", None) or co_id[:8],
                "company_sector": getattr(c, "company_sector", None) or "other",
                "company_color": _color_for_sector(getattr(c, "company_sector", None)),
                "cats": {},
                "sum_dev": Decimal(0),
                "sum_ref": Decimal(0),
                "above_count": 0,
            }
        co = by_company[co_id]

        # Skip dirty closures from KPI aggregates
        if getattr(c, "is_dirty", False):
            continue

        cat_id = c.category_id
        if cat_id not in co["cats"]:
            co["cats"][cat_id] = {
                "category_id": cat_id,
                "category_name": getattr(c, "category_name", "") or f"Категория {cat_id}",
                "category_short": (getattr(c, "category_name", "") or f"Кат {cat_id}")[:20],
                "sum_spend": Decimal(0),
                "sum_ref": Decimal(0),
                "closure_count": 0,
            }
        cat = co["cats"][cat_id]

        unit_price = c.unit_price or Decimal(0)
        market_avg = c.market_avg or Decimal(0)
        volume = c.volume or Decimal(0)

        spend = Decimal(unit_price) * Decimal(volume)
        ref = Decimal(market_avg) * Decimal(volume)

        cat["sum_spend"] += spend
        cat["sum_ref"] += ref
        cat["closure_count"] += 1

        co["sum_dev"] += (spend - ref)
        co["sum_ref"] += ref

    rating: List[CompanyRatingRow] = []
    for co_id, co in by_company.items():
        cat_devs: List[CategoryDeviation] = []
        above_count = 0
        for cat_id, cat in co["cats"].items():
            sum_dev = cat["sum_spend"] - cat["sum_ref"]
            dev_pct = float(sum_dev / cat["sum_ref"] * 100) if cat["sum_ref"] > 0 else 0.0
            cat_devs.append(
                CategoryDeviation(
                    category_id=cat_id,
                    category_name=cat["category_name"],
                    category_short=cat["category_short"],
                    sum_dev=sum_dev,
                    sum_ref=cat["sum_ref"],
                    deviation_pct=dev_pct,
                    closure_count=cat["closure_count"],
                )
            )
            if dev_pct > 0:
                above_count += 1

        company_dev_pct = float(co["sum_dev"] / co["sum_ref"] * 100) if co["sum_ref"] > 0 else 0.0

        # Sort cats — best (lowest dev_pct) and worst (highest dev_pct)
        sorted_by_dev = sorted(cat_devs, key=lambda x: x.deviation_pct)
        best_cats = sorted_by_dev[:3]
        worst_cats = list(reversed(sorted_by_dev[-3:]))

        rating.append(
            CompanyRatingRow(
                company_id=co["company_id"],
                company_name=co["company_name"],
                company_color=co["company_color"],
                company_sector=co["company_sector"],
                company_deviation=company_dev_pct,
                sum_dev=co["sum_dev"],
                sum_ref=co["sum_ref"],
                above_count=above_count,
                cat_count=len(cat_devs),
                cat_dev=cat_devs,
                best_cats=best_cats,
                worst_cats=worst_cats,
            )
        )

    rating.sort(key=lambda r: r.company_deviation)
    for i, r in enumerate(rating):
        r.rank = i + 1
    return rating


def _kpis_for(rating: List[CompanyRatingRow], all_closures: list) -> ProcurementKpis:
    clean = [c for c in all_closures if not getattr(c, "is_dirty", False)]
    above_count = sum(1 for r in rating if r.company_deviation > 0)
    total_overpay = sum(max(Decimal(0), r.sum_dev) for r in rating)
    above_pct = (above_count / len(rating) * 100) if rating else 0.0

    devs = sorted([r.company_deviation for r in rating])
    median_dev = devs[len(devs) // 2] if devs else 0.0

    return ProcurementKpis(
        total_companies=len(rating),
        clean_companies=len(rating),
        total_closures=len(all_closures),
        clean_closures=len(clean),
        total_overpay_uzs=total_overpay,
        above_market_pct=above_pct,
        median_deviation_pct=float(median_dev),
    )


# =====================================================================
# Routes
# =====================================================================

@router.get("/aggregate", response_model=ProcurementAggregate)
async def get_aggregate(
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    company_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns the full paCompute() aggregation."""
    if not HAS_CLOSURES_MODEL or ProcurementClosure is None:
        # Graceful degradation — frontend handles empty state
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
            rating=[],
            purchases=[],
            available_years=[],
            sectors=[],
            generated_at=datetime.now(timezone.utc),
        )

    # Scope filter: либо проверяем явный company_id, либо ограничиваем
    # выдачу для scoped users по allowed_companies. Пустой scope → пусто.
    if company_id is not None:
        await ensure_company_access(db, user, company_id)

    scope_ids = None
    if not has_unrestricted_view(user):
        scope_ids = await allowed_company_ids(db, user)
        if not scope_ids:
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
                generated_at=datetime.now(timezone.utc),
            )

    q = select(ProcurementClosure)
    if year is not None:
        q = q.where(ProcurementClosure.year == year)
    if company_id is not None:
        q = q.where(ProcurementClosure.company_id == company_id)
    elif scope_ids is not None:
        q = q.where(ProcurementClosure.company_id.in_(scope_ids))
    closures = (await db.execute(q)).scalars().all()

    # Enrich closures with company name/sector — best-effort
    if Company is not None and closures:
        co_ids = list({c.company_id for c in closures})
        co_q = await db.execute(select(Company).where(Company.id.in_(co_ids)))
        co_map = {str(c.id): c for c in co_q.scalars().all()}
        for c in closures:
            co = co_map.get(str(c.company_id))
            if co:
                # attach name+sector for aggregation
                setattr(c, "company_name", getattr(co, "name_short", None) or getattr(co, "name_ru", None) or "—")
                setattr(c, "company_sector", getattr(co, "sector_code", None))

    rating = _aggregate_rating(list(closures))
    kpis = _kpis_for(rating, list(closures))

    # Available years
    yr_q = await db.execute(select(ProcurementClosure.year).distinct())
    avail_years = sorted({y for (y,) in yr_q.all() if y is not None})

    # Build purchases array (capped to keep response sane)
    purchases: List[ClosureRow] = []
    for c in closures[:5000]:
        unit_price = c.unit_price or Decimal(0)
        market_avg = c.market_avg or Decimal(1)
        volume = c.volume or Decimal(0)
        dev_pct = float((unit_price - market_avg) / market_avg * 100) if market_avg else 0.0
        purchases.append(
            ClosureRow(
                id=c.id,
                company_id=c.company_id,
                company_name=getattr(c, "company_name", None),
                company_color=_color_for_sector(getattr(c, "company_sector", None)),
                company_sector=getattr(c, "company_sector", None),
                category_id=c.category_id,
                category_name=getattr(c, "category_name", "") or "—",
                category_unit=getattr(c, "unit", None) or "ед",
                product_code=getattr(c, "product_code", None),
                sub_product_code=getattr(c, "sub_product_code", None),
                product_name=getattr(c, "product_name", None),
                supplier=getattr(c, "supplier", None),
                unit_price=Decimal(unit_price),
                market_avg=Decimal(market_avg),
                volume=Decimal(volume),
                deviation_pct=dev_pct,
                deviation_abs=Decimal(unit_price - market_avg) * Decimal(volume),
                spread_pct=getattr(c, "spread_pct", None),
                is_dirty=getattr(c, "is_dirty", False),
                contract_date=getattr(c, "contract_date", None),
                year=getattr(c, "year", None),
            )
        )

    return ProcurementAggregate(
        year=year,
        sector_code=sector_code,
        kpis=kpis,
        categories=CATEGORIES_SEED,
        rating=rating,
        purchases=purchases,
        available_years=avail_years,
        sectors=[],
        generated_at=datetime.now(timezone.utc),
    )
