"""SOE Health Check — светофорная оценка здоровья компаний по методике МВФ.

Источник методики: IMF Fiscal Affairs Dept «SOE Health Check Tool»
(Downloads/SOE_HealthCheckTool.xlsm, настроен под Узбекистан) — 4-ступенчатые
пороги по коэффициентам → бенды риска 1..5 → Overall Rating (равные веса).

Данные — ТОЛЬКО канон financial_lines (summary FY, НСБУ/МСФО по выбору);
данные самого xlsm-файла не мигрируются (сверка июль-2026: 385 конфликтов
с редакторами — файл черновой; методика ценна, цифры — нет).

Честность (уроки аудитов):
  • нет данных ≠ 0: недоступный коэффициент = «н/д», исключён из Overall;
  • отрицательный капитал/EBITDA — отдельный кейс: бенд 5 с пометкой, без
    деления на отрицательное (иначе знак переворачивает смысл, ср. −187% в KPI);
  • Current/Quick Ratio НЕ считаем: в каноне нет кода текущих обязательств
    (честное «н/д» до появления totalCL в редакторе);
  • Cost Recovery и Cash Interest Coverage — приближения, помечены в формуле.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ─── Методика: коэффициенты и пороги МВФ (Parameters-лист) ────────────
# direction: gte — «больше = лучше» (value≥t1 → бенд 1) · lte — «меньше = лучше»
# thresholds: [t1, t2, t3, t4] → бенды 1..5
SOE_HEALTH_RATIOS: list[dict[str, Any]] = [
    {"key": "roa", "label": "ROA", "group": "Рентабельность",
     "formula": "Чистая прибыль / Активы",
     "direction": "gte", "thresholds": [0.10, 0.05, 0.0, -0.10], "fmt": "pct"},
    {"key": "roe", "label": "ROE", "group": "Рентабельность",
     "formula": "Чистая прибыль / Капитал",
     "direction": "gte", "thresholds": [0.20, 0.10, 0.0, -0.10], "fmt": "pct"},
    {"key": "costRecovery", "label": "Cost Recovery", "group": "Рентабельность",
     "formula": "Выручка / операционные затраты (≈ выручка − опер. прибыль)",
     "direction": "gte", "thresholds": [1.5, 1.3, 1.0, 0.8], "fmt": "x"},
    {"key": "debtorDays", "label": "Дебиторка, дни", "group": "Ликвидность",
     "formula": "Дебиторская задолженность / Выручка × 365",
     "direction": "lte", "thresholds": [30, 40, 50, 90], "fmt": "days"},
    {"key": "creditorDays", "label": "Кредиторка, дни", "group": "Ликвидность",
     "formula": "Кредиторская задолженность / Себестоимость × 365",
     "direction": "lte", "thresholds": [30, 60, 90, 120], "fmt": "days"},
    {"key": "debtToAssets", "label": "Долг/Активы", "group": "Платёжеспособность",
     "formula": "Долг / Активы",
     "direction": "lte", "thresholds": [0.3, 0.5, 0.8, 1.0], "fmt": "x"},
    {"key": "debtToEquity", "label": "Долг/Капитал", "group": "Платёжеспособность",
     "formula": "Долг / Капитал",
     "direction": "lte", "thresholds": [0.5, 1.0, 1.5, 2.0], "fmt": "x"},
    {"key": "debtToEbitda", "label": "Долг/EBITDA", "group": "Платёжеспособность",
     "formula": "Долг / EBITDA",
     "direction": "lte", "thresholds": [1.5, 2.0, 3.0, 5.0], "fmt": "x"},
    {"key": "interestCoverage", "label": "Interest Cov.", "group": "Платёжеспособность",
     "formula": "Операционная прибыль / Финансовые расходы",
     "direction": "gte", "thresholds": [2.0, 1.5, 1.2, 1.0], "fmt": "x"},
    {"key": "cashInterestCoverage", "label": "Cash Int. Cov.", "group": "Платёжеспособность",
     "formula": "EBITDA / Финансовые расходы (приближение)",
     "direction": "gte", "thresholds": [3.0, 2.0, 1.5, 1.0], "fmt": "x"},
    {"key": "debtCoverage", "label": "Debt Coverage", "group": "Платёжеспособность",
     "formula": "Операционный денежный поток (CFO) / Долг",
     "direction": "gte", "thresholds": [0.8, 0.6, 0.4, 0.3], "fmt": "x"},
]

SOE_HEALTH_ZONES = [
    {"max": 1.5, "key": "low",      "label": "Низкий риск",      "color": "#1D9E75"},
    {"max": 2.5, "key": "moderate", "label": "Умеренный",        "color": "#7DC4A0"},
    {"max": 3.5, "key": "elevated", "label": "Повышенный",       "color": "#EF9F27"},
    {"max": 4.5, "key": "high",     "label": "Высокий",          "color": "#E8590C"},
    {"max": 99,  "key": "severe",   "label": "Критический",      "color": "#E24B4A"},
]

_NEEDED_CODES = (
    "revenue", "cogs", "opProfit", "profit", "ebitda", "finCost",
    "totalAssets", "totalLiabilities", "equity", "debt",
    "accountsReceivable", "accountsPayable", "cfo",
)


def _band(value: float, direction: str, thr: list[float]) -> int:
    """Значение → бенд 1..5 по 4 порогам МВФ."""
    if direction == "gte":
        for i, t in enumerate(thr):
            if value >= t:
                return i + 1
        return 5
    for i, t in enumerate(thr):
        if value <= t:
            return i + 1
    return 5


def _zone(score: Optional[float]) -> Optional[dict]:
    if score is None:
        return None
    for z in SOE_HEALTH_ZONES:
        if score < z["max"]:
            return {"key": z["key"], "label": z["label"], "color": z["color"]}
    return None


def _compute_ratios(m: dict[str, float]) -> list[dict[str, Any]]:
    """Коэффициенты компании из канонических метрик. value=None → «н/д»;
    band может быть 5 при value=None (отриц. капитал/EBITDA) с note."""
    def g(k: str) -> Optional[float]:
        v = m.get(k)
        return float(v) if v is not None else None

    revenue, cogs = g("revenue"), g("cogs")
    op, profit, ebitda = g("opProfit"), g("profit"), g("ebitda")
    fin_cost = g("finCost")
    assets, equity, debt = g("totalAssets"), g("equity"), g("debt")
    ar, ap, cfo = g("accountsReceivable"), g("accountsPayable"), g("cfo")

    fc = abs(fin_cost) if fin_cost else None
    cogs_a = abs(cogs) if cogs else None
    out: dict[str, tuple[Optional[float], Optional[int], Optional[str]]] = {}

    out["roa"] = (profit / assets, None, None) if (profit is not None and assets and assets > 0) else (None, None, None)
    if equity is not None and equity <= 0:
        out["roe"] = (None, 5, "капитал ≤ 0")
        out["debtToEquity"] = (None, 5, "капитал ≤ 0")
    else:
        out["roe"] = (profit / equity, None, None) if (profit is not None and equity) else (None, None, None)
        out["debtToEquity"] = (debt / equity, None, None) if (debt is not None and equity) else (None, None, None)
    if revenue and op is not None and (revenue - op) > 0:
        out["costRecovery"] = (revenue / (revenue - op), None, None)
    else:
        out["costRecovery"] = (None, None, None)
    out["debtorDays"] = (abs(ar) / revenue * 365, None, None) if (ar is not None and revenue and revenue > 0) else (None, None, None)
    out["creditorDays"] = (abs(ap) / cogs_a * 365, None, None) if (ap is not None and cogs_a) else (None, None, None)
    out["debtToAssets"] = (debt / assets, None, None) if (debt is not None and assets and assets > 0) else (None, None, None)
    if ebitda is not None and ebitda <= 0:
        out["debtToEbitda"] = (None, 5, "EBITDA ≤ 0")
    else:
        out["debtToEbitda"] = (debt / ebitda, None, None) if (debt is not None and ebitda) else (None, None, None)
    out["interestCoverage"] = (op / fc, None, None) if (op is not None and fc) else (None, None, None)
    out["cashInterestCoverage"] = (ebitda / fc, None, None) if (ebitda is not None and fc) else (None, None, None)
    out["debtCoverage"] = (cfo / debt, None, None) if (cfo is not None and debt and debt > 0) else (None, None, None)

    rows: list[dict[str, Any]] = []
    for r in SOE_HEALTH_RATIOS:
        value, forced_band, note = out.get(r["key"], (None, None, None))
        band = forced_band
        if band is None and value is not None:
            band = _band(value, r["direction"], r["thresholds"])
        rows.append({
            "key": r["key"], "label": r["label"], "group": r["group"],
            "formula": r["formula"], "direction": r["direction"],
            "thresholds": r["thresholds"], "fmt": r["fmt"],
            "value": (round(value, 4) if value is not None else None),
            "band": band, "note": note,
        })
    return rows


def _overall(rows: list[dict[str, Any]]) -> tuple[Optional[float], int]:
    bands = [r["band"] for r in rows if r["band"] is not None]
    if not bands:
        return None, 0
    return round(sum(bands) / len(bands), 2), len(bands)


@dataclass
class SoeHealthService:
    async def _load_metrics(
        self, db: AsyncSession, *, year: int, standard: str,
        scope_ids: Optional[Sequence[UUID]],
    ) -> dict[str, dict[str, Any]]:
        """{company_code: {name, sector..., metrics{lc: val}}} из канона (summary FY)."""
        q = text(
            "SELECT c.code, COALESCE(c.name_short, c.name_ru) AS name, c.id AS cid, "
            "       s.code AS sector_code, s.name_ru AS sector_name, s.color_hex AS sector_color, "
            "       fl.line_code, fl.value "
            "FROM companies c "
            "LEFT JOIN sectors s ON s.id = c.sector_id "
            "JOIN financial_reports fr ON fr.company_id = c.id "
            "JOIN financial_lines fl ON fl.report_id = fr.id "
            "WHERE c.is_active = true AND fr.standard = :std AND fr.year = :yr "
            "AND fr.is_detailed = false AND fr.quarter IS NULL "
            "AND fl.line_code = ANY(:codes) AND fl.value IS NOT NULL"
        )
        rows = (await db.execute(q, {
            "std": standard, "yr": year, "codes": list(_NEEDED_CODES),
        })).all()
        out: dict[str, dict[str, Any]] = {}
        scope = {str(i) for i in scope_ids} if scope_ids is not None else None
        for code, name, cid, sec_code, sec_name, sec_color, lc, val in rows:
            if scope is not None and str(cid) not in scope:
                continue
            co = out.setdefault(code, {
                "code": code, "name": name, "company_id": str(cid),
                "sector_code": sec_code, "sector_name": sec_name,
                "sector_color": sec_color, "metrics": {},
            })
            co["metrics"][lc] = float(val)
        return out

    async def build(
        self, db: AsyncSession, *, year: int, standard: str,
        scope_ids: Optional[Sequence[UUID]],
    ) -> dict[str, Any]:
        standard = "IFRS" if standard.upper() == "IFRS" else "NSBU"
        cur = await self._load_metrics(db, year=year, standard=standard, scope_ids=scope_ids)
        prev = await self._load_metrics(db, year=year - 1, standard=standard, scope_ids=scope_ids)

        companies: list[dict[str, Any]] = []
        for code, co in cur.items():
            rows = _compute_ratios(co["metrics"])
            overall, n_avail = _overall(rows)
            prev_overall = None
            if code in prev:
                prev_overall, _n = _overall(_compute_ratios(prev[code]["metrics"]))
            companies.append({
                "code": code, "name": co["name"], "company_id": co["company_id"],
                "sector_code": co["sector_code"], "sector_name": co["sector_name"],
                "sector_color": co["sector_color"],
                "ratios": rows, "overall": overall, "zone": _zone(overall),
                "prev_overall": prev_overall,
                "delta": (round(overall - prev_overall, 2)
                          if overall is not None and prev_overall is not None else None),
                "available": n_avail,
            })
        # худшие сверху (внимание министра), н/д — в конец
        companies.sort(key=lambda x: (x["overall"] is None, -(x["overall"] or 0)))

        scored = [c for c in companies if c["overall"] is not None and c["available"] >= 5]
        zone_counts = {z["key"]: 0 for z in SOE_HEALTH_ZONES}
        for c in scored:
            zone_counts[c["zone"]["key"]] += 1
        portfolio_avg = round(sum(c["overall"] for c in scored) / len(scored), 2) if scored else None

        total_q = text("SELECT count(*) FROM companies WHERE is_active = true")
        total_companies = (await db.execute(total_q)).scalar() or 0

        return {
            "year": year,
            "standard": standard,
            "ratios_meta": SOE_HEALTH_RATIOS,
            "zones": SOE_HEALTH_ZONES,
            "companies": companies,
            "portfolio": {
                "avg": portfolio_avg,
                "zone": _zone(portfolio_avg),
                "zone_counts": zone_counts,
                "scored_count": len(scored),
                "total_companies": total_companies,
                "worst": ([{"code": c["code"], "name": c["name"], "overall": c["overall"]}
                           for c in scored[:3]] if scored else []),
                "best": ([{"code": c["code"], "name": c["name"], "overall": c["overall"]}
                          for c in sorted(scored, key=lambda x: x["overall"])[:3]] if scored else []),
            },
            # без брендинга источника в UI (пожелание пользователя) — методика
            # описана нейтрально; провенанс порогов см. в докстринге модуля.
            "methodology": "SOE Health Check · светофорная оценка финансовой устойчивости, пороги настраиваемые",
            "generated_at": datetime.now(UTC).isoformat(),
        }
