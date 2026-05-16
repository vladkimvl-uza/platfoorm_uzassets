"""KPI dashboard REST API.

Endpoints:
  GET    /kpi/available-companies            — companies with KPI + years
  GET    /kpi/{company_id}/{year}            — full managers tree for a year
  PUT    /kpi/{company_id}/{year}            — replace managers tree (editor save)
  DELETE /kpi/{company_id}/{year}            — delete year
  GET    /kpi/summary/{year}/{period}        — portfolio-wide weighted summary
  GET    /kpi/attention/{company_id}/{year}/{period} — attention issues
  GET    /kpi/comment/{company_id}/{year}/{period}   — get comment
  PUT    /kpi/comment                                — upsert comment
  POST   /kpi/load-ngmk-template/{year}      — bootstrap НГМК 2026 template

Period in queries is 'annual' (mapped to 'year' internally) | q1..q4.
"""
from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, ensure_company_access, has_unrestricted_view
from app.models.bp_kpi import (
    KpiComment,
    KpiIndicator,
    KpiManager,
)
from app.models.company import Company, Sector
from app.models.user import User
from app.schemas.bp_kpi import (
    BpAvailableCompany,
    KpiAttentionIssue,
    KpiCommentRead,
    KpiCommentUpsert,
    KpiCompanyRow,
    KpiCompanyYearUpsert,
    KpiIndPayload,
    KpiIndicatorRead,
    KpiManagerRead,
    KpiQuarterAgg,
    KpiSectorRow,
    KpiSummary,
)
from app.services.bp_kpi_helpers import (
    kpi_attention_issues,
    kpi_compute_completion,
    kpi_status_for_pct,
    sector_code,
    sector_color,
)


log = logging.getLogger(__name__)
router = APIRouter(prefix="/kpi", tags=["kpi"])


def _has_permission(user: User, code: str) -> bool:
    """Pack 137: same fix as business_plan.py — iterate user.roles."""
    if not user:
        return False
    if getattr(user, "is_owner", False):
        return True
    if getattr(user, "email", "") == "v.kim@uz-assets.uz":
        return True
    roles = getattr(user, "roles", None) or []
    for r in roles:
        rcode = getattr(r, "code", "") or ""
        if rcode in ("admin", "ceo"):
            return True
        if rcode in ("debt", "readonly", "imv_admin") and code == "kpi.view":
            return True
        for p in (getattr(r, "permissions", None) or []):
            if getattr(p, "code", "") == code:
                return True
    perms = getattr(user, "permission_codes", None)
    if perms and code in perms:
        return True
    return False


# ─── Available companies + years ──────────────────────────────────

@router.get("/available-companies", response_model=List[BpAvailableCompany])
async def available_companies(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "kpi.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.view required")

    rows = (
        await db.execute(
            select(KpiManager.company_id, KpiManager.year).distinct()
        )
    ).all()
    if not rows:
        return []

    co_years: Dict[UUID, set[int]] = {}
    for cid, yr in rows:
        co_years.setdefault(cid, set()).add(yr)

    cos = (
        await db.execute(
            select(Company)
            .options(selectinload(Company.sector))
            .where(Company.id.in_(list(co_years.keys())))
        )
    ).scalars().all()

    out: List[BpAvailableCompany] = []
    for co in cos:
        out.append(
            BpAvailableCompany(
                company_id=co.id,
                company_name_ru=co.name_ru or co.code or "—",
                company_code=co.code,
                sector_code=sector_code(co),
                sector_color=sector_color(co),
                years=sorted(co_years.get(co.id, set()), reverse=True),
            )
        )
    out.sort(key=lambda c: c.company_name_ru)
    return out


# ─── Full managers tree for one (company, year) ───────────────────

