"""Business Plan + KPI compute helpers — Python port of legacy logic.

Functions mirror the JS helpers in index.html lines 35357–42700:
- _bpCompute        → bp_compute
- _bpComputeSummary → bp_compute_summary
- _bpFactFromNSBU   → bp_fact_from_nsbu
- _bpAttentionIssues→ bp_attention_issues
- _kpiComputeSummary→ kpi_compute_summary
- _kpiAttentionIssues→ kpi_attention_issues
- _kpiComputeCompletion → kpi_compute_completion
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bp_kpi import (
    BP_METRIC_DIRECTION,
    BP_METRIC_KEYS,
    BP_METRICS,
    BpRecord,
    KpiIndicator,
    KpiManager,
)
from app.models.company import Company

# Sector colors for fallback in dashboards (mirror legacy SECTOR_SOLID)
SECTOR_FALLBACK_COLORS = {
    "mining": "#9B8EC4",
    "metallurgy": "#9B8EC4",
    "mining_metallurgy": "#9B8EC4",
    "oil_gas": "#0A7B5E",
    "oilgas": "#0A7B5E",
    "energy": "#EF9F27",
    "transport": "#378ADD",
    "transport_communications": "#378ADD",
    "telecom": "#378ADD",
    "chemistry": "#888780",
    "other": "#888780",
}


def sector_color(co: Company) -> Optional[str]:
    if co.sector and co.sector.color_hex:
        return co.sector.color_hex
    if co.sector and co.sector.code:
        return SECTOR_FALLBACK_COLORS.get(co.sector.code, "#888780")
    return "#888780"


def sector_code(co: Company) -> Optional[str]:
    return co.sector.code if co.sector else None


# ─── BP: NSBU autofill ────────────────────────────────────────────

async def bp_fact_from_nsbu(
    db: AsyncSession,
    company_id: UUID,
    year: int,
    metric: str,
    standard: str = "NSBU",
) -> Optional[Decimal]:
    """Годовой факт BP-метрики из финотчётности (реальный источник).

    Берёт значение из `financial_reports` (standard='NSBU' по умолчанию;
    'IFRS' — для исторических серий генератора планов, is_detailed=false,
    quarter IS NULL) × `financial_lines`, где line_code = канонический id и
    совпадает с ключом BP-метрики (revenue/cogs/grossProfit/opProfit/finIncome/
    finCost/pbt/tax/profit/ebitda и т.д.). Только period='annual'.
    Возвращает None, если данных нет (напр. год ещё не закрыт).

    Раньше функция смотрела в несуществующую таблицу financials_detailed и
    всегда возвращала None → автозаполнение факта было мёртвым.
    """
    if standard not in ("NSBU", "IFRS"):
        return None
    try:
        r = await db.execute(
            text(
                "SELECT fl.value FROM financial_reports fr "
                "JOIN financial_lines fl ON fl.report_id = fr.id "
                "WHERE fr.company_id::text = :cid AND fr.standard = :std "
                "AND COALESCE(fr.is_detailed, false) = false AND fr.quarter IS NULL "
                "AND fr.year = :yr AND fl.line_code = :metric AND fl.value IS NOT NULL "
                "ORDER BY fr.updated_at DESC NULLS LAST LIMIT 1"
            ),
            {"cid": str(company_id), "yr": year, "metric": metric, "std": standard},
        )
        v = r.scalar_one_or_none()
        return Decimal(str(v)) if v is not None else None
    except Exception:
        return None


# ─── BP: конвенция кварталов = НАРАСТАЮЩИЙ ИТОГ (НСБУ) ───────────

def ytd_to_deltas(vals: list) -> list:
    """Кварталы БП хранятся нарастающим итогом (НСБУ: q1=1 кв, q2=полугодие,
    q3=9 мес, q4=год) — подтверждено данными всех компаний. Величина «за квартал»
    = ytd[n] − ytd[n−1] (для q1 — сам ytd[0]).

    Честный None, когда сам квартал ИЛИ предыдущий не заполнен: иначе полугодие
    компании без q1 целиком легло бы в «Q2». Вход/выход — списки по [q1..q4]
    (Decimal | None), длина сохраняется.
    """
    out: list = []
    prev = None
    for i, v in enumerate(vals):
        if v is None or (i > 0 and prev is None):
            out.append(None)
        else:
            d = Decimal(v) - (Decimal(prev) if i > 0 else Decimal(0))
            out.append(d)
        prev = v
    return out


# ─── BP compute (single company, year, period) ───────────────────

async def bp_compute(
    db: AsyncSession,
    company_id: UUID,
    year: int,
    period: str,
    nsbu_fallback: bool = True,
) -> dict[str, dict]:
    """Mirror of legacy `_bpCompute(co, year, period)`.

    Returns dict of {metric_key: {plan, expect, fact, fact_auto}}.
    Auto-calculates derived metrics (grossProfit, opProfit, hhProfit, pbt, profit)
    from inputs when not explicitly stored. Auto-fills `fact` from NSBU only
    for period='annual'.

    ВАЖНО: для period='q1'..'q4' все значения — НАРАСТАЮЩИМ ИТОГОМ с начала года
    (конвенция НСБУ-отчётности; см. ytd_to_deltas). Производные формулы линейны,
    поэтому одинаково верны для YTD и для дельт.
    """
    # Load all stored BP records
    rows = (
        await db.execute(
            select(BpRecord)
            .where(BpRecord.company_id == company_id)
            .where(BpRecord.year == year)
            .where(BpRecord.period == period)
        )
    ).scalars().all()

    stored: dict[str, dict] = {r.metric: {"plan": r.plan, "expect": r.expect, "fact": r.fact} for r in rows}

    out: dict[str, dict] = {}
    for k in BP_METRIC_KEYS:
        cell = stored.get(k, {"plan": None, "expect": None, "fact": None})
        out[k] = {
            "plan": cell.get("plan"),
            "expect": cell.get("expect"),
            "fact": cell.get("fact"),
            "fact_auto": False,
            "fact_source": None,        # None | "nsbu" | "ytd" — источник годового факта
            "fact_source_value": None,  # значение источника (всегда, для сравнения в редакторе)
        }

    # Auto-calc derived metrics for each column (plan/expect/fact)
    def _v(metric: str, col: str):
        return out[metric][col] if out[metric][col] is not None else None

    for col in ("plan", "expect", "fact"):
        rev = _v("revenue", col)
        cogs = _v("cogs", col)
        if rev is not None and cogs is not None and out["grossProfit"][col] is None:
            out["grossProfit"][col] = (Decimal(rev) - abs(Decimal(cogs))).quantize(Decimal("0.001"))

        gp = out["grossProfit"][col]
        opex = _v("opExpenses", col)
        other_inc = _v("otherOpInc", col)
        if gp is not None and opex is not None and out["opProfit"][col] is None:
            out["opProfit"][col] = (
                Decimal(gp) - abs(Decimal(opex)) + (Decimal(other_inc) if other_inc is not None else Decimal(0))
            ).quantize(Decimal("0.001"))

        op = out["opProfit"][col]
        fi = _v("finIncome", col)
        fc = _v("finCost", col)
        if op is not None and out["hhProfit"][col] is None:
            out["hhProfit"][col] = (
                Decimal(op)
                + (Decimal(fi) if fi is not None else Decimal(0))
                - (abs(Decimal(fc)) if fc is not None else Decimal(0))
            ).quantize(Decimal("0.001"))

        if out["hhProfit"][col] is not None and out["pbt"][col] is None:
            out["pbt"][col] = out["hhProfit"][col]

        pbt = out["pbt"][col]
        tax = _v("tax", col)
        if pbt is not None and tax is not None and out["profit"][col] is None:
            out["profit"][col] = (Decimal(pbt) - abs(Decimal(tax))).quantize(Decimal("0.001"))

    # Автозаполнение годового факта (period='annual'), если он не введён вручную:
    #   1) из НСБУ-финотчётности (точный годовой факт закрытого года) → source='nsbu';
    #   2) иначе — значение Q4: кварталы хранятся НАРАСТАЮЩИМ ИТОГОМ, поэтому
    #      ytd(q4) = весь год → 'ytd'. НИКОГДА не Σ Q1..Q4 (сумма YTD ≈ 2.5× года)
    #      и не q3/q2 (занизили бы год).
    if period == "annual":
        # Кварталы — для YTD-источника (годовой факт = значение q4).
        qrows = (
            await db.execute(
                select(BpRecord)
                .where(BpRecord.company_id == company_id)
                .where(BpRecord.year == year)
                .where(BpRecord.period.in_(["q1", "q2", "q3", "q4"]))
            )
        ).scalars().all()
        # Ключуем по периоду (не список!): «взять q4» на неключёванном списке
        # не выражается и зависит от порядка строк.
        qfacts: dict[str, dict[str, Decimal]] = {}
        for qr in qrows:
            if qr.fact is not None:
                qfacts.setdefault(qr.metric, {})[qr.period] = qr.fact
        for k in BP_METRIC_KEYS:
            # Значение источника считаем ВСЕГДА (для пометки/сравнения в редакторе),
            # даже если факт уже введён вручную. Приоритет: НСБУ → ytd(q4).
            sv = None
            ssrc = None
            if nsbu_fallback:
                sv = await bp_fact_from_nsbu(db, company_id, year, k)
                if sv is not None:
                    ssrc = "nsbu"
            if sv is None:
                q4v = qfacts.get(k, {}).get("q4")
                if q4v is not None:
                    sv = q4v
                    ssrc = "ytd"
            if sv is not None:
                out[k]["fact_source_value"] = sv
                out[k]["fact_source"] = ssrc
                if out[k]["fact"] is None:   # автоподстановка — только в пустой факт
                    out[k]["fact"] = sv
                    out[k]["fact_auto"] = True

    return out


# ─── BP attention issues ──────────────────────────────────────────

def bp_pct(fact: Optional[Decimal], plan: Optional[Decimal]) -> Optional[float]:
    if plan is None or plan == 0 or fact is None:
        return None
    return float(fact) / float(plan)


def bp_fmt(v: Optional[Decimal]) -> str:
    if v is None:
        return "—"
    av = abs(float(v))
    if av >= 1000:
        return f"{round(float(v)):,}".replace(",", " ")
    if av >= 10:
        return f"{float(v):.0f}"
    return f"{float(v):.2f}"


async def bp_attention_issues(
    db: AsyncSession,
    company_id: UUID,
    year: int,
    period: str,
) -> list[dict]:
    """Mirror of legacy `_bpAttentionIssues`.

    Returns up to 5 issues sorted by severity. Skips KPI-side issues which
    are returned by kpi_attention_issues separately.
    """
    issues: list[dict] = []
    comp = await bp_compute(db, company_id, year, period)

    # Rule 1: deviation ≥15% below plan on key metrics
    label_by_key = {m["key"]: m["label"] for m in BP_METRICS}
    for k in ("revenue", "opProfit", "profit"):
        c = comp[k]
        if c["plan"] is not None and c["fact"] is not None and c["plan"] != 0:
            ratio = float(c["fact"]) / float(c["plan"])
            if ratio < 0.85:
                issues.append({
                    "severity": "high" if ratio < 0.70 else "medium",
                    "title": label_by_key[k],
                    "value": f"{round(ratio * 100)}% плана",
                    "detail": f"Факт {bp_fmt(c['fact'])} vs план {bp_fmt(c['plan'])}",
                })

    # Rule 2: cost ratio increase
    if (
        comp["cogs"]["fact"] is not None and comp["revenue"]["fact"] is not None
        and comp["revenue"]["fact"] != 0
    ):
        cost_ratio = abs(float(comp["cogs"]["fact"])) / float(comp["revenue"]["fact"])
        if (
            comp["cogs"]["plan"] is not None and comp["revenue"]["plan"] is not None
            and comp["revenue"]["plan"] != 0
        ):
            cost_ratio_plan = abs(float(comp["cogs"]["plan"])) / float(comp["revenue"]["plan"])
            if cost_ratio > cost_ratio_plan * 1.10:
                issues.append({
                    "severity": "medium",
                    "title": "Рост доли себестоимости",
                    "value": f"{round(cost_ratio * 100)}% vs план {round(cost_ratio_plan * 100)}%",
                    "detail": "Давление на маржинальность",
                })

    sev_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: sev_order.get(x["severity"], 9))
    return issues[:5]


# ─── KPI compute ──────────────────────────────────────────────────

def kpi_ratio(
    plan: Optional[float], fact: Optional[float], direction: str = "up",
) -> Optional[float]:
    """Отношение выполнения по паре (план, факт) с учётом направления.

    'up'   (больше=лучше): факт/план, осмысленно лишь при положительном плане.
    'down' (меньше=лучше): план/факт, осмысленно лишь при положительных план и факт.
    Отрицательный/нулевой план (плановый убыток) инвертировал бы знак (−187% при
    плане-убытке и факте-прибыли) — это артефакт, не оценка → None.
    """
    if plan is None or fact is None:
        return None
    plan, fact = float(plan), float(fact)
    if (direction or "up") == "down":
        if plan <= 0 or fact <= 0:
            return None
        return plan / fact
    if plan <= 0:
        return None
    return fact / plan


def kpi_bp_effective(
    ind: KpiIndicator, period: str, bp_cell: Optional[dict],
) -> Optional[tuple]:
    """Эффективная пара (plan, fact, direction) для СВЯЗАННОГО индикатора.

    Для индикатора с bp_metric_key берёт план/факт из BP-ячейки `bp_cell`
    ({'plan','fact'} нужного периода), direction форсит из канона. Квартал, по
    которому в BP значения нет, падает на хранимый q*_plan/q*_fact индикатора
    (связываем по умолчанию годовую строку; кварталы — fallback). Возвращает
    None, если индикатор не связан или BP-ячейки нет (вызывающий тогда считает
    обычным kpi_compute_completion по хранимым значениям).
    """
    key = getattr(ind, "bp_metric_key", None)
    if not key or not bp_cell:
        return None
    direction = BP_METRIC_DIRECTION.get(key, "up")
    plan = bp_cell.get("plan")
    fact = bp_cell.get("fact")
    if period not in ("year", "annual") and plan is None and fact is None:
        # Фолбэк на q*-поля индикатора — ТОЛЬКО парой целиком. BP-кварталы хранятся
        # нарастающим итогом (YTD), конвенция q*-полей KPI не закреплена; смешение
        # одной стороны из BP с другой из индикатора (факт «за квартал» ÷ план YTD)
        # дало бы бессмысленный % на министерских экранах.
        plan = getattr(ind, f"{period}_plan", None)
        fact = getattr(ind, f"{period}_fact", None)
    return (plan, fact, direction)


def kpi_period_weight(ind: KpiIndicator, period: str) -> float:
    """Вес индикатора для периода: годовой для 'year'; квартальный с ФОЛБЭКОМ на
    годовой для кварталов (поквартальный вес часто не заполняют). Единый источник —
    чтобы сводка, attention и by_quarter считали вес одинаково (раньше attention
    фолбэк не делал → списки расходились со сводкой)."""
    if period in ("year", "annual"):
        return float(ind.weight or 0)
    w = float(getattr(ind, f"{period}_weight", 0) or 0)
    return w if w != 0 else float(ind.weight or 0)


def kpi_is_cumulative(ind: KpiIndicator) -> bool:
    """Кварталы строки заведены нарастающим итогом? (явный признак строки)."""
    return str(getattr(ind, "quarters_mode", "per_quarter") or "") == "cumulative"


def kpi_quarter_deltas(ind: KpiIndicator, field: str = "plan") -> list:
    """Кварталы строки как суммы ЗА КВАРТАЛ [q1..q4] (учитывая её конвенцию).

    Для 'cumulative' — разности соседних (честный None при разрыве, как в БП);
    для 'per_quarter' — значения как есть. Нужно там, где арифметика требует
    независимых кварталов: движок прогноза (pace/run-rate/сезонность).
    """
    vals = [getattr(ind, f"q{i}_{field}", None) for i in (1, 2, 3, 4)]
    vals = [float(v) if v is not None else None for v in vals]
    if not kpi_is_cumulative(ind):
        return vals
    out, prev = [], None
    for i, v in enumerate(vals):
        if v is None or (i > 0 and prev is None):
            out.append(None)
        else:
            out.append(v - (prev if i > 0 else 0.0))
        prev = v
    return out


def kpi_year_pair(ind: KpiIndicator) -> tuple:
    """Годовая пара (plan, fact, source) для индикатора.

    'annual' — заведены plan_year+fact_year; иначе годовое значение выводится
    из кварталов С УЧЁТОМ КОНВЕНЦИИ строки (`quarters_mode`, решение владельца):
      • 'cumulative' → год = ПОСЛЕДНИЙ заполненный квартал (q4 = год), source 'ytd_q4';
      • 'per_quarter' → год = Σ q1..q4, source 'ytd' (прежнее поведение).

    P0 аудита KPI (07.2026): раньше суммировалось ВСЕГДА, а 75% строк заведены
    нарастающим итогом → годовая цифра завышалась примерно в 2.5 раза
    (UzAuto: план 437 000 → Σ кварталов 1 041 050). Плюс годовой план брался
    из кварталов, даже когда `plan_year` заполнен, — теперь он приоритетен.
    """
    plan = ind.plan_year
    fact = ind.fact_year
    if plan is not None and float(plan) != 0 and fact is not None:
        return (float(plan), float(fact), "annual")

    if kpi_is_cumulative(ind):
        # Нарастающий итог: берём последний квартал, где есть ПАРА план+факт
        # (иначе сравнивали бы план девяти месяцев с фактом полугодия).
        last_p = last_f = None
        for q in ("q1", "q2", "q3", "q4"):
            qp = getattr(ind, f"{q}_plan", None)
            qf = getattr(ind, f"{q}_fact", None)
            if qp is not None and qf is not None and float(qp) != 0:
                last_p, last_f = float(qp), float(qf)
        if last_p is not None:
            # Годовой план известен явно — он точнее последнего закрытого квартала.
            plan_out = float(plan) if (plan is not None and float(plan) != 0) else last_p
            return (plan_out, last_f, "ytd_q4")
        return (None, None, None)

    sum_p, sum_f = 0.0, 0.0
    had_pair = False
    for q in ("q1", "q2", "q3", "q4"):
        qp = getattr(ind, f"{q}_plan", None)
        qf = getattr(ind, f"{q}_fact", None)
        if qp is not None and qf is not None and float(qp) != 0:
            sum_p += float(qp)
            sum_f += float(qf)
            had_pair = True
    if had_pair and sum_p != 0:
        return (sum_p, sum_f, "ytd")
    return (None, None, None)


def kpi_compute_completion(ind: KpiIndicator, period: str) -> Optional[float]:
    """Compute fact/plan ratio for an indicator at a given period.

    period: 'year' | 'q1'..'q4'. Для 'year' — YTD-fallback (Σ Q1..Q4) когда
    годовые plan_year/fact_year не введены (см. kpi_year_pair).
    """
    if period in ("year", "annual"):
        plan, fact, _src = kpi_year_pair(ind)
    else:
        plan = getattr(ind, f"{period}_plan", None)
        fact = getattr(ind, f"{period}_fact", None)
    return kpi_ratio(
        plan, fact, (getattr(ind, "direction", "up") or "up"),
    )


def kpi_status_for_pct(pct: float) -> str:
    if pct >= 100:
        return "over"
    if pct >= 95:
        return "hit"
    if pct >= 75:
        return "risk"
    if pct >= 50:
        return "crit"
    return "fail"


async def kpi_attention_issues(
    db: AsyncSession,
    company_id: UUID,
    year: int,
    period: str,
) -> list[dict]:
    """Mirror of legacy `_kpiAttentionIssues`."""
    period_key = "year" if period == "annual" else period
    rows = (
        await db.execute(
            select(KpiManager)
            .where(KpiManager.company_id == company_id)
            .where(KpiManager.year == year)
            .options(selectinload(KpiManager.indicators))
            .order_by(KpiManager.sort_order)
        )
    ).scalars().all()

    # Read-through BP/НСБУ для связанных строк (один bp_compute на (компания, период)).
    _bp_comp = None
    if any(getattr(i, "bp_metric_key", None) for mgr in rows for i in mgr.indicators):
        _bp_comp = await bp_compute(
            db, company_id, year, "annual" if period_key == "year" else period_key,
        )

    issues: list[dict] = []
    for mgr in rows:
        for ind in mgr.indicators:
            key = getattr(ind, "bp_metric_key", None)
            if key and _bp_comp is not None:
                eff = kpi_bp_effective(ind, period_key, _bp_comp.get(key))
                ratio = kpi_ratio(*eff) if eff else None
            else:
                ratio = kpi_compute_completion(ind, period_key)
            if ratio is None:
                continue
            w = kpi_period_weight(ind, period_key)  # единый вес (с фолбэком на годовой)
            if w < 5:
                continue
            pct = min(150.0, max(0.0, ratio * 100))  # clamp как в сводке
            if pct < 75:
                short = (mgr.short_title or mgr.title or "")[:30]
                issues.append({
                    "severity": "high" if pct < 50 else "medium",
                    "title": (ind.name or "")[:60],
                    "value": f"{round(pct)}% (вес {round(w)})",
                    "detail": f"{short}",
                })

    sev = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: sev.get(x["severity"], 9))
    return issues[:3]
