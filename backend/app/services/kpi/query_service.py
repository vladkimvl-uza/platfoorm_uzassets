"""KPI query-side service — read-only сценарии.

Каждый use-case:
1. Открывает UoW (read-only — `__aexit__` без exception сделает commit, который
   для read-only это no-op).
2. Запрашивает данные через `uow.kpi.*`.
3. Выполняет бизнес-вычисления (агрегации, веса, статусы) — pure functions
   из `services/bp_kpi_helpers.py`.
4. Возвращает Pydantic-schemas (DTO).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.models.bp_kpi import BP_METRIC_DIRECTION, KpiManager
from app.models.company import Company
from app.schemas.bp_kpi import (
    BpAvailableCompany,
    KpiAttentionIssue,
    KpiCommentRead,
    KpiCompanyRow,
    KpiIndPayload,
    KpiManagerRead,
    KpiQuarterAgg,
    KpiSectorRow,
    KpiSummary,
)
from app.services.bp_kpi_helpers import (
    bp_compute,
    kpi_attention_issues,
    kpi_compute_completion,
    kpi_status_for_pct,
    sector_code,
    sector_color,
)
from app.uow.ports import UnitOfWorkABC


class KpiQueryService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── Available companies + years ──────────────────────────────

    async def list_available_companies(
        self, scope_company_ids: Optional[list] = None,
    ) -> list[BpAvailableCompany]:
        async with self.uow:
            rows = await self.uow.kpi.distinct_company_years()
            if not rows:
                return []

            # RBAC scope: ограниченный пользователь видит в пикере ВСЕ свои
            # компании (даже без KPI-данных — чтобы можно было их завести), а не
            # только те, по которым уже есть данные. None = owner/view_all.
            allowed = set(scope_company_ids) if scope_company_ids is not None else None
            co_years: dict[UUID, set[int]] = {}
            for cid, yr in rows:
                if allowed is not None and cid not in allowed:
                    continue
                co_years.setdefault(cid, set()).add(yr)
            # owner/admin (allowed is None): показываем ВСЕ компании реестра, не
            # только с KPI-данными — иначе пустой компании нельзя завести данные.
            if allowed is None:
                companies = await self.uow.kpi.list_all_companies_with_sector()
            else:
                company_ids = list(allowed)
                if not company_ids:
                    return []
                companies = await self.uow.kpi.list_companies_with_sector(company_ids)
            if not companies:
                return []

            out: list[BpAvailableCompany] = [
                BpAvailableCompany(
                    company_id=co.id,
                    company_name_ru=co.name_ru or co.code or "—",
                    company_code=co.code,
                    sector_code=sector_code(co),
                    sector_color=sector_color(co),
                    years=sorted(co_years.get(co.id, set()), reverse=True),
                )
                for co in companies
            ]
            out.sort(key=lambda c: c.company_name_ru)
            return out

    # ─── Full managers tree (per company-year) ────────────────────

    async def get_company_year(self, company_id: UUID, year: int) -> list[KpiManagerRead]:
        async with self.uow:
            managers = await self.uow.kpi.get_managers_with_indicators(company_id, year)
            out = [KpiManagerRead.model_validate(m) for m in managers]

            # Read-through из Бизнес-плана/НСБУ для связанных (bp_metric_key) строк:
            # план/факт зеркалятся из BP (annual), чтобы редактор показал выверенное
            # значение единого источника истины, а не пустые plan_year/fact_year.
            # direction форсится из канона. Один bp_compute на компанию-год (без N+1).
            if any(ir.bp_metric_key for mr in out for ir in mr.indicators):
                session = self.uow._session  # type: ignore[attr-defined]
                comp = await bp_compute(session, company_id, year, "annual")
                for mr in out:
                    for ir in mr.indicators:
                        k = ir.bp_metric_key
                        if not k:
                            continue
                        cell = comp.get(k)
                        if cell is None:
                            continue
                        ir.bp_resolved = True
                        ir.bp_plan_resolved = cell.get("plan")
                        ir.bp_fact_resolved = cell.get("fact")
                        src = cell.get("fact_source")
                        ir.bp_source = src or ("bp_plan" if cell.get("plan") is not None else None)
                        ir.direction = BP_METRIC_DIRECTION.get(k, ir.direction)
            return out

    # ─── Portfolio summary (the heavy one) ────────────────────────

    async def compute_summary(
        self,
        year: int,
        period: str,
        *,
        scope_company_ids: Optional[set[UUID]] = None,
    ) -> KpiSummary:
        """Portfolio KPI summary. period='year' | 'q1'..'q4'.

        Mirror of legacy `_kpiComputeSummary`. После P1-фикса 2026-05-23
        `overall` и `by_sector` считаются как mean(by_company.pct), а не
        weighted-by-indicator (защита от inflated весов одной компании).
        """
        # Empty scope → empty result без запроса
        if scope_company_ids is not None and not scope_company_ids:
            return _empty_summary(year, period)

        async with self.uow:
            managers = await self.uow.kpi.get_summary_managers(
                year, scope_company_ids=scope_company_ids,
            )

        if not managers:
            return _empty_summary(year, period)

        return _aggregate(managers, year, period)

    # ─── Attention + comments ─────────────────────────────────────

    async def get_attention(
        self, company_id: UUID, year: int, period: str,
    ) -> list[KpiAttentionIssue]:
        async with self.uow:
            # NB: kpi_attention_issues — legacy helper, принимает session напрямую.
            # При следующем рефакторе перевести его на repository.
            session = self.uow._session  # type: ignore[attr-defined]
            issues = await kpi_attention_issues(session, company_id, year, period)
            return [KpiAttentionIssue(**x) for x in issues]

    async def get_comment(
        self, company_id: UUID, year: int, period: str,
    ) -> Optional[KpiCommentRead]:
        async with self.uow:
            row = await self.uow.kpi.get_comment(company_id, year, period)
            return KpiCommentRead.model_validate(row) if row else None


# ═══ pure-function helpers ═══════════════════════════════════════════
# Вынесены в module-level чтобы их можно было unit-тестировать с
# fixture-managers без необходимости поднимать UnitOfWork.

def _empty_summary(year: int, period: str) -> KpiSummary:
    return KpiSummary(
        year=year, period=period, co_count=0, total_count=0,
        distribution={"over": [], "hit": [], "risk": [], "crit": [], "fail": []},
        by_company=[], by_sector=[], by_quarter=[],
        achievements=[], issues=[],
    )


def _aggregate(managers: list[KpiManager], year: int, period: str) -> KpiSummary:
    """Pure aggregation — не делает I/O. Берёт preloaded managers/inds/companies
    и считает портфельную сводку по правилам легасиа `_kpiComputeSummary`."""
    # Group by company
    by_co: dict[UUID, dict] = {}
    for m in managers:
        if m.company_id not in by_co:
            by_co[m.company_id] = {"company": m.company, "managers": []}
        by_co[m.company_id]["managers"].append(m)

    total_count = 0
    over_count = hit_count = risk_count = crit_count = fail_count = 0
    sum_weighted = 0.0
    sum_weights = 0.0
    distribution: dict[str, list[KpiIndPayload]] = {
        "over": [], "hit": [], "risk": [], "crit": [], "fail": [],
    }
    by_company: list[KpiCompanyRow] = []
    sector_agg: dict[str, dict] = {}
    all_inds: list[KpiIndPayload] = []

    for cid, e in by_co.items():
        co: Company = e["company"]
        co_name = co.name_ru or co.code or "—"
        sec_code = sector_code(co)
        sec_color = sector_color(co)
        co_sum_w = co_sum_weighted = 0.0
        co_count = co_hit = co_risk = co_crit = 0

        for mi, mgr in enumerate(e["managers"]):
            for ii, ind in enumerate(mgr.indicators):
                ratio = kpi_compute_completion(ind, period)
                if ratio is None:
                    continue
                if period == "year":
                    w = float(ind.weight or 0)
                else:
                    w = float(getattr(ind, f"{period}_weight", 0) or 0)
                    # Фолбэк: поквартальный вес часто не заполняют (вес заводят
                    # только годовой, а план/факт — поквартально). Без фолбэка
                    # квартал с план+факт «пропадал» из сводки → «нет данных»,
                    # хотя данные есть (ср. YTD-fallback для года в kpi_compute_completion).
                    if w == 0:
                        w = float(ind.weight or 0)
                if w == 0:
                    continue
                total_count += 1
                co_count += 1
                cap_ratio = min(ratio, 1.5)
                sum_weighted += cap_ratio * w
                sum_weights += w
                co_sum_weighted += cap_ratio * w
                co_sum_w += w
                pct = ratio * 100
                status = kpi_status_for_pct(pct)
                if status == "over":
                    over_count += 1
                    co_hit += 1
                elif status == "hit":
                    hit_count += 1
                    co_hit += 1
                elif status == "risk":
                    risk_count += 1
                    co_risk += 1
                elif status == "crit":
                    crit_count += 1
                    co_crit += 1
                else:  # fail
                    fail_count += 1
                    co_crit += 1  # P0 fix 2026-05-25: убран двойной счёт

                if period == "year":
                    plan = ind.plan_year
                    fact = ind.fact_year
                else:
                    plan = getattr(ind, f"{period}_plan", None)
                    fact = getattr(ind, f"{period}_fact", None)

                payload = KpiIndPayload(
                    co_id=cid, co_name=co_name,
                    mgr_idx=mi, mgr=mgr.short_title or mgr.title or "",
                    ind_idx=ii, ind_id=ind.id, name=ind.name or "",
                    unit=ind.unit, weight=Decimal(w),
                    plan=plan, fact=fact, ratio=ratio, pct=pct, status=status,
                )
                distribution[status].append(payload)
                all_inds.append(payload)

        if co_sum_w > 0:
            co_pct = co_sum_weighted / co_sum_w * 100
            by_company.append(KpiCompanyRow(
                company_id=cid, co_name=co_name,
                sector_code=sec_code, sector_color=sec_color,
                count=co_count, hit=co_hit, risk=co_risk, crit=co_crit, pct=co_pct,
            ))
            if sec_code:
                if sec_code not in sector_agg:
                    sector_agg[sec_code] = {
                        "label": (co.sector.name_ru if co.sector and co.sector.name_ru else sec_code),
                        # P1 fix: считаем среднее по компаниям, не взвешенно.
                        "co_pcts": [], "count": 0, "co_count": 0,
                    }
                sector_agg[sec_code]["co_pcts"].append(co_pct)
                sector_agg[sec_code]["count"] += co_count
                sector_agg[sec_code]["co_count"] += 1

    by_company.sort(key=lambda r: -r.pct)

    by_sector = [
        KpiSectorRow(
            sector_code=k, label=v["label"],
            pct=(sum(v["co_pcts"]) / len(v["co_pcts"])) if v["co_pcts"] else None,
            count=v["count"], co_count=v["co_count"],
        )
        for k, v in sector_agg.items()
    ]
    by_sector.sort(key=lambda r: -(r.pct or -1e9))

    # By-quarter: mean of per-company quarterly pcts
    by_quarter: list[KpiQuarterAgg] = []
    for q in ("q1", "q2", "q3", "q4"):
        co_pcts_q: list[float] = []
        has_plan = False
        for cid, e in by_co.items():
            co_sum_w_q = co_sum_wtd_q = 0.0
            for mgr in e["managers"]:
                for ind in mgr.indicators:
                    qw = float(getattr(ind, f"{q}_weight", 0) or 0)
                    if qw == 0:
                        qw = float(ind.weight or 0)  # фолбэк на годовой вес (см. total_count)
                    if qw == 0:
                        continue
                    qp = getattr(ind, f"{q}_plan", None)
                    if qp is not None:
                        has_plan = True
                    # direction-aware (для 'down' = план/факт); cap 150%
                    qr = kpi_compute_completion(ind, q)
                    if qr is not None:
                        co_sum_wtd_q += min(qr, 1.5) * qw
                        co_sum_w_q += qw
            if co_sum_w_q > 0:
                co_pcts_q.append(co_sum_wtd_q / co_sum_w_q * 100)
        by_quarter.append(KpiQuarterAgg(
            q=q,
            plan=100 if has_plan else None,
            fact=(sum(co_pcts_q) / len(co_pcts_q)) if co_pcts_q else None,
        ))

    achievements = sorted(
        [x for x in all_inds if x.pct is not None and x.pct >= 105],
        key=lambda x: -(x.pct or 0),
    )[:5]
    issues = sorted(
        [x for x in all_inds if x.pct is not None and x.pct < 90 and float(x.weight) >= 5],
        key=lambda x: (x.pct or 0),
    )[:5]

    overall = (
        sum(r.pct for r in by_company) / len(by_company)
        if by_company else None
    )

    return KpiSummary(
        year=year, period=period,
        co_count=len(by_co), total_count=total_count,
        overall=overall,
        over_count=over_count, hit_count=hit_count,
        risk_count=risk_count, crit_count=crit_count, fail_count=fail_count,
        distribution=distribution,
        by_company=by_company,
        by_sector=by_sector,
        by_quarter=by_quarter,
        achievements=achievements,
        issues=issues,
    )
