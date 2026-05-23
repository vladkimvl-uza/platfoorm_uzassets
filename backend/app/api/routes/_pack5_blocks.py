"""
backend/app/api/routes/_pack5_blocks.py
Pack 5 helper functions для Executive Dashboard:
  - build_economic_effect_block (Row 2.55)
  - build_bp_tracker_block       (Row 2.6)
  - build_tax_contribution_block (Row 2.7)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Iterable
from decimal import Decimal

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from dataclasses import dataclass
from app.schemas.executive_dashboard import (
    ExecEconomicEffectBlock,
    ExecEEKpi,
    ExecEEProject,
    ExecBPBlock,
    ExecBPCompanyRow,
    ExecTaxBlock,
    ExecTaxKpi,
    ExecTaxTopPayer,
)


# ═══════════════════ Constants ═══════════════════

# Бюджет Республики Узбекистан (трлн UZS), приближённо
# Источник: монолит window._UZ_BUDGET
_UZ_BUDGET_TRLN: Dict[int, float] = {
    2021: 230.0,
    2022: 260.0,
    2023: 290.0,
    2024: 320.0,
    2025: 350.0,
    2026: 380.0,
}

# VAT rate (Узбекистан)
_VAT_RATE = 0.12

# IFRS PL canonical line_codes (из data check)
_IFRS_PL_REVENUE = "revenue"
_IFRS_PL_EBITDA = "ebitda"
_IFRS_PL_PROFIT = "profit"
_IFRS_PL_TAX = "tax"
_IFRS_PL_OP_PROFIT = "opProfit"
_IFRS_PL_DEPRECIATION = "depreciation"

# Pack 7.27: NSBU PL line codes (fallback fact source for BP tracker)
_NSBU_PL_REVENUE = "revenue"
_NSBU_PL_EBITDA = "ebitda"
_NSBU_PL_PROFIT = "profit"


# ═══════════════════ Block 1: Экономический эффект ═══════════════════

def build_economic_effect_block(
    projects: Iterable[Any],
    year: int,
    co_id_to_name: Dict[Any, str],
    co_id_to_sector: Dict[Any, str],
) -> ExecEconomicEffectBlock:
    """
    Read economic effect data from Project.extra JSONB field.
    Format expected (как в монолите):
        extra: {
          "economicEffect": {
            "plannedValue": <number>,
            "realizedValue": <number>,
            "unit": "млрд" | "млн" | "трлн",
            "currency": "UZS" | "USD"
          }
        }

    Если в extra нет economicEffect (текущее состояние БД) — возвращаем
    has_data=False и пустые KPI, что приведёт к empty state на frontend.
    """
    UNIT_MULT = {"трлн": 1e12, "млрд": 1e9, "млн": 1e6}
    USD_RATE = 12700  # приближённо

    realized_sum = 0.0
    planned_sum = 0.0
    done_count = 0
    active_count = 0
    total_count = 0
    project_rows: List[ExecEEProject] = []

    for p in projects:
        extra = getattr(p, "extra", None) or {}
        ee = extra.get("economicEffect") if isinstance(extra, dict) else None
        if not isinstance(ee, dict):
            continue

        try:
            planned_raw = float(ee.get("plannedValue") or 0)
            realized_raw = float(ee.get("realizedValue") or 0)
        except (TypeError, ValueError):
            continue

        if planned_raw <= 0 and realized_raw <= 0:
            continue

        unit = ee.get("unit") or "млрд"
        currency = ee.get("currency") or "UZS"
        mult = UNIT_MULT.get(unit, 1)

        planned_uzs = planned_raw * mult
        realized_uzs = realized_raw * mult
        if currency == "USD":
            planned_uzs *= USD_RATE
            realized_uzs *= USD_RATE

        # Sanity cap: 100 трлн (отбрасываем явные ошибки данных)
        if max(planned_uzs, realized_uzs) > 1e14:
            continue

        realized_sum += realized_uzs
        planned_sum += planned_uzs
        total_count += 1
        status = (getattr(p, "status", None) or "").lower()
        if status == "done":
            done_count += 1
        elif status in ("active", "review"):
            active_count += 1

        co_id = getattr(p, "company_id", None)
        co_name = co_id_to_name.get(co_id, "—")
        sector = co_id_to_sector.get(co_id, "other")
        pct_realized = round(realized_uzs / planned_uzs * 100) if planned_uzs > 0 else 0

        project_rows.append(ExecEEProject(
            project_id=getattr(p, "id", None),
            title=getattr(p, "title", None) or "—",
            company_name=co_name,
            sector=sector,
            direction=None,
            status=status or "new",
            planned_value=planned_uzs / 1e9,   # convert to млрд для UI
            realized_value=realized_uzs / 1e9,
            pct_realized=pct_realized,
            unit="млрд сум",
        ))

    pipeline_sum = max(0.0, planned_sum - realized_sum)
    conversion_pct = round(realized_sum / planned_sum * 100) if planned_sum > 0 else 0
    has_data = total_count > 0

    # Top-10 by realized value
    project_rows.sort(key=lambda r: -r.realized_value)
    top_projects = project_rows[:10]

    return ExecEconomicEffectBlock(
        year=year,
        kpi=ExecEEKpi(
            realized_sum=realized_sum / 1e9,    # млрд для UI
            planned_sum=planned_sum / 1e9,
            pipeline_sum=pipeline_sum / 1e9,
            conversion_pct=conversion_pct,
            done_count=done_count,
            active_count=active_count,
            total_count=total_count,
            has_data=has_data,
        ),
        top_projects=top_projects,
    )


# ═══════════════════ Block 2: BP-трекер ═══════════════════

_METRIC_LABELS = {
    "revenue": "Выручка",
    "ebitda": "EBITDA",
    "profit": "Прибыль",
}


async def build_bp_tracker_block(
    db: AsyncSession,
    year: int,
    metric: str,
    co_id_to_name: Dict[Any, str],
    co_id_to_sector: Dict[Any, str],
    sector_filter: Optional[List[str]] = None,
) -> ExecBPBlock:
    """
    Performance Spine BP-tracker — port 1:1 of monolith _execBPData.

    Two modes:
      • plan-fact: when ≥30% of companies have BP plan for selected year
                   → compare fact / plan
      • yoy:       when plan is sparse but ≥3 companies have year+prev_year fact pairs
                   → compare fact_curr / fact_prev (динамика)

    Special handling for signed metrics (profit, ebitda):
      - Recovery (loss→profit) → cls='ok' with 'выход из убытка' label
      - Drop (profit→loss)    → cls='bad' with 'переход в убыток' label
      - Loss shrinking/growing → tracked separately

    Sources:
      - Plan:  bp_records.plan  (period='annual', metric=metric)
      - Fact:  bp_records.fact  (preferred — explicit BP), then NSBU financial_lines as fallback
    """
    from app.models.bp_kpi import BpRecord
    from app.models.financial import FinancialReport, FinancialLine

    metric_low = (metric or "revenue").lower()
    if metric_low not in ("revenue", "ebitda", "profit"):
        metric_low = "revenue"

    metric_label = _METRIC_LABELS[metric_low]
    prev_year = year - 1
    is_signed_metric = metric_low in ("profit", "ebitda")

    # ─── 1. Load BP records for selected year (plan + fact) ───
    q_bp_year = (
        select(BpRecord.company_id, BpRecord.plan, BpRecord.fact)
        .where(
            and_(
                BpRecord.year == year,
                BpRecord.period == "annual",
                BpRecord.metric == metric_low,
            )
        )
    )
    rs = await db.execute(q_bp_year)
    bp_plan_map: Dict[Any, float] = {}
    bp_fact_map: Dict[Any, float] = {}
    for co_id, plan_v, fact_v in rs.all():
        if plan_v is not None:
            try:
                bp_plan_map[co_id] = float(plan_v)
            except (TypeError, ValueError):
                pass
        if fact_v is not None:
            try:
                bp_fact_map[co_id] = float(fact_v)
            except (TypeError, ValueError):
                pass

    # ─── 2. Load BP fact for previous year (для yoy fallback) ───
    q_bp_prev = (
        select(BpRecord.company_id, BpRecord.fact)
        .where(
            and_(
                BpRecord.year == prev_year,
                BpRecord.period == "annual",
                BpRecord.metric == metric_low,
            )
        )
    )
    rs_prev = await db.execute(q_bp_prev)
    bp_prev_fact_map: Dict[Any, float] = {}
    for co_id, fact_v in rs_prev.all():
        if fact_v is not None:
            try:
                bp_prev_fact_map[co_id] = float(fact_v)
            except (TypeError, ValueError):
                pass

    # ─── 3. Load NSBU fact as fallback for current and previous year ───
    line_code_map = {
        "revenue": _NSBU_PL_REVENUE,
        "ebitda": _NSBU_PL_EBITDA,
        "profit": _NSBU_PL_PROFIT,
    }
    nsbu_line = line_code_map[metric_low]

    async def _load_nsbu(target_year: int) -> Dict[Any, float]:
        q = (
            select(FinancialReport.company_id, FinancialLine.value)
            .join(FinancialLine, FinancialLine.report_id == FinancialReport.id)
            .where(
                and_(
                    FinancialReport.year == target_year,
                    FinancialReport.standard == "NSBU",
                    FinancialReport.report_type == "PL",
                    FinancialLine.line_code == nsbu_line,
                )
            )
        )
        rows = await db.execute(q)
        out: Dict[Any, float] = {}
        for co_id, v in rows.all():
            if v is None:
                continue
            try:
                out[co_id] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    nsbu_curr = await _load_nsbu(year)
    nsbu_prev = await _load_nsbu(prev_year)

    # ─── 4. Per-company merge ───
    sec_set = set(sector_filter) if sector_filter else None

    @dataclass
    class _Co:
        co_id: Any
        name: str
        sector: str
        plan: Optional[float] = None
        fact: Optional[float] = None
        prev_fact: Optional[float] = None
        # Computed later
        pct: Optional[float] = None
        display_pct: Optional[int] = None
        display_label: Optional[str] = None
        display_label_full: Optional[str] = None
        delta: Optional[float] = None
        cls: Optional[str] = None
        note: Optional[str] = None

    companies: List[_Co] = []
    for co_id, name in co_id_to_name.items():
        if sec_set and co_id_to_sector.get(co_id, "other") not in sec_set:
            continue

        plan = bp_plan_map.get(co_id)
        # fact priority: NSBU (фактический stmt), then BP fact (manual entry)
        fact = nsbu_curr.get(co_id)
        if fact is None:
            fact = bp_fact_map.get(co_id)
        prev_fact = nsbu_prev.get(co_id)
        if prev_fact is None:
            prev_fact = bp_prev_fact_map.get(co_id)

        if fact is None and plan is None and prev_fact is None:
            continue

        companies.append(_Co(
            co_id=co_id, name=name,
            sector=co_id_to_sector.get(co_id, "other"),
            plan=plan, fact=fact, prev_fact=prev_fact,
        ))

    # ─── 5. Determine mode ───
    with_plan = sum(1 for c in companies if c.plan is not None and c.plan > 0)
    with_fact_pair = sum(
        1 for c in companies
        if c.fact is not None and c.prev_fact is not None and c.prev_fact != 0
    )

    if with_plan >= max(3, int(len(companies) * 0.3)):
        mode = "plan-fact"
    elif with_fact_pair >= 3:
        mode = "yoy"
    else:
        mode = "empty"

    # ─── 6. Compute pct / cls per company (1:1 from monolith) ───
    for c in companies:
        if mode == "plan-fact" and c.plan is not None and c.plan > 0 and c.fact is not None:
            ref, cur = c.plan, c.fact
        elif mode == "yoy" and c.prev_fact is not None and c.prev_fact != 0 and c.fact is not None:
            ref, cur = c.prev_fact, c.fact
        else:
            continue

        c.delta = cur - ref

        if not is_signed_metric:
            # Revenue: classic ratio
            c.pct = cur / ref
            c.display_pct = round(c.pct * 100)
            if mode == "plan-fact":
                c.cls = "ok" if c.pct >= 0.95 else ("warn" if c.pct >= 0.80 else "bad")
            else:
                c.cls = "ok" if c.pct >= 1.00 else ("warn" if c.pct >= 0.95 else "bad")
        else:
            # Profit / EBITDA — sign-aware
            if ref > 0 and cur > 0:
                c.pct = cur / ref
                if c.pct > 5:
                    c.display_pct = None
                    c.display_label = f"×{c.pct:.1f}"
                elif c.pct < -5:
                    c.display_pct = None
                    c.display_label = "отриц."
                else:
                    c.display_pct = round(c.pct * 100)
                # cls по обычным порогам
                if mode == "plan-fact":
                    c.cls = "ok" if c.pct >= 0.95 else ("warn" if c.pct >= 0.80 else "bad")
                else:
                    c.cls = "ok" if c.pct >= 1.00 else ("warn" if c.pct >= 0.95 else "bad")
            elif ref <= 0 and cur > 0:
                c.display_label = "↑ восст."
                c.display_label_full = "выход из убытка"
                c.note = "recovery"
                c.cls = "ok"
            elif ref > 0 and cur <= 0:
                c.display_label = "↓ убыток"
                c.display_label_full = "переход в убыток"
                c.note = "loss"
                c.cls = "bad"
            else:
                # Оба отрицательны
                if cur > ref:
                    c.display_label = "↓ умень."
                    c.display_label_full = "убыток сокращён"
                    c.cls = "warn"
                elif cur < ref:
                    c.display_label = "↑ рост"
                    c.display_label_full = "убыток вырос"
                    c.cls = "bad"
                else:
                    c.display_label = "= стаб."
                    c.display_label_full = "убыток стабилен"
                    c.cls = "warn"
                c.note = "loss"

    # ─── 7. Aggregates ───
    sum_plan = sum_fact = sum_prev = 0.0
    sum_plan_ll = sum_fact_plan_ll = 0.0
    sum_prev_ll = sum_fact_ll = 0.0
    for c in companies:
        if c.plan is not None:
            sum_plan += c.plan
        if c.fact is not None:
            sum_fact += c.fact
        if c.prev_fact is not None:
            sum_prev += c.prev_fact
        if mode == "plan-fact" and c.plan is not None and c.plan > 0 and c.fact is not None:
            sum_plan_ll += c.plan
            sum_fact_plan_ll += c.fact
        if mode == "yoy" and c.prev_fact is not None and c.prev_fact != 0 and c.fact is not None:
            sum_prev_ll += c.prev_fact
            sum_fact_ll += c.fact

    overall_pct: Optional[float] = None
    overall_delta: Optional[float] = None
    overall_label: Optional[str] = None

    if mode == "plan-fact":
        if not is_signed_metric:
            overall_pct = sum_fact_plan_ll / sum_plan_ll if sum_plan_ll > 0 else None
        else:
            overall_delta = sum_fact_plan_ll - sum_plan_ll
            if sum_plan_ll > 0 and sum_fact_plan_ll > 0:
                overall_pct = sum_fact_plan_ll / sum_plan_ll
                if overall_pct > 5 or overall_pct < 0:
                    overall_pct = None
                    overall_label = "план перевыполнен" if overall_delta >= 0 else "план не выполнен"
            elif sum_plan_ll <= 0 and sum_fact_plan_ll > 0:
                overall_label = "выход из убытка"
            elif sum_plan_ll > 0 and sum_fact_plan_ll <= 0:
                overall_label = "переход в убыток"
            else:
                overall_label = "убыток сокращён" if sum_fact_plan_ll > sum_plan_ll else "убыток вырос"
    elif mode == "yoy":
        if not is_signed_metric:
            overall_pct = sum_fact_ll / sum_prev_ll if sum_prev_ll > 0 else None
        else:
            overall_delta = sum_fact_ll - sum_prev_ll
            if sum_prev_ll > 0 and sum_fact_ll > 0:
                overall_pct = sum_fact_ll / sum_prev_ll
                if overall_pct > 5 or overall_pct < 0:
                    overall_pct = None
                    overall_label = "значительный рост" if overall_delta >= 0 else "значительное снижение"
            elif sum_prev_ll <= 0 and sum_fact_ll > 0:
                overall_label = "выход из убытка"
            elif sum_prev_ll > 0 and sum_fact_ll <= 0:
                overall_label = "переход в убыток"
            else:
                overall_label = "убыток сокращён" if sum_fact_ll > sum_prev_ll else "убыток вырос"

    # prev_overall_pct — для unsigned yoy режима, дельта vs prev2 year
    prev_overall_pct: Optional[float] = None
    if mode == "yoy" and not is_signed_metric:
        prev2 = await _load_nsbu(prev_year - 1)
        sum_pp = sum_pf = 0.0
        for c in companies:
            v_pp = prev2.get(c.co_id)
            v_p = c.prev_fact
            if v_pp is not None and v_p is not None and v_pp > 0:
                sum_pp += v_pp
                sum_pf += v_p
        if sum_pp > 0:
            prev_overall_pct = sum_pf / sum_pp

    # ─── 8. Build rows for Performance Spine (only classified companies) ───
    with_cls = [c for c in companies if c.cls is not None]

    # Counters for footer
    on_target = sum(1 for c in with_cls if c.cls == "ok")
    attention = sum(1 for c in with_cls if c.cls == "warn")
    behind = sum(1 for c in with_cls if c.cls == "bad")

    # Sort leaders → laggards (by pct desc; signed без pct идут в конец после warn/bad)
    def _sort_key(c: _Co) -> float:
        if c.pct is not None:
            return -c.pct
        # Signed без pct: recovery (ok) → high; loss (bad) → low
        if c.note == "recovery":
            return -1.2
        if c.cls == "bad":
            return 0.65
        return 0.92  # warn

    with_cls.sort(key=_sort_key)

    rows = [
        ExecBPCompanyRow(
            company_id=c.co_id,
            name=c.name,
            sector=c.sector,
            plan_value=(c.plan if mode == "plan-fact" else c.prev_fact) or 0.0,
            fact_value=c.fact or 0.0,
            pct=c.pct,
            display_pct=c.display_pct,
            display_label=c.display_label,
            display_label_full=c.display_label_full,
            delta=c.delta,
            cls=c.cls,
            note=c.note,
        )
        for c in with_cls
    ]

    # ─── 9. Headline subtitle text ───
    ll_count = len(with_cls)
    total = len(companies)
    if mode == "plan-fact":
        head_sub = f"FY {year} · план-факт {metric_label.lower()} · сравнение по {ll_count} из {total} компаний"
    elif mode == "yoy":
        head_sub = f"FY {year} vs FY {prev_year} · динамика {metric_label.lower()} · сравнение по {ll_count} из {total} компаний"
    else:
        head_sub = f"Недостаточно данных по {metric_label.lower()} в портфеле"

    standard_used = "BP" if mode == "plan-fact" else "NSBU"

    return ExecBPBlock(
        year=year,
        prev_year=prev_year,
        metric=metric_low,
        metric_label=metric_label,
        standard=standard_used,
        mode=mode,
        head_sub=head_sub,
        is_signed_metric=is_signed_metric,
        plan_total=sum_plan,
        fact_total=sum_fact,
        sum_plan_ll=sum_plan_ll,
        sum_fact_plan_ll=sum_fact_plan_ll,
        sum_prev_ll=sum_prev_ll,
        sum_fact_ll=sum_fact_ll,
        overall_pct=overall_pct,
        prev_overall_pct=prev_overall_pct,
        overall_delta=overall_delta,
        overall_label=overall_label,
        rows=rows,
        on_target=on_target,
        attention=attention,
        behind=behind,
        total_count=total,
        with_pct_count=ll_count,
    )

# ═══════════════════ Block 3: Налоговый вклад ═══════════════════

async def build_tax_contribution_block(
    db: AsyncSession,
    year: int,
    co_id_to_name: Dict[Any, str],
    co_id_to_sector: Dict[Any, str],
    sector_filter: Optional[List[str]] = None,
) -> ExecTaxBlock:
    """
    Tax contribution block:
      - Налог на прибыль (income tax): line_code='tax' в IFRS PL (sum)
      - НДС (VAT): revenue × 12%
      - Total = income_tax + VAT
      - YoY: год N vs год N-1
      - Top-5 плательщиков
      - Доля бюджета РУ
    """
    from app.models.financial import FinancialReport, FinancialLine

    prev_year = year - 1

    async def _sum_by_co(target_year: int, std: str, line_code: str) -> Dict[Any, float]:
        """Sum of values per company_id, в условных «МЛН сум» (monolith convention).

        Pack 7.9h FINDINGS: в БД value для revenue ~135809 у крупнейшей SOE — это
        135.8 млрд сум. То есть `value` хранится в **миллионах сум**. Поле
        `unit_scale` существует но используется непоследовательно (112 reports
        со scale=1000, 6 со scale=1e9) — игнорируем его для consistency со старой
        логикой; принимаем convention: 1 единица value = 1 млн сум.
        """
        q = (
            select(FinancialReport.company_id, func.sum(FinancialLine.value))
            .join(FinancialLine, FinancialLine.report_id == FinancialReport.id)
            .where(
                and_(
                    FinancialReport.year == target_year,
                    FinancialReport.standard == std,
                    FinancialReport.report_type == "PL",
                    FinancialLine.line_code == line_code,
                )
            )
            .group_by(FinancialReport.company_id)
        )
        rows = await db.execute(q)
        out: Dict[Any, float] = {}
        for co_id, val in rows.all():
            if val is None:
                continue
            try:
                # Tax usually negative; we take absolute value
                out[co_id] = abs(float(val))
            except (TypeError, ValueError):
                continue
        return out

    # Pack 7.28 (restore Pack 7.14.1): NSBU first, fallback to IFRS.
    # Tax filings in UZ are based on NSBU; IFRS is the optional disclosure.
    # Showing IFRS tax numbers misleads — they often differ from what's
    # actually paid to the budget.
    standard_used = "NSBU"
    tax_cur = await _sum_by_co(year, "NSBU", _IFRS_PL_TAX)
    tax_prev = await _sum_by_co(prev_year, "NSBU", _IFRS_PL_TAX)
    rev_cur = await _sum_by_co(year, "NSBU", _IFRS_PL_REVENUE)
    rev_prev = await _sum_by_co(prev_year, "NSBU", _IFRS_PL_REVENUE)

    if not tax_cur and not rev_cur:
        # NSBU empty for this year → fall back to IFRS (rare, but possible
        # for early years before NSBU import). Display will note the source.
        standard_used = "IFRS"
        tax_cur = await _sum_by_co(year, "IFRS", _IFRS_PL_TAX)
        tax_prev = await _sum_by_co(prev_year, "IFRS", _IFRS_PL_TAX)
        rev_cur = await _sum_by_co(year, "IFRS", _IFRS_PL_REVENUE)
        rev_prev = await _sum_by_co(prev_year, "IFRS", _IFRS_PL_REVENUE)

    sec_set = set(sector_filter) if sector_filter else None

    # Aggregate sums
    sum_tax = 0.0
    sum_vat = 0.0
    sum_tax_prev = 0.0
    sum_vat_prev = 0.0

    per_company: Dict[Any, float] = {}
    cos_seen: set = set()

    for co_id in co_id_to_name.keys():
        if sec_set and co_id_to_sector.get(co_id, "other") not in sec_set:
            continue
        t = tax_cur.get(co_id, 0.0)
        r = rev_cur.get(co_id, 0.0)
        if t == 0.0 and r == 0.0:
            continue
        v = r * _VAT_RATE
        sum_tax += t
        sum_vat += v
        per_company[co_id] = t + v
        cos_seen.add(co_id)

        sum_tax_prev += tax_prev.get(co_id, 0.0)
        sum_vat_prev += rev_prev.get(co_id, 0.0) * _VAT_RATE

    has_data = sum_tax > 0 or sum_vat > 0
    total = sum_tax + sum_vat
    total_prev = sum_tax_prev + sum_vat_prev

    yoy_total = ((total / total_prev) - 1.0) * 100 if total_prev > 0 else None
    yoy_tax = ((sum_tax / sum_tax_prev) - 1.0) * 100 if sum_tax_prev > 0 else None
    yoy_vat = ((sum_vat / sum_vat_prev) - 1.0) * 100 if sum_vat_prev > 0 else None

    # Pack 7.9l: revert to monolith-original convention per user feedback.
    # В монолите `total` интерпретируется в специфичной convention где
    # `total_trln = total / 1e3` даёт 28% от бюджета 350 (трлн)
    # — то есть SOE-портфель ≈ 28% бюджета РУз, что соответствует реальности.
    # Math purity (98.7 млрд / 350 трлн = 0.028%) даёт цифру которая не
    # отражает фактический вклад крупнейших госкомпаний в госбюджет.
    # Monolith convention сохраняется для consistency с legacy интерпретацией.
    total_trln = total / 1e3   # monolith convention — gives 28.2% for SOE portfolio

    # Pack 7.35: бюджет читаем из year_registry (admin-editable). Если в БД
    # колонка пустая (например миграция ещё не накатилась) — используем
    # hardcoded fallback из _UZ_BUDGET_TRLN.
    budget_trln = None
    try:
        from app.models.year_registry import YearRegistry  # local import to avoid circular
        q = await db.execute(
            select(YearRegistry.uz_budget_trln).where(YearRegistry.year == year)
        )
        db_val = q.scalar_one_or_none()
        if db_val is not None:
            budget_trln = float(db_val)
    except Exception:
        # Если что-то сломалось при чтении из БД — не валим весь дашборд,
        # просто откатываемся на hardcoded fallback.
        budget_trln = None

    if budget_trln is None:
        budget_trln = _UZ_BUDGET_TRLN.get(year)

    budget_share_pct = (total_trln / budget_trln * 100) if budget_trln else None

    # Pack 7.9h: per_company в МЛН сум — конвертируем в МЛРД для отображения (/1e3)
    top_5_pairs = sorted(per_company.items(), key=lambda x: -x[1])[:5]
    top_payers: List[ExecTaxTopPayer] = []
    for co_id, amt in top_5_pairs:
        share = round(amt / total * 100) if total > 0 else 0
        top_payers.append(ExecTaxTopPayer(
            company_id=co_id,
            name=co_id_to_name.get(co_id, "—"),
            sector=co_id_to_sector.get(co_id, "other"),
            amount=amt / 1e3,     # млн → млрд
            share_pct=share,
        ))

    # Pack 7.9h: список компаний без NSBU PL данных за год
    # (полезно понять почему cos_count < 22)
    missing_companies: List[str] = []
    if sec_set is None:  # only when no sector filter — full picture
        for co_id, name in co_id_to_name.items():
            if co_id not in cos_seen:
                missing_companies.append(name)

    return ExecTaxBlock(
        year=year,
        prev_year=prev_year,
        has_data=has_data,
        standard=standard_used,
        cos_count=len(cos_seen),
        missing_companies=missing_companies,
        kpi=ExecTaxKpi(
            income_tax=sum_tax / 1e3,         # млн → млрд
            vat=sum_vat / 1e3,
            total=total / 1e3,
            yoy_total_pct=yoy_total,
            yoy_income_tax_pct=yoy_tax,
            yoy_vat_pct=yoy_vat,
            budget_share_pct=budget_share_pct,
            budget=budget_trln * 1e3 if budget_trln else None,  # trln → mlrd
            vat_is_estimate=True,             # always True — нет vat line_code в NSBU
        ),
        top_payers=top_payers,
    )
