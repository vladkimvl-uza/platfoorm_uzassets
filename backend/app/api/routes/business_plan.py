"""Business Plan REST API.

Endpoints:
  GET  /bp/available-companies              — companies with BP data + years available
  GET  /bp/{company_id}/{year}/{period}     — computed BP for one scope
  GET  /bp/raw/{company_id}/{year}          — raw stored records (all periods)
  POST /bp/upsert                           — upsert single cell
  POST /bp/bulk-upsert                      — upsert many cells (editor save)
  DELETE /bp/{company_id}/{year}            — delete year
  GET  /bp/summary/{year}/{period}          — portfolio-wide summary
  GET  /bp/attention/{company_id}/{year}/{period} — attention issues
  GET  /bp/comment/{company_id}/{year}/{period}   — get comment
  PUT  /bp/comment                                — upsert comment
  GET  /bp/metrics                                — list of all 22 BP metrics
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.security import has_effective_permission
from app.core.access import allowed_company_ids, ensure_company_access, has_unrestricted_view
from app.models.bp_kpi import (
    BP_METRICS,
    BP_METRIC_KEYS,
    BP_PERIODS,
    BpComment,
    BpRecord,
)
from app.models.company import Company, Sector
from app.models.user import User
from app.schemas.bp_kpi import (
    BpAvailableCompany,
    BpAttentionIssue,
    BpBulkUpsert,
    BpCell,
    BpCommentRead,
    BpCommentUpsert,
    BpCompanyRow,
    BpComputed,
    BpMetricTotal,
    BpQuarterRow,
    BpRecordUpsert,
    BpSectorRow,
    BpSummary,
)
from app.services.bp_kpi_helpers import (
    bp_attention_issues,
    bp_compute,
    sector_code,
    sector_color,
)


log = logging.getLogger(__name__)
router = APIRouter(prefix="/bp", tags=["business-plan"])


# ─── Static metadata ──────────────────────────────────────────────

@router.get("/metrics")
async def list_metrics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the list of 22 BP metrics with labels, groups, formulas."""
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    return BP_METRICS


# ─── Available companies and years ────────────────────────────────

@router.get("/available-companies", response_model=List[BpAvailableCompany])
async def available_companies(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    try:
        # Find companies that have any BP record + the years they have
        rows = (
            await db.execute(
                select(BpRecord.company_id, BpRecord.year)
                .distinct()
            )
        ).all()
        if not rows:
            return []
        co_years: Dict[UUID, set[int]] = {}
        for cid, yr in rows:
            co_years.setdefault(cid, set()).add(yr)

        # Load all referenced companies in one query
        cos = (
            await db.execute(
                select(Company)
                .options(selectinload(Company.sector))
                .where(Company.id.in_(list(co_years.keys())))
            )
        ).scalars().all()

        out: List[BpAvailableCompany] = []
        for co in cos:
            years = sorted(co_years.get(co.id, set()), reverse=True)
            out.append(
                BpAvailableCompany(
                    company_id=co.id,
                    company_name_ru=co.name_ru or co.code or "—",
                    company_code=co.code,
                    sector_code=sector_code(co),
                    sector_color=sector_color(co),
                    years=years,
                )
            )
        out.sort(key=lambda c: c.company_name_ru)
        return out
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[bp /available-companies] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"available-companies failed: {type(e).__name__}: {e}",
        )


# ─── Computed (one company × year × period) ───────────────────────

