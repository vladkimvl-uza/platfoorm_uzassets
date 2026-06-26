"""Pure-function aggregators для procurement_analysis. Вынесены в отдельный
module — чтобы можно было unit-тестировать с fixture-closures без БД, и
переиспользовать из других контекстов (например AI-tools).
"""
from __future__ import annotations

import statistics
from decimal import Decimal
from typing import Optional

from app.schemas.procurement_analysis import (
    CategoryAggregate,
    CategoryDeviation,
    CategoryMeta,
    CompanyRatingRow,
    MethodAgg,
    PlatformAgg,
    ProcurementKpis,
    ProductAgg,
    SupplierAgg,
    SupplierConcentration,
)

# Полоса сопоставимости для потенц. экономии / премии поставщика:
# цены в [медиана×LO … медиана×HI]; вне — иная спецификация/выброс.
_BAND_LO, _BAND_HI = 0.5, 2.0

# 15 fixed categories — verbatim from legacy (Ф-59 decree). xarid xlsx
# тагирует rows с этими IDs в "Category" column, имена должны совпадать.
CATEGORIES_SEED: list[CategoryMeta] = [
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


_SECTOR_FAMILY = {
    "mining": "mining", "mining_metallurgy": "mining", "metallurgy": "mining",
    "oilgas": "oilgas", "oil_gas": "oilgas",
    "energy": "energy",
    "transport": "transport", "transport_communications": "transport", "telecom": "transport",
    "chemistry": "chemistry",
}


def sector_family(code: Optional[str]) -> str:
    """Нормализует разнобой кодов сектора (короткие/длинные) к семье для фильтра."""
    return _SECTOR_FAMILY.get((code or "other").lower(), "other")


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
) -> tuple[dict[str, ProductAgg], list[CategoryAggregate]]:
    """Per-product aggregation (productsByCode) + per-category buckets.

    Quality bands (legacy line 21433): clean<200% spread, wide 200-1000%, dirty>1000%.
    """
    by_code: dict[str, list] = {}
    for c in closures:
        if not c.product_code:
            continue
        by_code.setdefault(c.product_code, []).append(c)

    products: dict[str, ProductAgg] = {}
    for code, rows in by_code.items():
        # Объединяем одинаковый код ПО КОМПАНИЯМ: несколько контрактов одной
        # компании по этому коду схлопываются в ОДНУ единицу сравнения —
        # эффективная цена компании = Σ(цена×объём) / Σ(объём). Особенно важно
        # для услуг (shartli birlik), где цена за отдельную строку несравнима,
        # но и для товаров (одна компания, много закупок одного кода).
        by_co: dict = {}
        for r in rows:
            up = float(r.unit_price or 0)
            vol = float(r.volume or 0)
            if up <= 0 or vol <= 0:
                continue
            d = by_co.setdefault(r.company_id, [0.0, 0.0])  # [spend, volume]
            d[0] += up * vol
            d[1] += vol
        co_prices = [s / v for (s, v) in by_co.values() if v > 0]
        if not co_prices:
            continue
        min_p = min(co_prices)
        max_p = max(co_prices)
        avg_p = float(statistics.median(co_prices))   # медиана ПО КОМПАНИЯМ
        spread_pct = ((max_p - min_p) / min_p * 100) if min_p > 0 else 0.0
        total_spend = sum(d[0] for d in by_co.values())
        total_volume = sum(d[1] for d in by_co.values())
        unique_buyers = len(by_co)

        # Потенц. экономия = Σ объём×(эфф.цена компании − лучшая сопоставимая)
        # в полосе [медиана×0.5 … ×2]. Только для сопоставимых (>=2 компаний).
        potential_saving = 0.0
        if unique_buyers >= 2 and avg_p > 0:
            lo, hi = avg_p * _BAND_LO, avg_p * _BAND_HI
            band = [p for p in co_prices if lo <= p <= hi]
            band_min = min(band) if band else min_p
            for (s, v) in by_co.values():
                if v <= 0:
                    continue
                p = s / v
                if p > band_min and lo <= p <= hi:
                    potential_saving += (p - band_min) * v
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

        # product_type лежит в extra.product_type (PRODUCT/SERVICE)
        pt_counts: dict = {}
        for r in rows:
            pt = ((getattr(r, "extra", None) or {}).get("product_type") or "").upper()
            if pt:
                pt_counts[pt] = pt_counts.get(pt, 0) + 1
        product_type = max(pt_counts.items(), key=lambda x: x[1])[0] if pt_counts else "PRODUCT"

        products[code] = ProductAgg(
            code=code,
            root_code=code.split("-")[0],
            name=_most_common(rows, "product_name") or code,
            unit=_most_common(rows, "unit") or "ед",
            product_type=product_type,
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
            potential_saving=round(potential_saving, 2),
            total_volume=round(total_volume, 2),
        )

    # Per-category aggregates
    cat_aggs: list[CategoryAggregate] = []
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


