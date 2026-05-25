"""Use cases for Business Plan.

Delegates to the existing core `app/services/bp_kpi_helpers.py`
(bp_compute, bp_attention_issues, sector_code, sector_color,
kpi_attention_issues) — those are tightly-coupled formulas used by
multiple modules; do not duplicate.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Sequence
from uuid import UUID

from fastapi import HTTPException, status as http_status

from app.models.bp_kpi import BP_METRIC_KEYS, BP_PERIODS, BpRecord
from app.schemas.bp_kpi import (
    BpAttentionIssue, BpAvailableCompany, BpBulkUpsert, BpCell,
    BpCommentRead, BpCommentUpsert, BpCompanyRow, BpComputed,
    BpMetricTotal, BpQuarterRow, BpRecordUpsert, BpSectorRow, BpSummary,
)
from app.services.bp_kpi_helpers import (
    bp_attention_issues, bp_compute,
    sector_code as sector_code_fn,
    sector_color as sector_color_fn,
)
from app.uow.ports import UnitOfWorkABC


VALID_HEADLINE_METRICS = {
    "revenue", "cogs", "grossProfit", "opExpenses", "otherOpInc",
    "opProfit", "finIncome", "finCost", "pbt", "tax", "profit",
}


class BpService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── available-companies ──────────────────────────────────────

    async def available_companies(self) -> List[BpAvailableCompany]:
        async with self.uow:
            rows = await self.uow.bp.list_company_year_pairs()
            if not rows:
                return []
            co_years: Dict[UUID, set[int]] = {}
            for cid, yr in rows:
                co_years.setdefault(cid, set()).add(yr)
            cos = await self.uow.bp.list_companies_with_sector(list(co_years.keys()))

        out: List[BpAvailableCompany] = []
        for co in cos:
            years = sorted(co_years.get(co.id, set()), reverse=True)
            out.append(BpAvailableCompany(
                company_id=co.id,
                company_name_ru=co.name_ru or co.code or "—",
                company_code=co.code,
                sector_code=sector_code_fn(co),
                sector_color=sector_color_fn(co),
                years=years,
            ))
        out.sort(key=lambda c: c.company_name_ru)
        return out

    # ─── raw records ──────────────────────────────────────────────

    async def get_raw_records(
        self,
        company_id: UUID,
        year: int,
    ) -> dict:
        async with self.uow:
            rows = await self.uow.bp.list_records_for_year(company_id, year)
        out: Dict[str, Dict[str, Dict]] = {p: {} for p in BP_PERIODS}
        for r in rows:
            out[r.period][r.metric] = {
                "plan": r.plan, "expect": r.expect, "fact": r.fact,
            }
        return out

    # ─── computed (single co × year × period) ─────────────────────

    async def get_computed(
        self,
        company_id: UUID,
        year: int,
        period: str,
    ) -> BpComputed:
        if period not in BP_PERIODS:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, f"Invalid period: {period}",
            )
        async with self.uow:
            # bp_compute is an existing helper that takes the AsyncSession
            comp = await bp_compute(self.uow._session, company_id, year, period)  # type: ignore[attr-defined]
        return BpComputed(
            company_id=company_id, year=year, period=period,
            metrics={k: BpCell(**comp[k]) for k in BP_METRIC_KEYS},
        )

    # ─── portfolio summary ────────────────────────────────────────

    async def get_summary(
        self,
        year: int,
        period: str,
        *,
        headline_metric: str = "revenue",
        scope_company_ids: Optional[Sequence[UUID]] = None,
    ) -> BpSummary:
        if period not in BP_PERIODS:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                                f"Invalid period: {period}")
        if headline_metric not in VALID_HEADLINE_METRICS:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                                f"Invalid metric: {headline_metric}")

        if scope_company_ids is not None and not scope_company_ids:
            return BpSummary(
                year=year, period=period, co_count=0,
                totals=[], prev_totals=[],
                by_company=[], by_sector=[], by_quarter=[],
            )

        async with self.uow:
            co_ids = await self.uow.bp.distinct_companies_with_bp(
                scope_company_ids=scope_company_ids,
            )
            if not co_ids:
                return BpSummary(
                    year=year, period=period, co_count=0,
                    totals=[], prev_totals=[],
                    by_company=[], by_sector=[], by_quarter=[],
                )
            cos_full = await self.uow.bp.list_companies_with_sector(co_ids)

            metrics_for_summary = [
                "revenue", "cogs", "grossProfit", "opExpenses", "otherOpInc",
                "opProfit", "finIncome", "finCost", "pbt", "tax", "profit",
            ]
            totals = {
                m: {"plan": Decimal(0), "fact": Decimal(0), "expect": Decimal(0),
                    "has_plan": False, "has_fact": False, "has_expect": False}
                for m in metrics_for_summary
            }
            prev_totals = {
                m: {"plan": Decimal(0), "fact": Decimal(0), "expect": Decimal(0),
                    "has_plan": False, "has_fact": False, "has_expect": False}
                for m in metrics_for_summary
            }
            by_company: List[BpCompanyRow] = []
            sector_sums: Dict[str, Dict] = {}

            session = self.uow._session  # type: ignore[attr-defined]

            for co in cos_full:
                comp = await bp_compute(session, co.id, year, period)
                prev = await bp_compute(session, co.id, year - 1, "annual")
                for m in metrics_for_summary:
                    for c in ("plan", "fact", "expect"):
                        v = comp[m][c]
                        if v is not None:
                            totals[m][c] += Decimal(v)
                            totals[m][f"has_{c}"] = True
                    if prev[m]["fact"] is not None:
                        prev_totals[m]["fact"] += Decimal(prev[m]["fact"])
                        prev_totals[m]["has_fact"] = True

                m_plan = comp[headline_metric]["plan"]
                m_fact = comp[headline_metric]["fact"]
                pct = None
                if m_plan is not None and m_plan != 0:
                    pct = float(m_fact or 0) / float(m_plan) * 100
                if pct is not None:
                    sec_code = sector_code_fn(co)
                    sec_color = sector_color_fn(co)
                    by_company.append(BpCompanyRow(
                        company_id=co.id,
                        company_name_ru=co.name_ru or co.code or "—",
                        sector_code=sec_code, sector_color=sec_color,
                        rev_fact=m_fact, rev_plan=m_plan, pct=pct,
                    ))
                    if sec_code:
                        if sec_code not in sector_sums:
                            sector_sums[sec_code] = {
                                "label": (
                                    co.sector.name_ru
                                    if co.sector and co.sector.name_ru
                                    else sec_code
                                ),
                                "sum": Decimal(0),
                            }
                        if m_fact is not None:
                            sector_sums[sec_code]["sum"] += Decimal(m_fact)

            by_company.sort(key=lambda r: -(r.pct or -1e9))
            by_sector = [
                BpSectorRow(sector_code=k, label=v["label"], sum_revenue=v["sum"])
                for k, v in sector_sums.items()
            ]
            by_sector.sort(key=lambda r: -float(r.sum_revenue))

            by_quarter: List[BpQuarterRow] = []
            for q in ("q1", "q2", "q3", "q4"):
                sum_plan, sum_fact = Decimal(0), Decimal(0)
                has_plan = has_fact = False
                for co in cos_full:
                    qcomp = await bp_compute(session, co.id, year, q)
                    if qcomp[headline_metric]["plan"] is not None:
                        sum_plan += Decimal(qcomp[headline_metric]["plan"])
                        has_plan = True
                    if qcomp[headline_metric]["fact"] is not None:
                        sum_fact += Decimal(qcomp[headline_metric]["fact"])
                        has_fact = True
                by_quarter.append(BpQuarterRow(
                    q=q,
                    plan=sum_plan if has_plan else None,
                    fact=sum_fact if has_fact else None,
                ))

            return BpSummary(
                year=year, period=period, co_count=len(cos_full),
                totals=[BpMetricTotal(metric=m, **totals[m]) for m in metrics_for_summary],
                prev_totals=[BpMetricTotal(metric=m, **prev_totals[m]) for m in metrics_for_summary],
                by_company=by_company,
                by_sector=by_sector,
                by_quarter=by_quarter,
            )

    # ─── attention issues ─────────────────────────────────────────

    async def attention(
        self,
        company_id: UUID,
        year: int,
        period: str,
    ) -> list[BpAttentionIssue]:
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            issues = await bp_attention_issues(session, company_id, year, period)
            from app.services.bp_kpi_helpers import kpi_attention_issues as _kpi_iss
            kpi_iss = await _kpi_iss(session, company_id, year, period)
        return [BpAttentionIssue(**x) for x in issues + kpi_iss][:5]

    # ─── upserts ──────────────────────────────────────────────────

    async def upsert_one(self, payload: BpRecordUpsert) -> None:
        if payload.period not in BP_PERIODS:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                                f"Invalid period: {payload.period}")
        if payload.metric not in BP_METRIC_KEYS:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                                f"Invalid metric: {payload.metric}")
        async with self.uow:
            await self.uow.bp.upsert_record(
                company_id=payload.company_id, year=payload.year,
                period=payload.period, metric=payload.metric,
                plan=payload.plan, expect=payload.expect, fact=payload.fact,
            )

    async def bulk_upsert(
        self,
        payload: BpBulkUpsert,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> int:
        allowed_set: Optional[set[UUID]] = (
            None if scope_company_ids is None else set(scope_company_ids)
        )
        async with self.uow:
            n = 0
            for rec in payload.records:
                if rec.period not in BP_PERIODS or rec.metric not in BP_METRIC_KEYS:
                    continue
                if allowed_set is not None and rec.company_id not in allowed_set:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        f"Access to company {rec.company_id} is not allowed",
                    )
                await self.uow.bp.upsert_record(
                    company_id=rec.company_id, year=rec.year,
                    period=rec.period, metric=rec.metric,
                    plan=rec.plan, expect=rec.expect, fact=rec.fact,
                )
                n += 1
        return n

    async def delete_year(self, company_id: UUID, year: int) -> None:
        async with self.uow:
            await self.uow.bp.delete_year(company_id, year)

    # ─── comments ─────────────────────────────────────────────────

    async def get_comment(
        self, company_id: UUID, year: int, period: str,
    ) -> Optional[BpCommentRead]:
        async with self.uow:
            row = await self.uow.bp.get_comment(company_id, year, period)
        return BpCommentRead.model_validate(row) if row else None

    async def upsert_comment(
        self,
        payload: BpCommentUpsert,
        *,
        author_id: UUID,
    ) -> BpCommentRead:
        async with self.uow:
            row = await self.uow.bp.upsert_comment(
                company_id=payload.company_id, year=payload.year,
                period=payload.period, body=payload.body,
                author_id=author_id,
            )
            return BpCommentRead.model_validate(row)
