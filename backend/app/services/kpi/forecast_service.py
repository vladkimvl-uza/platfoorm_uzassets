"""KPI forecast service — детерминированный прогноз по кварталам и будущим годам.

Строит per-indicator ряды из БД (сопоставление индикаторов между годами по
bp_metric_key или нормализованному имени) и зовёт чистый движок
`app.core.forecast`. Числа воспроизводимы; ИИ-слой получает их как опору.

Ключевые решения (в каноне аудитов):
- Индикаторы между годами сопоставляются по `bp_metric_key` (стабильно) ИЛИ по
  нормализованному имени (иначе). Не совпало / нет истории → движок честно
  вернёт method='none' (не выдумываем).
- Годовой ряд для регрессии = фактические `fact_year` за прошлые годы + значение
  текущего года: факт, если закрыт, иначе ожидаемое из квартального прогноза
  (pace) — так прогноз будущих лет опирается на свежайший темп текущего года.
- Сводный прогноз выполнения компании — по взвешенному % выполнения за год
  (та же формула, что в summary: cap[0;150], вес квартал→год fallback).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.core.forecast import ForecastResult, forecast_annual, forecast_quarters
from app.schemas.kpi_forecast import (
    CompanyForecast,
    ForecastBlock,
    ForecastPoint,
    IndicatorForecast,
    ManagerForecast,
    SeriesPoint,
)
from app.services.bp_kpi_helpers import (
    kpi_compute_completion,
    kpi_period_weight,
    kpi_year_pair,
)
from app.uow.ports import UnitOfWorkABC

_MAX_HISTORY = 6  # сколько лет истории максимум берём в ряд


def _norm(s: Optional[str]) -> str:
    return " ".join((s or "").lower().split())


def _ind_key(ind) -> str:
    """Стабильный ключ индикатора для сопоставления между годами."""
    return (getattr(ind, "bp_metric_key", None) or "") or _norm(getattr(ind, "name", ""))


def _f(x: object) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _block(r: ForecastResult) -> ForecastBlock:
    d = r.to_dict()
    return ForecastBlock(
        method=d["method"],
        confidence=d["confidence"],
        points_used=d["points_used"],
        note=d["note"],
        expected_year=d["expected_year"],
        projections=[ForecastPoint(**p) for p in d["projections"]],
    )


class KpiForecastService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def forecast_company(
        self, company_id: UUID, base_year: int, horizon: int = 2,
    ) -> CompanyForecast:
        horizon = max(1, min(int(horizon), 5))
        async with self.uow:
            years = await self.uow.kpi.years_for_company(company_id)
            hist_years = [y for y in years if y <= base_year][-_MAX_HISTORY:]
            if base_year not in hist_years:
                hist_years = sorted({*hist_years, base_year})

            mgrs = await self.uow.kpi.get_managers_for_years(company_id, hist_years)
            company = mgrs[0].company if mgrs else await self.uow.kpi.get_company(company_id)
            name = (
                (company.name_short or company.name_ru or company.code)
                if company else None
            ) or str(company_id)
            code = company.code if company else None

            # Группировка по годам + индекс индикаторов по ключу (для рядов).
            by_year: dict[int, list] = {}
            for m in mgrs:
                by_year.setdefault(m.year, []).append(m)
            idx_by_year: dict[int, dict[str, object]] = {}
            for y, ms in by_year.items():
                d: dict[str, object] = {}
                for m in ms:
                    for ind in m.indicators:
                        d.setdefault(_ind_key(ind), ind)
                idx_by_year[y] = d

            # Сводный % выполнения за каждый год (для прогноза выполнения компании).
            comp_series: dict[int, float] = {}
            for y, ms in by_year.items():
                tw = sw = 0.0
                for m in ms:
                    for ind in m.indicators:
                        w = kpi_period_weight(ind, "year")
                        if w <= 0:
                            continue
                        r = kpi_compute_completion(ind, "year")
                        if r is None:
                            continue
                        tw += w
                        sw += w * max(0.0, min(r, 1.5))
                if tw > 0:
                    comp_series[y] = sw / tw * 100.0

            managers_out: list[ManagerForecast] = []
            for m in by_year.get(base_year, []):
                inds_out: list[IndicatorForecast] = []
                for ind in m.indicators:
                    ikey = _ind_key(ind)
                    q_plan = [getattr(ind, f"q{i}_plan", None) for i in (1, 2, 3, 4)]
                    q_fact = [getattr(ind, f"q{i}_fact", None) for i in (1, 2, 3, 4)]

                    prior = idx_by_year.get(base_year - 1, {}).get(ikey)
                    prior_q = (
                        [getattr(prior, f"q{i}_fact", None) for i in (1, 2, 3, 4)]
                        if prior is not None else None
                    )
                    qf = forecast_quarters(q_plan, q_fact, prior_q_fact=prior_q)

                    # Годовой ряд: факт прошлых лет + текущий год (факт или ожидаемое).
                    hist: list[SeriesPoint] = []
                    syears: list[int] = []
                    svals: list[float] = []
                    for y in hist_years:
                        oind = idx_by_year.get(y, {}).get(ikey)
                        if oind is None:
                            continue
                        plan_o, fact_o, _ = kpi_year_pair(oind)
                        if y == base_year:
                            # текущий год: факт, если закрыт, иначе ожидаемое (pace)
                            cur_val = fact_o if fact_o is not None else qf.expected_year
                            hist.append(SeriesPoint(year=y, fact=_f(fact_o), plan=_f(plan_o)))
                            if cur_val is not None:
                                syears.append(y)
                                svals.append(float(cur_val))
                        else:
                            hist.append(SeriesPoint(year=y, fact=_f(fact_o), plan=_f(plan_o)))
                            if fact_o is not None:
                                syears.append(y)
                                svals.append(float(fact_o))
                    af = forecast_annual(syears, svals, horizon)

                    plan_y, fact_y, _ = kpi_year_pair(ind)
                    inds_out.append(IndicatorForecast(
                        name=ind.name or "",
                        unit=ind.unit,
                        direction=(getattr(ind, "direction", "up") or "up"),
                        weight=kpi_period_weight(ind, "year"),
                        bp_metric_key=getattr(ind, "bp_metric_key", None),
                        manager=m.short_title or m.title or "",
                        role=m.role,
                        plan_year=_f(plan_y),
                        fact_year=_f(fact_y),
                        q_plan=[_f(x) for x in q_plan],
                        q_fact=[_f(x) for x in q_fact],
                        quarterly=_block(qf),
                        annual=_block(af),
                        history=hist,
                    ))
                if inds_out:
                    managers_out.append(ManagerForecast(
                        title=m.title or m.short_title or "",
                        role=m.role,
                        indicators=inds_out,
                    ))

            # Сводный прогноз выполнения компании (годовой ряд взвешенных %).
            cs_years = sorted(comp_series)
            comp_hist = [SeriesPoint(year=y, fact=comp_series[y]) for y in cs_years]
            comp_block = None
            if len(cs_years) >= 2:
                comp_block = _block(forecast_annual(
                    cs_years, [comp_series[y] for y in cs_years], horizon, method="ols",
                ))

            return CompanyForecast(
                company_id=company_id,
                company_code=code,
                company_name=name,
                base_year=base_year,
                horizon=horizon,
                future_years=[base_year + k for k in range(1, horizon + 1)],
                managers=managers_out,
                completion=comp_block,
                completion_history=comp_hist,
                note=("" if managers_out else "Нет KPI за базовый год — прогноз недоступен"),
            )