def aggregate_rating(closures: list) -> list[CompanyRatingRow]:
    """Group closures by company × category, compute weighted-avg deviations,
    rank companies by company_deviation ascending (lower=better)."""
    if not closures:
        return []

    by_company: dict[str, dict] = {}

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

    rating: list[CompanyRatingRow] = []
    for co_id, co in by_company.items():
        cat_devs: list[CategoryDeviation] = []
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


def compute_kpis(
    rating: list[CompanyRatingRow],
    all_closures: list,
    lots: Optional[list[dict]] = None,
    products: Optional[dict[str, ProductAgg]] = None,
    *,
    undisclosed_spend: float = 0.0,
    supplier_count: int = 0,
) -> ProcurementKpis:
    clean = [c for c in all_closures if not getattr(c, "is_dirty", False)]
    above_count = sum(1 for r in rating if r.company_deviation > 0)
    total_overpay = sum(max(Decimal(0), r.sum_dev) for r in rating)
    devs = [r.company_deviation for r in rating if r.company_deviation is not None]
    median_dev = float(statistics.median(devs)) if devs else 0.0

    lots = lots or []
    total_spend = sum(l["spend"] for l in lots)
    total_start = sum(l["start"] for l in lots)
    total_saved = sum(l["saved"] for l in lots)
    no_tender_spend = sum(l["spend"] for l in lots if l["saved"] <= 0)
    services_spend = sum(l["spend"] for l in lots if l.get("is_service"))
    potential = sum(p.potential_saving for p in (products or {}).values())

    return ProcurementKpis(
        total_companies=len(rating),
        clean_companies=sum(1 for r in rating if r.sum_ref > 0),
        total_closures=len(all_closures),
        clean_closures=len(clean),
        total_overpay_uzs=total_overpay,
        above_market_pct=(above_count / len(rating) * 100) if rating else 0.0,
        median_deviation_pct=median_dev,
        total_spend=Decimal(str(round(total_spend, 2))),
        total_lots=len(lots),
        saved_amount=Decimal(str(round(total_saved, 2))),
        saved_rate_pct=round(total_saved / total_start * 100, 2) if total_start > 0 else 0.0,
        no_tender_spend=Decimal(str(round(no_tender_spend, 2))),
        no_tender_pct=round(no_tender_spend / total_spend * 100, 2) if total_spend > 0 else 0.0,
        potential_saving_uzs=Decimal(str(round(potential, 2))),
        supplier_count=supplier_count,
        disclosed_supplier_pct=round((total_spend - undisclosed_spend) / total_spend * 100, 2) if total_spend > 0 else 0.0,
        services_spend=Decimal(str(round(services_spend, 2))),
        services_pct=round(services_spend / total_spend * 100, 2) if total_spend > 0 else 0.0,
        goods_spend=Decimal(str(round(total_spend - services_spend, 2))),
    )


# ═══ Supplier / method / platform aggregators (lot-deduplicated) ═════

def _clean_supplier(name: Optional[str]) -> str:
    return (str(name).replace('"', "").replace("\\", "").strip()) if name else ""


_UNDISCLOSED = "(не указан)"


def _supplier_key(inn: str, name: str) -> str:
    if inn:
        return inn
    if name:
        return "NM:" + name.lower()
    return _UNDISCLOSED


def dedup_lots(closures: list) -> list[dict]:
    """Схлопывает строки-товары в уникальные лоты (одна сумма контракта на lotId).
    Внутри лота поставщик/способ/площадка/компания постоянны. Чинит задвоение
    суммы на мультитоварных лотах (см. extra.contract_amount)."""
    lots: dict = {}
    for c in closures:
        lid = (getattr(c, "lot_id", None) or "").strip()
        key = (str(c.company_id), lid) if lid else ("", str(getattr(c, "id", id(c))))
        rec = lots.get(key)
        if rec is None:
            name = _clean_supplier(getattr(c, "supplier_name", None))
            inn = (getattr(c, "supplier_inn", None) or "").strip()
            rec = lots[key] = {
                "company_id": c.company_id,
                "company_name": getattr(c, "company_name", None),
                "company_sector": getattr(c, "company_sector", None),
                "supplier_inn": inn,
                "supplier_name": name,
                "supplier_key": _supplier_key(inn, name),
                "method": (getattr(c, "purchase_type", None) or "").strip().lower(),
                "platform": (getattr(c, "platform", None) or "").strip(),
                "is_service": ((getattr(c, "extra", None) or {}).get("product_type") or "").upper() == "SERVICE",
                "_ca": None, "_start": None, "_lines": 0.0, "saved": 0.0,
            }
        extra = getattr(c, "extra", None) or {}
        if rec["_ca"] is None and extra.get("contract_amount") is not None:
            try:
                rec["_ca"] = float(extra["contract_amount"])
            except (TypeError, ValueError):
                pass
        if rec["_start"] is None and extra.get("start_summa") is not None:
            try:
                rec["_start"] = float(extra["start_summa"])
            except (TypeError, ValueError):
                pass
        ta = getattr(c, "total_amount", None)
        if ta is not None:
            rec["_lines"] += float(ta)
        else:
            rec["_lines"] += float(getattr(c, "unit_price", 0) or 0) * float(getattr(c, "volume", 0) or 0)
        sa = getattr(c, "saved_amount", None)
        if sa is not None:
            try:
                rec["saved"] = max(rec["saved"], float(sa))
            except (TypeError, ValueError):
                pass

    out: list[dict] = []
    for rec in lots.values():
        spend = rec["_ca"] if rec["_ca"] is not None else rec["_lines"]
        start = rec["_start"] if rec["_start"] is not None else (spend + rec["saved"])
        rec["spend"] = spend
        rec["start"] = start
        out.append(rec)
    return out


