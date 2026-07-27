"""BP forecast service — прогноз финансовых метрик Бизнес-плана.

По каждой headline-метрике ОФР строит годовой ряд факта (bp_compute — с честным
источником nsbu/ytd; для базового года факт ИЛИ ожидаемое `expect`, чтобы
прогноз опирался на свежую оценку) и проецирует движком core/forecast; кварталы
будущих лет — по сезонности квартального плана. Числа воспроизводимы; ИИ-слой
получает их как опору.

nsbu-автозаполнение включается только для свежих лет (>= base_year−2) — иначе
bp_compute делает по ~20 SQL-запросов к финотчётности на КАЖДЫЙ исторический год.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.core.forecast import (
    forecast_annual,
    seasonal_shares,
    split_by_shares,
)
from app.models.bp_kpi import (
    BP_HEADLINE_METRIC_KEYS,
    BP_METRIC_DIRECTION,
    BP_METRIC_LABELS,
)
from app.schemas.bp_forecast import BpCompanyForecast, BpMetricForecast
from app.schemas.kpi_forecast import ForecastBlock, ForecastPoint, SeriesPoint
from app.services.bp_kpi_helpers import bp_compute, ytd_to_deltas
from app.uow.ports import UnitOfWorkABC

_MAX_HISTORY = 6
_QUARTERS = ("q1", "q2", "q3", "q4")


def _f(x: object) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _block(r, shares: Optional[list[float]] = None) -> ForecastBlock:
    d = r.to_dict()
    pts: list[ForecastPoint] = []
    for p in d["projections"]:
        q = split_by_shares(p["value"], shares) if (shares and p["value"] is not None) else None
        pts.append(ForecastPoint(
            period=p["period"], value=p["value"], low=p["low"], high=p["high"], quarters=q,
        ))
    return ForecastBlock(
        method=d["method"], confidence=d["confidence"], points_used=d["points_used"],
        note=d["note"], expected_year=d["expected_year"], projections=pts,
    )


class BpForecastService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def forecast_company(
        self, company_id: UUID, base_year: int, horizon: int = 2,
    ) -> BpCompanyForecast:
        horizon = max(1, min(int(horizon), 5))
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            years = await self.uow.bp.years_for_company(company_id)
            hist_years = [y for y in years if y <= base_year][-_MAX_HISTORY:]
            if base_year not in hist_years:
                hist_years = sorted({*hist_years, base_year})

            company = await self.uow.bp.get_company(company_id)
            name = (
                (company.name_short or company.name_ru or company.code)
                if company else None
            ) or str(company_id)
            code = company.code if company else None

            annual_by_year: dict[int, dict] = {}
            for y in hist_years:
                annual_by_year[y] = await bp_compute(
                    session, company_id, y, "annual", nsbu_fallback=(y >= base_year - 2),
                )
            base_q: dict[str, dict] = {}
            for q in _QUARTERS:
                base_q[q] = await bp_compute(session, company_id, base_year, q)

            metrics_out: list[BpMetricForecast] = []
            for m in BP_HEADLINE_METRIC_KEYS:
                syears: list[int] = []
                svals: list[float] = []
                hist: list[SeriesPoint] = []
                for y in hist_years:
                    cell = annual_by_year.get(y, {}).get(m, {}) or {}
                    fact = _f(cell.get("fact"))
                    plan = _f(cell.get("plan"))
                    expect = _f(cell.get("expect"))
                    hist.append(SeriesPoint(year=y, fact=fact, plan=plan))
                    val = fact if fact is not None else (expect if y == base_year else None)
                    if val is not None:
                        syears.append(y)
                        svals.append(val)
                af = forecast_annual(syears, svals, horizon)

                # Сезонность: план кварталов базового года → факт кварталов.
                # Кварталы БП хранятся НАРАСТАЮЩИМ ИТОГОМ → перед seasonal_shares
                # (движок ждёт суммы «за квартал») конвертируем в дельты. Иначе
                # доли всегда монотонно растут к Q4 независимо от сезонности
                # (плоские кварталы [25,50,75,100] дали бы 10/20/30/40%).
                def _q_deltas(metric: str, col: str) -> list:
                    ytd = [base_q[q].get(metric, {}).get(col) for q in _QUARTERS]
                    return [_f(v) for v in ytd_to_deltas(ytd)]

                shares = seasonal_shares([_q_deltas(m, "plan")])
                if shares is None:
                    shares = seasonal_shares([_q_deltas(m, "fact")])

                base_cell = annual_by_year.get(base_year, {}).get(m, {}) or {}
                # Метрику без единого значения (пустой ряд + пустой базовый год) — пропускаем.
                if not syears and all(
                    base_cell.get(c) is None for c in ("plan", "expect", "fact")
                ):
                    continue
                metrics_out.append(BpMetricForecast(
                    key=m, label=BP_METRIC_LABELS.get(m, m), unit=None,
                    direction=BP_METRIC_DIRECTION.get(m, "up"),
                    plan=_f(base_cell.get("plan")),
                    expect=_f(base_cell.get("expect")),
                    fact=_f(base_cell.get("fact")),
                    annual=_block(af, shares), history=hist,
                ))

            return BpCompanyForecast(
                company_id=company_id, company_code=code, company_name=name,
                base_year=base_year, horizon=horizon,
                future_years=[base_year + k for k in range(1, horizon + 1)],
                metrics=metrics_out,
                note=("" if metrics_out else "Нет данных БП за базовый год — прогноз недоступен"),
            )