@router.get("/summary/{year}/{period}", response_model=BpSummary)
async def get_summary(
    year: int,
    period: str,
    metric: str = "revenue",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Portfolio BP summary.

    `metric` (query param) chooses which BP_FIELD drives the by_company /
    by_sector / by_quarter aggregations. Defaults to "revenue" (legacy).
    The headline-metric values appear in the `rev_*` / `sum_revenue` fields
    for backwards-compat — they now reflect whichever metric was requested.
    Useful values: revenue, cogs, opExpenses, finCost, tax.
    """
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    if period not in BP_PERIODS:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Invalid period: {period}")

    valid_metrics = {"revenue", "cogs", "grossProfit", "opExpenses", "otherOpInc",
                     "opProfit", "finIncome", "finCost", "pbt", "tax", "profit"}
    if metric not in valid_metrics:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                            f"Invalid metric: {metric}. Must be one of {sorted(valid_metrics)}")

    scope_set: Optional[set] = None
    if not has_unrestricted_view(user):
        scope = await allowed_company_ids(db, user)
        scope_set = set(scope or [])

    try:
        return await _bp_summary_impl(db, year, period, scope_company_ids=scope_set,
                                      headline_metric=metric)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[bp /summary/{year}/{period}] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"summary failed: {type(e).__name__}: {e}",
        )


async def _bp_summary_impl(
    db: AsyncSession,
    year: int,
    period: str,
    *,
    scope_company_ids: Optional[set] = None,
    headline_metric: str = "revenue",
) -> BpSummary:
    """Portfolio BP summary.

    Если `scope_company_ids` задан (set[UUID]) — агрегат строится только
    по этим компаниям. None — без фильтра (admin/owner).
    """
    if scope_company_ids is not None and not scope_company_ids:
        return BpSummary(
            year=year, period=period, co_count=0,
            totals=[], prev_totals=[], by_company=[], by_sector=[], by_quarter=[],
        )

    # Find companies with any BP records for any year (mirror _bpAvailableCompanies)
    co_ids_q = select(BpRecord.company_id).distinct()
    if scope_company_ids is not None:
        co_ids_q = co_ids_q.where(BpRecord.company_id.in_(scope_company_ids))
    co_ids = [r[0] for r in (await db.execute(co_ids_q)).all()]
    if not co_ids:
        return BpSummary(
            year=year, period=period, co_count=0,
            totals=[], prev_totals=[], by_company=[], by_sector=[], by_quarter=[],
        )

    cos_full = (
        await db.execute(
            select(Company)
            .options(selectinload(Company.sector))
            .where(Company.id.in_(co_ids))
        )
    ).scalars().all()

    # Aggregate metric totals
    metrics_for_summary = ["revenue", "cogs", "grossProfit", "opExpenses", "otherOpInc",
                           "opProfit", "finIncome", "finCost", "pbt", "tax", "profit"]
    totals: Dict[str, Dict] = {
        m: {"plan": Decimal(0), "fact": Decimal(0), "expect": Decimal(0),
            "has_plan": False, "has_fact": False, "has_expect": False}
        for m in metrics_for_summary
    }
    prev_totals: Dict[str, Dict] = {
        m: {"plan": Decimal(0), "fact": Decimal(0), "expect": Decimal(0),
            "has_plan": False, "has_fact": False, "has_expect": False}
        for m in metrics_for_summary
    }

    by_company: List[BpCompanyRow] = []
    sector_sums: Dict[str, Dict] = {}

    for co in cos_full:
        comp = await bp_compute(db, co.id, year, period)
        prev = await bp_compute(db, co.id, year - 1, "annual")

        for m in metrics_for_summary:
            for c in ("plan", "fact", "expect"):
                v = comp[m][c]
                if v is not None:
                    totals[m][c] += Decimal(v)
                    totals[m][f"has_{c}"] = True
            if prev[m]["fact"] is not None:
                prev_totals[m]["fact"] += Decimal(prev[m]["fact"])
                prev_totals[m]["has_fact"] = True

        # Per-company % by HEADLINE metric (revenue by default; cogs/opExpenses/etc
        # for lens tabs). Field names rev_fact/rev_plan/sum_revenue stay for
        # backwards-compat — they now reflect whichever metric was requested.
        m_plan = comp[headline_metric]["plan"]
        m_fact = comp[headline_metric]["fact"]
        if m_plan is not None and m_plan != 0:
            pct = float(m_fact or 0) / float(m_plan) * 100
        else:
            pct = None
        if pct is not None:
            sec_code = sector_code(co)
            sec_color = sector_color(co)
            by_company.append(
                BpCompanyRow(
                    company_id=co.id,
                    company_name_ru=co.name_ru or co.code or "—",
                    sector_code=sec_code,
                    sector_color=sec_color,
                    rev_fact=m_fact,
                    rev_plan=m_plan,
                    pct=pct,
                )
            )
            if sec_code:
                if sec_code not in sector_sums:
                    sector_sums[sec_code] = {
                        "label": (co.sector.name_ru if co.sector and co.sector.name_ru else sec_code),
                        "sum": Decimal(0),
                    }
                if m_fact is not None:
                    sector_sums[sec_code]["sum"] += Decimal(m_fact)

    by_company.sort(key=lambda r: -(r.pct or -1e9))

    # By sector — totals of HEADLINE metric across companies
    by_sector = [
        BpSectorRow(sector_code=k, label=v["label"], sum_revenue=v["sum"])
        for k, v in sector_sums.items()
    ]
    by_sector.sort(key=lambda r: -float(r.sum_revenue))

    # By quarter — sum of HEADLINE metric across all companies per quarter
    by_quarter: List[BpQuarterRow] = []
    for q in ("q1", "q2", "q3", "q4"):
        sum_plan, sum_fact = Decimal(0), Decimal(0)
        has_plan, has_fact = False, False
        for co in cos_full:
            qcomp = await bp_compute(db, co.id, year, q)
            if qcomp[headline_metric]["plan"] is not None:
                sum_plan += Decimal(qcomp[headline_metric]["plan"])
                has_plan = True
            if qcomp[headline_metric]["fact"] is not None:
                sum_fact += Decimal(qcomp[headline_metric]["fact"])
                has_fact = True
        by_quarter.append(
            BpQuarterRow(
                q=q,
                plan=sum_plan if has_plan else None,
                fact=sum_fact if has_fact else None,
            )
        )

    return BpSummary(
        year=year,
        period=period,
        co_count=len(cos_full),
        totals=[BpMetricTotal(metric=m, **totals[m]) for m in metrics_for_summary],
        prev_totals=[BpMetricTotal(metric=m, **prev_totals[m]) for m in metrics_for_summary],
        by_company=by_company,
        by_sector=by_sector,
        by_quarter=by_quarter,
    )


# ─── Raw records (for editor) ────────────────────────────────────
# IMPORTANT: This route MUST be registered BEFORE /{company_id}/{year}/{period}
# below — otherwise FastAPI matches `raw` as company_id and returns 422 for the
# UUID validation failure.

@router.get("/raw/{company_id}/{year}")
async def get_raw_records(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return all stored records for a company-year — used by the editor.

    Format: {period: {metric: {plan, expect, fact}}}
    """
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    rows = (
        await db.execute(
            select(BpRecord)
            .where(BpRecord.company_id == company_id)
            .where(BpRecord.year == year)
        )
    ).scalars().all()
    out: Dict[str, Dict[str, Dict]] = {p: {} for p in BP_PERIODS}
    for r in rows:
        out[r.period][r.metric] = {
            "plan": r.plan,
            "expect": r.expect,
            "fact": r.fact,
        }
    return out


# ─── Computed (catch-all for {company_id}/{year}/{period}) ────────

@router.get("/{company_id}/{year}/{period}", response_model=BpComputed)
async def get_computed(
    company_id: UUID,
    year: int,
    period: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    if period not in BP_PERIODS:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Invalid period: {period}")
    try:
        comp = await bp_compute(db, company_id, year, period)
        return BpComputed(
            company_id=company_id,
            year=year,
            period=period,
            metrics={k: BpCell(**comp[k]) for k in BP_METRIC_KEYS},
        )
    except Exception as e:
        import traceback
        print(f"[bp /{company_id}/{year}/{period}] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"compute failed: {type(e).__name__}: {e}",
        )


# ─── Upsert single + bulk ─────────────────────────────────────────

@router.post("/upsert")
async def upsert_one(
    payload: BpRecordUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.edit required")
    if payload.period not in BP_PERIODS:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Invalid period: {payload.period}")
    if payload.metric not in BP_METRIC_KEYS:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Invalid metric: {payload.metric}")
    await ensure_company_access(db, user, payload.company_id)

    stmt = pg_insert(BpRecord).values(
        company_id=payload.company_id,
        year=payload.year,
        period=payload.period,
        metric=payload.metric,
        plan=payload.plan,
        expect=payload.expect,
        fact=payload.fact,
    ).on_conflict_do_update(
        index_elements=["company_id", "year", "period", "metric"],
        set_={
            "plan": payload.plan,
            "expect": payload.expect,
            "fact": payload.fact,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}


@router.post("/bulk-upsert")
async def bulk_upsert(
    payload: BpBulkUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Editor save: replace many cells in one transaction.

    Pack 148-followup: gated by moderation. If user is not bypass and a
    rule matches (module='business_plan', action='bulk_upsert'), the write
    is queued instead of applied.
    """
    if not await has_effective_permission(db, user, "bp.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.edit required")

    # Scope check: резолвим allowed-set один раз, потом проверяем в цикле,
    # чтобы не дёргать БД на каждой записи. None = unrestricted.
    allowed_ids = None if has_unrestricted_view(user) else set(await allowed_company_ids(db, user) or [])

    # ── Moderation gate ────────────────────────────────────────
    # Use the first record's company_id/year for rule matching (records
    # touching multiple companies in one batch all share the same gate).
    from app.services.moderation_service import gate_or_apply
    first = payload.records[0] if payload.records else None
    queued, sub = await gate_or_apply(
        db, user=user,
        module="business_plan", action="bulk_upsert",
        entity_id=str(first.company_id) if first else None,
        entity_label=f"BP {first.year}" if first else "BP",
        company_id=first.company_id if first else None,
        sector_id=None,
        year=first.year if first else None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Bulk-upsert {len(payload.records)} ячеек бизнес-плана",
    )
    if queued:
        return {
            "queued": True,
            "submission_id": str(sub.id),
            "status": sub.status,
            "message": "Изменение отправлено на модерацию",
        }

    n = 0
    for rec in payload.records:
        if rec.period not in BP_PERIODS or rec.metric not in BP_METRIC_KEYS:
            continue
        if allowed_ids is not None and rec.company_id not in allowed_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                f"Access to company {rec.company_id} is not allowed",
            )
        stmt = pg_insert(BpRecord).values(
            company_id=rec.company_id,
            year=rec.year,
            period=rec.period,
            metric=rec.metric,
            plan=rec.plan,
            expect=rec.expect,
            fact=rec.fact,
        ).on_conflict_do_update(
            index_elements=["company_id", "year", "period", "metric"],
            set_={
                "plan": rec.plan,
                "expect": rec.expect,
                "fact": rec.fact,
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
        n += 1
    await db.commit()
    return {"upserted": n}


@router.delete("/{company_id}/{year}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_year(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.delete"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.delete required")
    await ensure_company_access(db, user, company_id)
    await db.execute(
        delete(BpRecord)
        .where(BpRecord.company_id == company_id)
        .where(BpRecord.year == year)
    )
    await db.execute(
        delete(BpComment)
        .where(BpComment.company_id == company_id)
        .where(BpComment.year == year)
    )
    await db.commit()


# ─── Summary across portfolio ─────────────────────────────────────

@router.get("/attention/{company_id}/{year}/{period}", response_model=List[BpAttentionIssue])
async def get_attention(
    company_id: UUID,
    year: int,
    period: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    issues = await bp_attention_issues(db, company_id, year, period)
    # Add KPI-side attention
    from app.services.bp_kpi_helpers import kpi_attention_issues as _kpi_iss
    kpi_iss = await _kpi_iss(db, company_id, year, period)
    return [BpAttentionIssue(**x) for x in issues + kpi_iss][:5]


# ─── Comments ────────────────────────────────────────────────────

@router.get("/comment/{company_id}/{year}/{period}", response_model=Optional[BpCommentRead])
async def get_comment(
    company_id: UUID,
    year: int,
    period: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    row = (
        await db.execute(
            select(BpComment)
            .where(BpComment.company_id == company_id)
            .where(BpComment.year == year)
            .where(BpComment.period == period)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return BpCommentRead.model_validate(row)


@router.put("/comment", response_model=BpCommentRead)
async def upsert_comment(
    payload: BpCommentUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.edit required")
    await ensure_company_access(db, user, payload.company_id)
    stmt = pg_insert(BpComment).values(
        company_id=payload.company_id,
        year=payload.year,
        period=payload.period,
        body=payload.body,
        author_id=user.id,
    ).on_conflict_do_update(
        index_elements=["company_id", "year", "period"],
        set_={"body": payload.body, "author_id": user.id, "updated_at": func.now()},
    ).returning(BpComment)
    row = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return BpCommentRead.model_validate(row)