def _supplier_excess(closures: list, products: dict[str, ProductAgg]) -> dict[str, dict]:
    """Премия поставщика над медианой рынка по сопоставимым кодам (row-level)."""
    acc: dict[str, dict] = {}
    for c in closures:
        code = getattr(c, "product_code", None)
        prod = products.get(code) if code else None
        if not prod or prod.unique_buyers < 2 or prod.avg_price <= 0:
            continue
        price = float(getattr(c, "unit_price", 0) or 0)
        vol = float(getattr(c, "volume", 0) or 0)
        if price <= 0 or vol <= 0:
            continue
        med = prod.avg_price
        if not (med * _BAND_LO <= price <= med * _BAND_HI):
            continue
        inn = (getattr(c, "supplier_inn", None) or "").strip()
        name = _clean_supplier(getattr(c, "supplier_name", None))
        key = _supplier_key(inn, name)
        a = acc.setdefault(key, {"excess": 0.0, "cmp_spend": 0.0, "lines": 0})
        a["cmp_spend"] += price * vol
        if price > med:
            a["excess"] += (price - med) * vol
            a["lines"] += 1
    return acc


def aggregate_suppliers(
    lots: list[dict],
    closures: list,
    products: dict[str, ProductAgg],
    total_spend: float,
    *,
    top_n: int = 50,
) -> tuple[list[SupplierAgg], list[SupplierAgg], list[SupplierAgg]]:
    """Возвращает (топ по спенду, сквозные >=2 компаний, дорогие по премии)."""
    excess = _supplier_excess(closures, products)
    S: dict[str, dict] = {}
    for L in lots:
        key = L["supplier_key"]
        s = S.get(key)
        if s is None:
            s = S[key] = {
                "inn": L["supplier_inn"], "name": L["supplier_name"] or _UNDISCLOSED,
                "spend": 0.0, "saved": 0.0, "start": 0.0, "lots": 0, "companies": {},
            }
        s["spend"] += L["spend"]; s["saved"] += L["saved"]; s["start"] += L["start"]
        s["lots"] += 1
        if L["company_id"] is not None:
            s["companies"][str(L["company_id"])] = L["company_name"] or "—"

    def _mk(key: str, d: dict) -> SupplierAgg:
        ex = excess.get(key, {})
        excess_uzs = ex.get("excess", 0.0)
        cmp_spend = ex.get("cmp_spend", 0.0)
        comps = d["companies"]
        return SupplierAgg(
            supplier_inn=d["inn"] or None,
            supplier_name=d["name"],
            spend=Decimal(str(round(d["spend"], 2))),
            spend_share_pct=round(d["spend"] / total_spend * 100, 2) if total_spend > 0 else 0.0,
            lot_count=d["lots"],
            company_count=len(comps),
            company_codes=sorted(comps.values())[:12],
            saved_amount=Decimal(str(round(d["saved"], 2))),
            saved_rate_pct=round(d["saved"] / d["start"] * 100, 2) if d["start"] > 0 else 0.0,
            is_cross=len(comps) >= 2,
            excess_uzs=Decimal(str(round(excess_uzs, 2))),
            comparable_spend=Decimal(str(round(cmp_spend, 2))),
            premium_pct=round(excess_uzs / cmp_spend * 100, 2) if cmp_spend > 0 else 0.0,
            overpriced_lines=ex.get("lines", 0),
        )

    named = {k: v for k, v in S.items() if k != _UNDISCLOSED}
    rows = {k: _mk(k, v) for k, v in named.items()}

    top = sorted(rows.values(), key=lambda s: -float(s.spend))[:top_n]
    cross = sorted((s for s in rows.values() if s.is_cross), key=lambda s: -float(s.spend))[:top_n]
    expensive = sorted(
        (s for s in rows.values() if float(s.excess_uzs) > 0 and float(s.comparable_spend) >= 1e8),
        key=lambda s: -float(s.excess_uzs),
    )[:40]
    return top, cross, expensive


