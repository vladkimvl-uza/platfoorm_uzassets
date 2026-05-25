"""Pure-function aggregators для procurement_analysis. Вынесены в отдельный
module — чтобы можно было unit-тестировать с fixture-closures без БД, и
переиспользовать из других контекстов (например AI-tools).
"""
from __future__ import annotations

import statistics
from decimal import Decimal
from typing import Dict, List, Optional

from app.schemas.procurement_analysis import (
    CategoryAggregate,
    CategoryDeviation,
    CategoryMeta,
    CompanyRatingRow,
    ProcurementKpis,
    ProductAgg,
)

# 15 fixed categories — verbatim from monolith (Ф-59 decree). xarid xlsx
# тагирует rows с этими IDs в "Category" column, имена должны совпадать.
CATEGORIES_SEED: List[CategoryMeta] = [
    CategoryMeta(id=1,  name="Офисная бумага",                       short="Бумага",     unit="пачка"),
    CategoryMeta(id=2,  name="Канцелярские товары",                  short="Канц.",      unit="набор"),
    CategoryMeta(id=3,  name="Компьютеры и периферия",               short="ПК",         unit="шт"),
    CategoryMeta(id=4,  name="Картриджи и расходники",               short="Картр.",     unit="шт"),
    CategoryMeta(id=5,  name="СИЗ и спецодежда",                     short="СИЗ",        unit="комплект"),
    CategoryMeta(id=6,  name="Офисная мебель",                       short="Мебель",     unit="шт"),
    CategoryMeta(id=7,  name="Гигиена и чистящие средства",          short="Гигиена",    unit="л"),
    CategoryMeta(id=8,  name="Продукты питания",                     short="Питание",    unit="кг"),
    CategoryMeta(id=9,  name="Топливо-смазочные материалы",          short="ТСМ",        unit="л"),
    CategoryMeta(id=10, name="Запчасти для автотранспорта",          short="Запч.",      unit="шт"),
    CategoryMeta(id=11, name="Стройматериалы",                       short="Стр-во",     unit="т"),
    CategoryMeta(id=12, name="Освещение и электротехника",           short="Свет",       unit="шт"),
    CategoryMeta(id=13, name="Кондиционеры и вентиляция",            short="Конд.",      unit="шт"),
    CategoryMeta(id=14, name="Связь и телекоммуникации",             short="Связь",      unit="шт"),
    CategoryMeta(id=15, name="Лицензии на ПО",                       short="ПО",         unit="лиц"),
]


def color_for_sector(sector: Optional[str]) -> str:
    """Sector code → UzAssets brand color. Поддерживает оба варианта кодов
    (короткие и длинные) — БД хранит длинные (`mining_metallurgy`)."""
    pal = {
        "mining":                   "#7F77DD",
        "mining_metallurgy":        "#7F77DD",
        "metallurgy":               "#7F77DD",
        "oilgas":                   "#1D9E75",
        "oil_gas":                  "#1D9E75",
        "energy":                   "#EF9F27",
        "transport":                "#378ADD",
        "transport_communications": "#378ADD",
        "telecom":                  "#378ADD",
        "chemistry":                "#888780",
        "other":                    "#888780",
    }
    return pal.get((sector or "other").lower(), "#888780")


# ═══ Aggregators (pure functions) ═══════════════════════════════════

