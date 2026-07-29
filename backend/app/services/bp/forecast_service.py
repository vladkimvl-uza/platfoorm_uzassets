"""BP forecast service — прогноз финансовых метрик Бизнес-плана.

По каждой headline-метрике ОФР строит годовой ряд факта (bp_compute — с честным
источником nsbu/ytd; для базового года факт ИЛИ ожидаемое `expect`, чтобы
прогноз опирался на свежую оценку) и проецирует движком core/forecast; кварталы
будущих лет — по сезонности квартального плана. Числа воспроизводимы; ИИ-слой
получает их как опору.

nsbu-автозаполнение включено на всю глубину истории (НСБУ-отчётность лежит с
2021): ~20 лёгких SQL-запросов на исторический год — приемлемая цена за полную
серию для CAGR/OLS (прогноз и генератор планов дергаются по кнопке, не в цикле).
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.core.forecast import (
    forecast_annual,
    forecast_quarters,
    seasonal_shares,
    split_by_shares,
)
from app.models.bp_kpi import (
    BP_HEADLINE_METRIC_KEYS,
    BP_METRIC_DIRECTION,
    BP_METRIC_LABELS,
    BP_METRICS,
)
from app.schemas.bp_forecast import (
    BpCompanyForecast,
    BpMetricForecast,
    BpPlanDraft,
    BpPlanDraftMetric,
    BpQuarterOutlook,
    BpQuarterProjection,
)
from app.schemas.kpi_forecast import ForecastBlock, ForecastPoint, SeriesPoint
from app.services.bp_kpi_helpers import bp_compute, bp_fact_from_nsbu, ytd_to_deltas
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


_QO_METHOD_RU = {
    "pace": "план × темп", "seasonal": "сезонность прошлого года",
    "run_rate": "run-rate", "plan": "по плану", "actual": "год закрыт",
}
_QO_CONF_ORD = {"none": 0, "low": 1, "medium": 2, "high": 3}


class BpForecastService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def plan_draft(self, company_id: UUID, target_year: int) -> BpPlanDraft:
        """Черновик ПЛАНА на target_year из истории фактов компании.

        Годовое предложение — forecast_annual (auto: CAGR/OLS) по годовым фактам
        (для последнего исторического года допускается «ожидаемое»). Квартальная
        разбивка — историческая сезонность из ФАКТ-дельт (fallback план-дельты,
        до 3 последних лет), результат конвертируется ОБРАТНО в нарастающий итог
        (канон хранения; q4 ≡ годовому предложению). Только вводимые метрики —
        auto-итоги считаются формулами. Черновик НИЧЕГО не пишет: применение —
        редактором в пустые ячейки + штатный save (модерация/локи сохраняются).
        """
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            years = await self.uow.bp.years_for_company(company_id)
            # История ШИРЕ годов bp_records: НСБУ-факты существуют и за годы без
            # строк БП (bp_compute с nsbu_fallback их достаёт) — пробуем весь
            # диапазон, пустые годы отпадут сами (значений не будет).
            hist = sorted({
                *(y for y in years if y < target_year),
                *range(target_year - _MAX_HISTORY, target_year),
            })[-_MAX_HISTORY:]
            if not hist:
                return BpPlanDraft(
                    company_id=company_id, target_year=target_year,
                    note="Нет исторических лет БП — черновик построить не из чего",
                )
            # nsbu_fallback на ВСЮ глубину: НСБУ-отчётность лежит с 2021 года —
            # резать её перф-лимитом значит строить CAGR по огрызку серии.
            annual_by_year = {
                y: await bp_compute(
                    session, company_id, y, "annual", nsbu_fallback=True,
                )
                for y in hist
            }
            # Сезонность: до 3 последних лет, квартальные ДЕЛЬТЫ (канон YTD).
            season_years = hist[-3:]
            q_by_year = {
                y: [await bp_compute(session, company_id, y, q) for q in _QUARTERS]
                for y in season_years
            }
            input_keys = [m["key"] for m in BP_METRICS if not m.get("auto")]
            last_hist = hist[-1]
            used_years: set[int] = set()
            metrics_out: list[BpPlanDraftMetric] = []
            for k in input_keys:
                label = BP_METRIC_LABELS.get(k, k)
                syears: list[int] = []
                svals: list[float] = []
                for y in hist:
                    cell = annual_by_year[y].get(k, {}) or {}
                    v = _f(cell.get("fact"))
                    if v is None and y == last_hist:
                        v = _f(cell.get("expect"))   # текущий год — свежая оценка
                    if v is None and y == last_hist:
                        # Годовой факт/ожидаемое не закрыты, но есть кварталы —
                        # честная pace-оценка года (только при наличии ФАКТ-кварталов;
                        # method='plan' не годится — это не оценка факта).
                        qcells = q_by_year.get(y)
                        if qcells:
                            dpl = [_f(x) for x in ytd_to_deltas([c[k]["plan"] for c in qcells])]
                            dfc = [_f(x) for x in ytd_to_deltas([c[k]["fact"] for c in qcells])]
                            if any(x is not None for x in dfc):
                                qr = forecast_quarters(dpl, dfc)
                                if qr.method in ("pace", "seasonal", "run_rate", "actual"):
                                    v = _f(qr.expected_year)
                    if v is not None:
                        syears.append(y)
                        svals.append(v)
                        used_years.add(y)
                src_note = ""
                if len(syears) < 2:
                    # НСБУ-истории мало — пробуем серию ЦЕЛИКОМ из МСФО (стандарты
                    # в одной серии НЕ смешиваем; источник помечаем честно).
                    iy: list[int] = []
                    iv: list[float] = []
                    for y in hist:
                        v = _f(await bp_fact_from_nsbu(
                            session, company_id, y, k, standard="IFRS"))
                        if v is not None:
                            iy.append(y)
                            iv.append(v)
                    if len(iy) >= 2 and len(iy) > len(syears):
                        syears, svals = iy, iv
                        used_years.update(iy)
                        src_note = " · источник истории: МСФО"
                if not syears:
                    metrics_out.append(BpPlanDraftMetric(
                        key=k, label=label, note="Нет истории факта"))
                    continue
                horizon = target_year - max(syears)
                if horizon < 1:
                    metrics_out.append(BpPlanDraftMetric(
                        key=k, label=label, note="Год уже присутствует в истории"))
                    continue
                af = forecast_annual(syears, svals, horizon)
                proj = next(
                    (p for p in af.projections if p.period == str(target_year)), None)
                if proj is None or proj.value is None:
                    metrics_out.append(BpPlanDraftMetric(
                        key=k, label=label, method=af.method,
                        confidence=af.confidence,
                        note=af.note or "Прогноз недоступен"))
                    continue
                rows_fact: list[list] = []
                rows_plan: list[list] = []
                for y in season_years:
                    cells = q_by_year[y]
                    rows_fact.append(
                        [_f(v) for v in ytd_to_deltas([c[k]["fact"] for c in cells])])
                    rows_plan.append(
                        [_f(v) for v in ytd_to_deltas([c[k]["plan"] for c in cells])])
                shares = seasonal_shares(rows_fact) or seasonal_shares(rows_plan)
                quarters_ytd: Optional[list[Optional[float]]] = None
                if shares:
                    qs = split_by_shares(proj.value, shares) or []
                    acc = 0.0
                    quarters_ytd = []
                    for v in qs:
                        acc += (v or 0.0)
                        quarters_ytd.append(round(acc, 1))
                    if quarters_ytd:
                        # q4 ≡ годовому предложению (без дрейфа округления)
                        quarters_ytd[-1] = round(proj.value, 1)
                metrics_out.append(BpPlanDraftMetric(
                    key=k, label=label,
                    annual=round(proj.value, 1),
                    low=(round(proj.low, 1) if proj.low is not None else None),
                    high=(round(proj.high, 1) if proj.high is not None else None),
                    quarters_ytd=quarters_ytd,
                    method=af.method, confidence=af.confidence,
                    note=(af.note or "") + src_note,
                ))
            return BpPlanDraft(
                company_id=company_id, target_year=target_year,
                base_years=sorted(used_years) or hist,
                metrics=metrics_out,
                note=("Черновик из истории (факты НСБУ/БП; незакрытый год — "
                      "pace-оценка по кварталам) — применяется только в пустые "
                      "ячейки плана; кварталы нарастающим итогом"),
            )

    async def quarter_outlook(
        self,
        year: int,
        metric: str = "revenue",
        *,
        company_id: Optional[UUID] = None,
        scope_company_ids: Optional[Sequence[UUID]] = None,
    ) -> BpQuarterOutlook:
        """Прогноз оставшихся кварталов года для «Динамики по кварталам».

        Движок core/forecast.forecast_quarters ждёт суммы «ЗА квартал» →
        кварталы БП (нарастающий итог) конвертируются через ytd_to_deltas;
        сезонный fallback — дельты фактов прошлого года.

        Компания: движок на её рядах как есть. Портфель: движок ПО КАЖДОЙ
        компании (naz прогнозится pace по своим q3/q4-планам, компании без
        планов — сезонностью/run-rate), сводные проекции = Σ по кварталам
        ПОЗЖЕ последнего портфельного факта; методы перечисляются в note,
        уверенность = минимальная среди вошедших. Честность: коридор Σ
        только когда он есть у всех вошедших компаний, иначе None.
        """
        if metric not in BP_HEADLINE_METRIC_KEYS:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                                f"Invalid metric: {metric}")
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            if company_id is not None:
                co_ids: list[UUID] = [company_id]
            else:
                # Портфельный режим: репозиторий сам отсекает include_in_rollups=false,
                # но ТОЛЬКО когда область не задана — при явной области компании уже
                # выбраны вызывающим, иначе пользователь с областью из одной такой
                # компании не увидит собственного прогноза.
                co_ids = list(await self.uow.bp.distinct_companies_with_bp(
                    scope_company_ids=scope_company_ids,
                ))
            qkeys = ("q1", "q2", "q3", "q4")
            agg = {"plan": [0.0] * 4, "fact": [0.0] * 4}
            has = {"plan": [False] * 4, "fact": [False] * 4}
            per = []
            for cid in co_ids:
                cur = [await bp_compute(session, cid, year, q) for q in qkeys]
                prior = [await bp_compute(session, cid, year - 1, q) for q in qkeys]
                dplan = [_f(v) for v in ytd_to_deltas([c[metric]["plan"] for c in cur])]
                dfact = [_f(v) for v in ytd_to_deltas([c[metric]["fact"] for c in cur])]
                dprior = [_f(v) for v in ytd_to_deltas([c[metric]["fact"] for c in prior])]
                for i in range(4):
                    if dplan[i] is not None:
                        agg["plan"][i] += dplan[i]
                        has["plan"][i] = True
                    if dfact[i] is not None:
                        agg["fact"][i] += dfact[i]
                        has["fact"][i] = True
                per.append(forecast_quarters(
                    dplan, dfact,
                    prior_q_fact=dprior if any(v is not None for v in dprior) else None,
                ))
            q_plan = [agg["plan"][i] if has["plan"][i] else None for i in range(4)]
            q_fact = [agg["fact"][i] if has["fact"][i] else None for i in range(4)]

            if company_id is not None:
                r = per[0]
                return BpQuarterOutlook(
                    year=year, metric=metric, scope="company",
                    company_id=company_id, co_count=1,
                    q_plan=q_plan, q_fact=q_fact,
                    projections=[BpQuarterProjection(
                        period=p.period, value=p.value, low=p.low, high=p.high, co_count=1,
                    ) for p in r.projections],
                    expected_year=r.expected_year,
                    method=r.method, confidence=r.confidence, note=r.note,
                )

            # ── Портфель: Σ по-компанейских проекций ──
            last_fact_i = max((i for i in range(4) if q_fact[i] is not None), default=-1)
            psum: dict[str, dict] = {}
            for r in per:
                for p in r.projections:
                    i = int(p.period[1]) - 1
                    # «прогноз» кварталов, где у портфеля уже есть факт (компания
                    # без q1 и т.п.) — не суммируем: бары там фактические.
                    if i <= last_fact_i or p.value is None:
                        continue
                    s = psum.setdefault(p.period, {
                        "v": 0.0, "lo": 0.0, "hi": 0.0, "cnt": 0,
                        "lo_ok": True, "hi_ok": True,
                    })
                    s["v"] += p.value
                    s["cnt"] += 1
                    if p.low is None:
                        s["lo_ok"] = False
                    else:
                        s["lo"] += p.low
                    if p.high is None:
                        s["hi_ok"] = False
                    else:
                        s["hi"] += p.high
            projections = [
                BpQuarterProjection(
                    period=q, value=s["v"],
                    low=(s["lo"] if s["lo_ok"] else None),
                    high=(s["hi"] if s["hi_ok"] else None),
                    co_count=s["cnt"],
                )
                for q, s in sorted(psum.items())
            ]
            methods: dict[str, int] = {}
            for r in per:
                if r.method != "none":
                    methods[r.method] = methods.get(r.method, 0) + 1
            confs = [r.confidence for r in per if r.projections]
            conf = min(confs, key=lambda c: _QO_CONF_ORD.get(c, 0)) if confs else "none"
            real_methods = [m for m in methods if m != "actual"]
            method = ("mixed" if len(real_methods) > 1
                      else (real_methods[0] if real_methods else "none"))
            exp_vals = [r.expected_year for r in per if r.expected_year is not None]
            note = (
                "Σ по-компанейских прогнозов · "
                + ", ".join(f"{_QO_METHOD_RU.get(m, m)}: {n}"
                            for m, n in sorted(methods.items(), key=lambda t: -t[1]))
                if methods else "Недостаточно данных для квартального прогноза"
            )
            return BpQuarterOutlook(
                year=year, metric=metric, scope="portfolio", co_count=len(co_ids),
                q_plan=q_plan, q_fact=q_fact, projections=projections,
                expected_year=(sum(exp_vals) if exp_vals else None),
                method=method, confidence=conf, note=note,
            )

    async def forecast_company(
        self, company_id: UUID, base_year: int, horizon: int = 2,
    ) -> BpCompanyForecast:
        horizon = max(1, min(int(horizon), 5))
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            years = await self.uow.bp.years_for_company(company_id)
            # История шире годов bp_records: НСБУ-факты есть и за годы без строк
            # БП (2021+) — пустые годы отпадут сами (значений не будет).
            hist_years = sorted({
                *(y for y in years if y <= base_year),
                *range(base_year - _MAX_HISTORY + 1, base_year + 1),
            })[-_MAX_HISTORY:]

            company = await self.uow.bp.get_company(company_id)
            name = (
                (company.name_short or company.name_ru or company.code)
                if company else None
            ) or str(company_id)
            code = company.code if company else None

            annual_by_year: dict[int, dict] = {}
            for y in hist_years:
                # nsbu_fallback на всю глубину: НСБУ-факты лежат с 2021 — иначе
                # тренд строится по огрызку серии (2-3 точки вместо 5-6).
                annual_by_year[y] = await bp_compute(
                    session, company_id, y, "annual", nsbu_fallback=True,
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