_METHOD_LABELS = {
    "e_shop": "Электронный магазин",
    "e_store": "Электронный магазин",
    "auction": "Аукцион",
    "best_offer": "Лучшее предложение",
    "competitive": "Конкурентные методы",
    "tender": "Тендер",
    "": "(не указан)",
}
_COMPETITIVE = {"auction", "best_offer", "competitive", "tender"}


def aggregate_methods(lots: list[dict], total_spend: float) -> list[MethodAgg]:
    M: dict[str, dict] = {}
    for L in lots:
        m = L["method"]
        rec = M.setdefault(m, {"spend": 0.0, "saved": 0.0, "start": 0.0, "lots": 0})
        rec["spend"] += L["spend"]; rec["saved"] += L["saved"]; rec["start"] += L["start"]
        rec["lots"] += 1
    out = [
        MethodAgg(
            method=m or "(не указан)",
            label=_METHOD_LABELS.get(m, m or "(не указан)"),
            lot_count=d["lots"],
            spend=Decimal(str(round(d["spend"], 2))),
            spend_share_pct=round(d["spend"] / total_spend * 100, 2) if total_spend > 0 else 0.0,
            saved_amount=Decimal(str(round(d["saved"], 2))),
            saved_rate_pct=round(d["saved"] / d["start"] * 100, 2) if d["start"] > 0 else 0.0,
            is_competitive=m in _COMPETITIVE,
        )
        for m, d in M.items()
    ]
    out.sort(key=lambda x: -float(x.spend))
    return out


def aggregate_platforms(lots: list[dict], total_spend: float) -> list[PlatformAgg]:
    P: dict[str, dict] = {}
    for L in lots:
        p = L["platform"] or "(не указана)"
        rec = P.setdefault(p, {"spend": 0.0, "saved": 0.0, "start": 0.0, "lots": 0})
        rec["spend"] += L["spend"]; rec["saved"] += L["saved"]; rec["start"] += L["start"]
        rec["lots"] += 1
    out = [
        PlatformAgg(
            platform=p,
            lot_count=d["lots"],
            spend=Decimal(str(round(d["spend"], 2))),
            spend_share_pct=round(d["spend"] / total_spend * 100, 2) if total_spend > 0 else 0.0,
            saved_amount=Decimal(str(round(d["saved"], 2))),
            saved_rate_pct=round(d["saved"] / d["start"] * 100, 2) if d["start"] > 0 else 0.0,
        )
        for p, d in P.items()
    ]
    out.sort(key=lambda x: -float(x.spend))
    return out


def aggregate_concentration(lots: list[dict]) -> list[SupplierConcentration]:
    """Концентрация поставщиков внутри каждой компании (HHI + доли топ-1/топ-3)."""
    C: dict[str, dict] = {}
    for L in lots:
        cid = str(L["company_id"])
        rec = C.get(cid)
        if rec is None:
            rec = C[cid] = {
                "company_id": L["company_id"],
                "company_name": L["company_name"] or cid[:8],
                "company_sector": L["company_sector"],
                "spend": 0.0, "suppliers": {},
            }
        rec["spend"] += L["spend"]
        sk = L["supplier_key"]
        sn = L["supplier_name"] or _UNDISCLOSED
        s = rec["suppliers"].setdefault(sk, {"name": sn, "spend": 0.0})
        s["spend"] += L["spend"]

    out: list[SupplierConcentration] = []
    for rec in C.values():
        tot = rec["spend"] or 1.0
        ordered = sorted(rec["suppliers"].values(), key=lambda s: -s["spend"])
        top1 = ordered[0]["spend"] / tot * 100 if ordered else 0.0
        top3 = sum(s["spend"] for s in ordered[:3]) / tot * 100
        hhi = sum((s["spend"] / tot) ** 2 for s in ordered) * 10000
        out.append(SupplierConcentration(
            company_id=rec["company_id"],
            company_name=rec["company_name"],
            company_color=color_for_sector(rec["company_sector"]),
            company_sector=rec["company_sector"],
            spend=Decimal(str(round(rec["spend"], 2))),
            supplier_count=len(rec["suppliers"]),
            top1_name=ordered[0]["name"] if ordered else None,
            top1_pct=round(top1, 1),
            top3_pct=round(top3, 1),
            hhi=round(hhi, 0),
        ))
    out.sort(key=lambda x: -x.top1_pct)
    return out