@router.get("/{company_id}/{year}", response_model=List[KpiManagerRead])
async def get_company_year(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "kpi.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.view required")
    await ensure_company_access(db, user, company_id)
    rows = (
        await db.execute(
            select(KpiManager)
            .where(KpiManager.company_id == company_id)
            .where(KpiManager.year == year)
            .options(selectinload(KpiManager.indicators))
            .order_by(KpiManager.sort_order)
        )
    ).scalars().all()
    return [KpiManagerRead.model_validate(m) for m in rows]


# ─── Replace tree (editor save) ────────────────────────────────────

@router.put("/{company_id}/{year}")
async def replace_company_year(
    company_id: UUID,
    year: int,
    payload: KpiCompanyYearUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace ALL managers + indicators for a (company, year) scope.

    Done as: delete existing managers (cascades to indicators) → insert all.
    """
    if not _has_permission(user, "kpi.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.edit required")
    if payload.company_id != company_id or payload.year != year:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "company_id/year mismatch")
    await ensure_company_access(db, user, company_id)

    # Delete existing
    await db.execute(
        delete(KpiManager)
        .where(KpiManager.company_id == company_id)
        .where(KpiManager.year == year)
    )
    # Insert new
    inserted_mgr = 0
    inserted_ind = 0
    for mi, m in enumerate(payload.managers):
        mgr = KpiManager(
            company_id=company_id,
            year=year,
            sort_order=m.sort_order if m.sort_order is not None else mi,
            title=m.title,
            short_title=m.short_title,
            role=m.role,
        )
        db.add(mgr)
        await db.flush()
        for ii, ind in enumerate(m.indicators):
            db.add(KpiIndicator(
                manager_id=mgr.id,
                sort_order=ind.sort_order if ind.sort_order is not None else ii,
                name=ind.name,
                unit=ind.unit,
                weight=ind.weight,
                plan_year=ind.plan_year,
                fact_year=ind.fact_year,
                q1_weight=ind.q1_weight, q2_weight=ind.q2_weight,
                q3_weight=ind.q3_weight, q4_weight=ind.q4_weight,
                q1_plan=ind.q1_plan, q1_fact=ind.q1_fact,
                q2_plan=ind.q2_plan, q2_fact=ind.q2_fact,
                q3_plan=ind.q3_plan, q3_fact=ind.q3_fact,
                q4_plan=ind.q4_plan, q4_fact=ind.q4_fact,
                notes=ind.notes,
            ))
            inserted_ind += 1
        inserted_mgr += 1
    await db.commit()
    return {"managers": inserted_mgr, "indicators": inserted_ind}


@router.delete("/{company_id}/{year}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_year(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "kpi.delete"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.delete required")
    await ensure_company_access(db, user, company_id)
    await db.execute(
        delete(KpiManager)
        .where(KpiManager.company_id == company_id)
        .where(KpiManager.year == year)
    )
    await db.execute(
        delete(KpiComment)
        .where(KpiComment.company_id == company_id)
        .where(KpiComment.year == year)
    )
    await db.commit()


# ─── Summary across portfolio ─────────────────────────────────────

@router.get("/summary/{year}/{period}", response_model=KpiSummary)
async def get_summary(
    year: int,
    period: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Portfolio KPI summary. period='year' or 'q1'..'q4'.

    'annual' is accepted as alias for 'year'.
    """
    if not _has_permission(user, "kpi.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.view required")
    if period == "annual":
        period = "year"
    if period not in ("year", "q1", "q2", "q3", "q4"):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Invalid period: {period}")

    scope_set: Optional[set] = None
    if not has_unrestricted_view(user):
        scope = await allowed_company_ids(db, user)
        scope_set = set(scope or [])

    try:
        return await _kpi_summary_impl(db, year, period, scope_company_ids=scope_set)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[kpi /summary/{year}/{period}] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"summary failed: {type(e).__name__}: {e}",
        )


