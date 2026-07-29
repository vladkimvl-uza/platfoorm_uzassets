"""ExecDash-блок «Прогноз KPI» — детерминированный движок core/forecast.

Портфельный прогноз сводного выполнения KPI: по каждой компании строит годовой
ряд взвешенного % выполнения (та же формула, что в summary: cap[0;150], вес
квартал→год fallback) и проецирует на ближайший будущий год OLS-трендом.
Изолирован — падение блока не валит дашборд (см. service.build_dashboard).
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.forecast import forecast_annual
from app.models.bp_kpi import KpiManager
from app.models.company import Company
from app.schemas.executive_dashboard import (
    ExecKpiForecastBlock,
    ExecKpiForecastCompany,
)
from app.services.bp_kpi_helpers import (
    kpi_compute_completion,
    kpi_period_weight,
    sector_color,
)

_HIST = 5  # лет истории в ряд


def _empty(year: int, total: int = 0) -> ExecKpiForecastBlock:
    return ExecKpiForecastBlock(
        year=year, forecast_year=year + 1, has_data=False, total_companies=total,
    )


async def build_kpi_forecast_block(
    session: AsyncSession, year: int, *,
    scope_ids: Optional[Sequence[UUID]] = None, horizon: int = 1,
) -> ExecKpiForecastBlock:
    years = list(range(year - _HIST + 1, year + 1))
    q = (
        select(KpiManager)
        .join(Company, KpiManager.company_id == Company.id)
        .where(
            KpiManager.year.in_(years),
            Company.is_active.is_(True),
        )
        .options(
            selectinload(KpiManager.indicators),
            selectinload(KpiManager.company).selectinload(Company.sector),
        )
    )
    if scope_ids is None:
        # include_in_rollups: демо и непрофильные компании не должны искажать
        # ПОРТФЕЛЬНЫЙ прогноз. При явной области выборка уже сужена вызывающим —
        # иначе пользователь, чья область состоит из такой компании, остался бы
        # без собственного прогноза.
        q = q.where(Company.include_in_rollups.is_(True))
    else:
        if not scope_ids:
            return _empty(year)
        q = q.where(KpiManager.company_id.in_(list(scope_ids)))
    mgrs = list((await session.execute(q)).scalars().all())
    if not mgrs:
        return _empty(year)

    # (company, year) → [sum_weight, sum_weighted_ratio]; + имя/цвет компании.
    acc: dict[tuple[UUID, int], list[float]] = {}
    meta: dict[UUID, tuple[str, Optional[str]]] = {}
    for m in mgrs:
        co = m.company
        meta.setdefault(m.company_id, (
            co.name_short or co.name_ru or co.code or "—", sector_color(co),
        ))
        agg = acc.setdefault((m.company_id, m.year), [0.0, 0.0])
        for ind in m.indicators:
            w = kpi_period_weight(ind, "year")
            if w <= 0:
                continue
            r = kpi_compute_completion(ind, "year")
            if r is None:
                continue
            agg[0] += w
            agg[1] += w * max(0.0, min(r, 1.5))

    comp: dict[UUID, dict[int, float]] = {}
    for (cid, y), (sw, swr) in acc.items():
        if sw > 0:
            comp.setdefault(cid, {})[y] = swr / sw * 100.0

    total_companies = len(meta)
    rows: list[ExecKpiForecastCompany] = []
    for cid, series in comp.items():
        ys = sorted(series)
        if len(ys) < 2:
            continue  # тренд нужен ≥2 года — движок иначе вернёт none
        fr = forecast_annual(ys, [series[y] for y in ys], horizon, method="ols")
        if not fr.projections:
            continue
        p0 = fr.projections[0]
        fy = int(p0.period) if str(p0.period).isdigit() else ys[-1] + 1
        cur = series.get(year, series[ys[-1]])
        forecast = p0.value
        delta = (forecast - cur) if (forecast is not None and cur is not None) else None
        rows.append(ExecKpiForecastCompany(
            company_id=str(cid), name=meta[cid][0], sector_color=meta[cid][1],
            current=round(cur, 1) if cur is not None else None,
            forecast=round(forecast, 1) if forecast is not None else None,
            low=round(p0.low, 1) if p0.low is not None else None,
            high=round(p0.high, 1) if p0.high is not None else None,
            delta=round(delta, 1) if delta is not None else None,
            method=fr.method, confidence=fr.confidence, forecast_year=fy,
        ))
    if not rows:
        return _empty(year, total_companies)

    fvals = [r.forecast for r in rows if r.forecast is not None]
    cvals = [r.current for r in rows if r.current is not None]
    fyear = min((r.forecast_year for r in rows if r.forecast_year), default=year + 1)
    companies_sorted = sorted(rows, key=lambda r: -(r.forecast if r.forecast is not None else -1))
    risks = sorted(
        [r for r in rows if r.forecast is not None],
        key=lambda r: (r.forecast, r.delta if r.delta is not None else 0.0),
    )[:5]
    return ExecKpiForecastBlock(
        year=year, forecast_year=fyear, has_data=True,
        avg_forecast=round(sum(fvals) / len(fvals), 1) if fvals else None,
        avg_current=round(sum(cvals) / len(cvals), 1) if cvals else None,
        improving=sum(1 for r in rows if (r.delta or 0) > 1),
        declining=sum(1 for r in rows if (r.delta or 0) < -1),
        at_risk=sum(1 for r in rows if r.forecast is not None and r.forecast < 75),
        scored_count=len(rows), total_companies=total_companies,
        companies=companies_sorted, risks=risks, leaders=companies_sorted[:5],
    )
