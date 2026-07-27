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

from app.core.forecast import (
    ForecastResult,
    forecast_annual,
    forecast_quarters,
    seasonal_shares,
    split_by_shares,
)
from app.schemas.kpi_forecast import (
    CompanyForecast,
    ForecastBlock,
    ForecastPoint,
    IndicatorForecast,
    KpiPlanDraft,
    KpiPlanDraftIndicator,
    ManagerForecast,
    SeriesPoint,
)
from app.services.bp_kpi_helpers import (
    kpi_compute_completion,
    kpi_is_cumulative,
    kpi_period_weight,
    kpi_quarter_deltas,
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


def _block(
    r: ForecastResult, shares: Optional[list[float]] = None,
) -> ForecastBlock:
    """ForecastResult → DTO. Если переданы сезонные доли `shares` — каждая годовая
    проекция дополнительно раскладывается по кварталам (для будущих лет)."""
    d = r.to_dict()
    pts: list[ForecastPoint] = []
    for p in d["projections"]:
        q = split_by_shares(p["value"], shares) if (shares and p["value"] is not None) else None
        pts.append(ForecastPoint(
            period=p["period"], value=p["value"], low=p["low"], high=p["high"], quarters=q,
        ))
    return ForecastBlock(
        method=d["method"],
        confidence=d["confidence"],
        points_used=d["points_used"],
        note=d["note"],
        expected_year=d["expected_year"],
        projections=pts,
    )


class KpiForecastService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def plan_draft(self, company_id: UUID, target_year: int) -> KpiPlanDraft:
        """Черновик ПЛАНОВ KPI на target_year из истории фактов.

        Индикаторы сопоставляются между годами по bp_metric_key/нормализованному
        имени (_ind_key). Связанные с БП строки пропускаются — их план тянется из
        Бизнес-плана (reference-pull). Годовое предложение — forecast_annual
        (CAGR/OLS) по годовым фактам (kpi_year_pair, с YTD-фолбэком); квартальная
        разбивка — сезонность исторических КВАРТАЛЬНЫХ значений KPI, приведённых
        к суммам ЗА КВАРТАЛ по конвенции строки (`quarters_mode`); предложение
        отдаётся обратно В КОНВЕНЦИИ целевой строки. Ничего не пишет: применение —
        редактором в пустые планы + штатное сохранение (модерация/лок сохраняются).
        """
        async with self.uow:
            years = await self.uow.kpi.years_for_company(company_id)
            hist = sorted(y for y in years if y < target_year)[-_MAX_HISTORY:]
            mgrs = await self.uow.kpi.get_managers_for_years(
                company_id, [*hist, target_year])
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

            target_mgrs = by_year.get(target_year, [])
            if not target_mgrs:
                return KpiPlanDraft(
                    company_id=company_id, target_year=target_year, base_years=hist,
                    note=(f"Нет KPI за {target_year} — сначала создайте структуру "
                          "(шаблон или копия прошлого года)"))
            if not hist:
                return KpiPlanDraft(
                    company_id=company_id, target_year=target_year,
                    note="Нет исторических лет KPI — черновик построить не из чего")

            inds_out: list[KpiPlanDraftIndicator] = []
            for m in target_mgrs:
                mgr_title = m.short_title or m.title or ""
                for ind in m.indicators:
                    nm = ind.name or ""
                    cur_plan = _f(ind.plan_year)
                    if getattr(ind, "bp_metric_key", None):
                        inds_out.append(KpiPlanDraftIndicator(
                            name=nm, manager=mgr_title, linked=True,
                            current_plan_year=cur_plan,
                            note="План тянется из Бизнес-плана (связанный KPI)"))
                        continue
                    ikey = _ind_key(ind)
                    syears: list[int] = []
                    svals: list[float] = []
                    hist_qp: list[list] = []
                    hist_qf: list[list] = []
                    for y in hist:
                        oind = idx_by_year.get(y, {}).get(ikey)
                        if oind is None:
                            continue
                        _plan_o, fact_o, _src = kpi_year_pair(oind)
                        # Суммы ЗА КВАРТАЛ по конвенции строки: и pace-оценка,
                        # и сезонные доли осмысленны только на дельтах.
                        qp_o = kpi_quarter_deltas(oind, "plan")
                        qf_o = kpi_quarter_deltas(oind, "fact")
                        if fact_o is not None:
                            syears.append(y)
                            svals.append(float(fact_o))
                        elif y == hist[-1] and any(x is not None for x in qf_o):
                            # Незакрытый последний год: честная pace-оценка по его
                            # кварталам (метод 'plan' не годится — это не факт).
                            qr = forecast_quarters(qp_o, qf_o)
                            if (qr.method in ("pace", "seasonal", "run_rate", "actual")
                                    and qr.expected_year is not None):
                                syears.append(y)
                                svals.append(float(qr.expected_year))
                        hist_qp.append(qp_o)
                        hist_qf.append(qf_o)
                    if not syears:
                        inds_out.append(KpiPlanDraftIndicator(
                            name=nm, manager=mgr_title,
                            current_plan_year=cur_plan,
                            note="Нет истории факта по этому KPI"))
                        continue
                    horizon = target_year - max(syears)
                    if horizon < 1:
                        inds_out.append(KpiPlanDraftIndicator(
                            name=nm, manager=mgr_title, current_plan_year=cur_plan,
                            note="Год уже присутствует в истории"))
                        continue
                    af = forecast_annual(syears, svals, horizon)
                    proj = next(
                        (p for p in af.projections if p.period == str(target_year)),
                        None)
                    if proj is None or proj.value is None:
                        inds_out.append(KpiPlanDraftIndicator(
                            name=nm, manager=mgr_title, current_plan_year=cur_plan,
                            method=af.method, confidence=af.confidence,
                            note=af.note or "Прогноз недоступен"))
                        continue
                    # Сезонность: факт прошлых лет → план прошлых лет (за квартал).
                    shares = seasonal_shares(hist_qf) or seasonal_shares(hist_qp)
                    proposed_q = None
                    if shares:
                        qs = split_by_shares(proj.value, shares) or []
                        if kpi_is_cumulative(ind):
                            # Строка ведётся нарастающим итогом — отдаём предложение
                            # в её конвенции, иначе редактор запишет дельты в
                            # накопительные поля.
                            acc, cum = 0.0, []
                            for v in qs:
                                if v is None:
                                    cum.append(None)
                                    continue
                                acc += float(v)
                                cum.append(acc)
                            qs = cum
                        proposed_q = [
                            round(v, 2) if v is not None else None for v in qs]
                    inds_out.append(KpiPlanDraftIndicator(
                        name=nm, manager=mgr_title, linked=False,
                        current_plan_year=cur_plan,
                        proposed_plan_year=round(proj.value, 2),
                        low=(round(proj.low, 2) if proj.low is not None else None),
                        high=(round(proj.high, 2) if proj.high is not None else None),
                        proposed_q=proposed_q,
                        method=af.method, confidence=af.confidence, note=af.note))
            return KpiPlanDraft(
                company_id=company_id, target_year=target_year, base_years=hist,
                indicators=inds_out,
                note="Черновик из истории — применяется только в пустые планы")

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
                    # P0 аудита KPI: движок (pace/run-rate/сезонность) ждёт суммы
                    # ЗА КВАРТАЛ. Строки с нарастающим итогом конвертируем в
                    # дельты по явной конвенции строки — иначе Σфакт/Σплан и
                    # run-rate считались по накопленным значениям.
                    q_plan = kpi_quarter_deltas(ind, "plan")
                    q_fact = kpi_quarter_deltas(ind, "fact")

                    prior = idx_by_year.get(base_year - 1, {}).get(ikey)
                    prior_q = (
                        kpi_quarter_deltas(prior, "fact") if prior is not None else None
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

                    # Сезонность для разбивки будущих ЛЕТ по кварталам. Приоритет:
                    # план текущего года (намеренная сезонность) → средние план
                    # прошлых лет → факт прошлых лет.
                    shares = seasonal_shares([q_plan])
                    if shares is None:
                        hist_qp: list[list] = []
                        hist_qf: list[list] = []
                        for y in hist_years:
                            oind = idx_by_year.get(y, {}).get(ikey)
                            if oind is None:
                                continue
                            hist_qp.append(kpi_quarter_deltas(oind, "plan"))
                            hist_qf.append(kpi_quarter_deltas(oind, "fact"))
                        shares = seasonal_shares(hist_qp) or seasonal_shares(hist_qf)

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
                        annual=_block(af, shares),
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