async def _kpi_summary_impl(
    db: AsyncSession,
    year: int,
    period: str,
    *,
    scope_company_ids: Optional[set] = None,
) -> KpiSummary:
    """Mirror of monolith _kpiComputeSummary (lines 39166–39305).

    Если `scope_company_ids` задан (set[UUID]) — агрегат строится только
    по этим компаниям. None — без фильтра (admin/owner).
    """
    if scope_company_ids is not None and not scope_company_ids:
        # Empty scope — empty summary, без дальнейших запросов.
        return KpiSummary(
            year=year, period=period, co_count=0, total_count=0,
            distribution={"over": [], "hit": [], "risk": [], "crit": [], "fail": []},
            by_company=[], by_sector=[], by_quarter=[],
            achievements=[], issues=[],
        )

    q = (
        select(KpiManager)
        .where(KpiManager.year == year)
        .options(selectinload(KpiManager.indicators), selectinload(KpiManager.company).selectinload(Company.sector))
        .order_by(KpiManager.company_id, KpiManager.sort_order)
    )
    if scope_company_ids is not None:
        q = q.where(KpiManager.company_id.in_(scope_company_ids))
    mgrs = (await db.execute(q)).scalars().all()

    if not mgrs:
        return KpiSummary(
            year=year, period=period, co_count=0, total_count=0,
            distribution={"over": [], "hit": [], "risk": [], "crit": [], "fail": []},
            by_company=[], by_sector=[], by_quarter=[],
            achievements=[], issues=[],
        )

    # Group by company
    by_co: Dict[UUID, Dict] = {}
    for m in mgrs:
        if m.company_id not in by_co:
            by_co[m.company_id] = {"company": m.company, "managers": []}
        by_co[m.company_id]["managers"].append(m)

    total_count = 0
    over_count = hit_count = risk_count = crit_count = fail_count = 0
    sum_weighted = 0.0
    sum_weights = 0.0
    distribution: Dict[str, List[KpiIndPayload]] = {"over": [], "hit": [], "risk": [], "crit": [], "fail": []}
    by_company: List[KpiCompanyRow] = []
    sector_agg: Dict[str, Dict] = {}
    all_inds: List[KpiIndPayload] = []

    for cid, e in by_co.items():
        co = e["company"]
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
                if w == 0:
                    continue
                total_count += 1
                co_count += 1
                cap_ratio = min(ratio, 1.5)  # cap at 150% (mirror monolith)
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
                    crit_count += 1
                    co_crit += 1

                if period == "year":
                    plan = ind.plan_year
                    fact = ind.fact_year
                else:
                    plan = getattr(ind, f"{period}_plan", None)
                    fact = getattr(ind, f"{period}_fact", None)

                payload = KpiIndPayload(
                    co_id=cid,
                    co_name=co_name,
                    mgr_idx=mi,
                    mgr=mgr.short_title or mgr.title or "",
                    ind_idx=ii,
                    ind_id=ind.id,
                    name=ind.name or "",
                    unit=ind.unit,
                    weight=Decimal(w),
                    plan=plan,
                    fact=fact,
                    ratio=ratio,
                    pct=pct,
                    status=status,
                )
                distribution[status].append(payload)
                all_inds.append(payload)

        if co_sum_w > 0:
            co_pct = co_sum_weighted / co_sum_w * 100
            by_company.append(
                KpiCompanyRow(
                    company_id=cid, co_name=co_name,
                    sector_code=sec_code, sector_color=sec_color,
                    count=co_count, hit=co_hit, risk=co_risk, crit=co_crit, pct=co_pct,
                )
            )
            if sec_code:
                if sec_code not in sector_agg:
                    sector_agg[sec_code] = {
                        "label": (co.sector.name_ru if co.sector and co.sector.name_ru else sec_code),
                        "sum_w": 0.0, "sum_weighted": 0.0, "count": 0, "co_count": 0,
                    }
                sector_agg[sec_code]["sum_w"] += co_sum_w
                sector_agg[sec_code]["sum_weighted"] += co_sum_weighted
                sector_agg[sec_code]["count"] += co_count
                sector_agg[sec_code]["co_count"] += 1

    by_company.sort(key=lambda r: -r.pct)

    by_sector = [
        KpiSectorRow(
            sector_code=k,
            label=v["label"],
            pct=(v["sum_weighted"] / v["sum_w"] * 100) if v["sum_w"] > 0 else None,
            count=v["count"], co_count=v["co_count"],
        )
        for k, v in sector_agg.items()
    ]
    by_sector.sort(key=lambda r: -(r.pct or -1e9))

    # By quarter — overall progress for each quarter
    by_quarter: List[KpiQuarterAgg] = []
    for q in ("q1", "q2", "q3", "q4"):
        q_sum_w = 0.0
        q_sum_wtd = 0.0
        has_plan = False
        for cid, e in by_co.items():
            for mgr in e["managers"]:
                for ind in mgr.indicators:
                    qw = float(getattr(ind, f"{q}_weight", 0) or 0)
                    if qw == 0:
                        continue
                    qp = getattr(ind, f"{q}_plan", None)
                    qf = getattr(ind, f"{q}_fact", None)
                    if qp is not None:
                        has_plan = True
                    if qf is not None and qp is not None and qp != 0:
                        q_sum_wtd += min(float(qf) / float(qp), 1.5) * qw
                        q_sum_w += qw
        by_quarter.append(KpiQuarterAgg(
            q=q,
            plan=100 if has_plan else None,
            fact=(q_sum_wtd / q_sum_w * 100) if q_sum_w > 0 else None,
        ))

    achievements = sorted(
        [x for x in all_inds if x.pct is not None and x.pct >= 105],
        key=lambda x: -(x.pct or 0),
    )[:5]
    issues = sorted(
        [x for x in all_inds if x.pct is not None and x.pct < 90 and float(x.weight) >= 5],
        key=lambda x: (x.pct or 0),
    )[:5]

    return KpiSummary(
        year=year,
        period=period,
        co_count=len(by_co),
        total_count=total_count,
        overall=(sum_weighted / sum_weights * 100) if sum_weights > 0 else None,
        over_count=over_count,
        hit_count=hit_count,
        risk_count=risk_count,
        crit_count=crit_count,
        fail_count=fail_count,
        distribution=distribution,
        by_company=by_company,
        by_sector=by_sector,
        by_quarter=by_quarter,
        achievements=achievements,
        issues=issues,
    )