def aggregate_products(
    closures: list,
) -> tuple[Dict[str, ProductAgg], List[CategoryAggregate]]:
    """Per-product aggregation (productsByCode) + per-category buckets.

    Quality bands (monolith line 21433): clean<200% spread, wide 200-1000%, dirty>1000%.
    """
    by_code: Dict[str, list] = {}
    for c in closures:
        if not c.product_code:
            continue
        by_code.setdefault(c.product_code, []).append(c)

    products: Dict[str, ProductAgg] = {}
    for code, rows in by_code.items():
        prices = [float(r.unit_price) for r in rows if r.unit_price]
        if not prices:
            continue
        min_p = min(prices)
        max_p = max(prices)
        avg_p = float(statistics.median(prices))
        spread_pct = ((max_p - min_p) / min_p * 100) if min_p > 0 else 0.0
        total_spend = sum(float(r.unit_price or 0) * float(r.volume or 0) for r in rows)
        unique_buyers = len({r.company_id for r in rows})
        contract_count = len(rows)
        max_dev = max(
            (abs(float(r.deviation_pct or 0)) for r in rows if r.deviation_pct is not None),
            default=0.0,
        )
        if spread_pct < 200:
            band = "clean"
        elif spread_pct <= 1000:
            band = "wide"
        else:
            band = "dirty"

        def _most_common(rrs, attr):
            counts: dict = {}
            for r in rrs:
                v = getattr(r, attr, None)
                if v:
                    counts[v] = counts.get(v, 0) + 1
            return max(counts.items(), key=lambda x: x[1])[0] if counts else None

        products[code] = ProductAgg(
            code=code,
            root_code=code.split("-")[0],
            name=_most_common(rows, "product_name") or code,
            unit=_most_common(rows, "unit") or "ед",
            category_id=_most_common(rows, "category_id"),
            avg_price=avg_p,
            min_price=min_p,
            max_price=max_p,
            spread_pct=round(spread_pct, 2),
            total_spend=round(total_spend, 2),
            unique_buyers=unique_buyers,
            contract_count=contract_count,
            max_deviation_pct=round(max_dev, 2),
            quality_band=band,
        )

    # Per-category aggregates
    cat_aggs: List[CategoryAggregate] = []
    for cat in CATEGORIES_SEED:
        cat_key = str(cat.id)
        in_cat = [p for p in products.values() if p.category_id == cat_key]
        in_cat.sort(key=lambda p: -p.total_spend)
        in_cat_capped = in_cat[:50]
        clean = [p for p in in_cat if p.quality_band == "clean"]
        clean_avgs = [p.avg_price for p in clean]
        cat_aggs.append(CategoryAggregate(
            id=cat.id,
            name=cat.name,
            short=cat.short,
            unit="ед",
            all_products=in_cat_capped,
            clean_count=len(clean),
            benchmark_product_count=len(clean),
            clean_spread_min=min(clean_avgs) if clean_avgs else None,
            clean_spread_max=max(clean_avgs) if clean_avgs else None,
        ))

    return products, cat_aggs


def aggregate_rating(closures: list) -> List[CompanyRatingRow]:
    """Group closures by company × category, compute weighted-avg deviations,
    rank companies by company_deviation ascending (lower=better)."""
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
                "company_color": color_for_sector(getattr(c, "company_sector", None)),
                "cats": {},
                "sum_dev": Decimal(0),
                "sum_ref": Decimal(0),
                "red_count": 0,
                "yellow_count": 0,
                "green_count": 0,
                "total_count": 0,
                "sum_overpay": Decimal(0),
                "sum_savings": Decimal(0),
            }
        co = by_company[co_id]

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

        delta = spend - ref
        co["sum_dev"] += delta
        co["sum_ref"] += ref
        co["total_count"] += 1

        if delta > 0:
            co["sum_overpay"] += delta
        else:
            co["sum_savings"] += -delta

        closure_dev = getattr(c, "deviation_pct", None)
        dev_val = float(closure_dev) if closure_dev is not None else 0.0
        if dev_val >= 10:
            co["red_count"] += 1
        elif dev_val >= 0:
            co["yellow_count"] += 1
        else:
            co["green_count"] += 1

    rating: List[CompanyRatingRow] = []
    for co_id, co in by_company.items():
        cat_devs: List[CategoryDeviation] = []
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

        above_count = co["red_count"]
        company_dev_pct = float(co["sum_dev"] / co["sum_ref"] * 100) if co["sum_ref"] > 0 else 0.0

        total_n = max(1, co["total_count"])
        red_pct = co["red_count"] / total_n * 100
        yellow_pct = co["yellow_count"] / total_n * 100
        green_pct = co["green_count"] / total_n * 100
        problem_cats = sum(1 for cd in cat_devs if cd.deviation_pct > 10)

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
                sum_overpay=co["sum_overpay"],
                sum_savings=co["sum_savings"],
                red_pct=red_pct,
                yellow_pct=yellow_pct,
                green_pct=green_pct,
                problem_cats=problem_cats,
                total_count=co["total_count"],
            )
        )

    rating.sort(key=lambda r: r.company_deviation)
    for i, r in enumerate(rating):
        r.rank = i + 1
    return rating


def compute_kpis(rating: List[CompanyRatingRow], all_closures: list) -> ProcurementKpis:
    clean = [c for c in all_closures if not getattr(c, "is_dirty", False)]
    above_count = sum(1 for r in rating if r.company_deviation > 0)
    total_overpay = sum(max(Decimal(0), r.sum_dev) for r in rating)
    devs = [r.company_deviation for r in rating if r.company_deviation is not None]
    median_dev = float(statistics.median(devs)) if devs else 0.0
    return ProcurementKpis(
        total_companies=len(rating),
        clean_companies=sum(1 for r in rating if r.sum_ref > 0),
        total_closures=len(all_closures),
        clean_closures=len(clean),
        total_overpay_uzs=total_overpay,
        above_market_pct=(above_count / len(rating) * 100) if rating else 0.0,
        median_deviation_pct=median_dev,
    )