# ─── Attention ────────────────────────────────────────────────────

@router.get("/attention/{company_id}/{year}/{period}", response_model=List[KpiAttentionIssue])
async def get_attention(
    company_id: UUID,
    year: int,
    period: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "kpi.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.view required")
    await ensure_company_access(db, user, company_id)
    issues = await kpi_attention_issues(db, company_id, year, period)
    return [KpiAttentionIssue(**x) for x in issues]


# ─── Comments ─────────────────────────────────────────────────────

@router.get("/comment/{company_id}/{year}/{period}", response_model=Optional[KpiCommentRead])
async def get_comment(
    company_id: UUID,
    year: int,
    period: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "kpi.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.view required")
    await ensure_company_access(db, user, company_id)
    row = (
        await db.execute(
            select(KpiComment)
            .where(KpiComment.company_id == company_id)
            .where(KpiComment.year == year)
            .where(KpiComment.period == period)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return KpiCommentRead.model_validate(row)


@router.put("/comment", response_model=KpiCommentRead)
async def upsert_comment(
    payload: KpiCommentUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "kpi.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.edit required")
    await ensure_company_access(db, user, payload.company_id)
    stmt = pg_insert(KpiComment).values(
        company_id=payload.company_id,
        year=payload.year,
        period=payload.period,
        body=payload.body,
        author_id=user.id,
    ).on_conflict_do_update(
        index_elements=["company_id", "year", "period"],
        set_={"body": payload.body, "author_id": user.id, "updated_at": func.now()},
    ).returning(KpiComment)
    row = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return KpiCommentRead.model_validate(row)


# ─── NGMK Template loader ─────────────────────────────────────────

@router.post("/load-ngmk-template/{year}")
async def load_ngmk_template(
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bootstrap NGMK KPI template (4 managers, 27 indicators) for a year.

    Mirror of monolith _kpiLoadNGMKTemplate. Reads JSON from app/scripts/ngmk_kpi_template.json.
    """
    if not _has_permission(user, "kpi.import"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "kpi.import required")

    # Find NGMK company
    co = (
        await db.execute(
            select(Company).where(func.lower(Company.code) == "ngmk")
        )
    ).scalar_one_or_none()
    if co is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company NGMK (code='ngmk') not found")

    # Check existing
    existing = (
        await db.execute(
            select(func.count())
            .select_from(KpiManager)
            .where(KpiManager.company_id == co.id)
            .where(KpiManager.year == year)
        )
    ).scalar_one()
    if existing > 0:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            detail=f"NGMK already has {existing} managers for {year}. Delete year first.",
        )

    # Load template JSON
    path = Path(__file__).parent.parent.parent / "scripts" / "ngmk_kpi_template.json"
    if not path.exists():
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Template not found: {path}",
        )
    with open(path, encoding="utf-8") as f:
        template = json.load(f)

    inserted_mgr = 0
    inserted_ind = 0
    for mi, m in enumerate(template["managers"]):
        mgr = KpiManager(
            company_id=co.id,
            year=year,
            sort_order=mi,
            title=m.get("title", ""),
            short_title=m.get("shortTitle"),
            role=m.get("role"),
        )
        db.add(mgr)
        await db.flush()
        for ii, ind in enumerate(m.get("indicators", [])):
            q = ind.get("quarters", {})
            db.add(KpiIndicator(
                manager_id=mgr.id,
                sort_order=ii,
                name=ind.get("name", ""),
                unit=ind.get("unit"),
                weight=Decimal(str(ind.get("weight", 0))),
                plan_year=Decimal(str(ind["planYear"])) if ind.get("planYear") is not None else None,
                fact_year=Decimal(str(ind["factYear"])) if ind.get("factYear") is not None else None,
                q1_weight=Decimal(str((q.get("q1") or {}).get("weight", 0))),
                q2_weight=Decimal(str((q.get("q2") or {}).get("weight", 0))),
                q3_weight=Decimal(str((q.get("q3") or {}).get("weight", 0))),
                q4_weight=Decimal(str((q.get("q4") or {}).get("weight", 0))),
                q1_plan=Decimal(str((q.get("q1") or {}).get("plan"))) if (q.get("q1") or {}).get("plan") is not None else None,
                q1_fact=Decimal(str((q.get("q1") or {}).get("fact"))) if (q.get("q1") or {}).get("fact") is not None else None,
                q2_plan=Decimal(str((q.get("q2") or {}).get("plan"))) if (q.get("q2") or {}).get("plan") is not None else None,
                q2_fact=Decimal(str((q.get("q2") or {}).get("fact"))) if (q.get("q2") or {}).get("fact") is not None else None,
                q3_plan=Decimal(str((q.get("q3") or {}).get("plan"))) if (q.get("q3") or {}).get("plan") is not None else None,
                q3_fact=Decimal(str((q.get("q3") or {}).get("fact"))) if (q.get("q3") or {}).get("fact") is not None else None,
                q4_plan=Decimal(str((q.get("q4") or {}).get("plan"))) if (q.get("q4") or {}).get("plan") is not None else None,
                q4_fact=Decimal(str((q.get("q4") or {}).get("fact"))) if (q.get("q4") or {}).get("fact") is not None else None,
            ))
            inserted_ind += 1
        inserted_mgr += 1

    await db.commit()
    return {
        "company_id": str(co.id),
        "company_name": co.name_ru,
        "year": year,
        "managers_added": inserted_mgr,
        "indicators_added": inserted_ind,
    }
