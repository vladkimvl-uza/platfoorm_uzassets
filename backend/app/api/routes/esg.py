"""ESG endpoints: overview dashboard + per-company detail + metrics/issues CRUD.

Endpoints:
  GET    /esg/overview                          Overview dashboard (pillars, rankings, KPIs)
  GET    /esg/companies/{company_id}            Per-company detail with metrics by pillar
  PUT    /esg/metric                            Upsert a metric (auto-create on first save)
  DELETE /esg/metric/{metric_id}                Remove a metric
  GET    /esg/issues                            List issues with filters
  POST   /esg/issue                             Create a new issue
  PATCH  /esg/issue/{issue_id}                  Update issue (status, severity, etc.)
  DELETE /esg/issue/{issue_id}                  Delete issue

Permissions:
  - esg.view  for all GETs
  - esg.edit  for PUT/POST/PATCH/DELETE
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import and_, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import _has_permission, get_current_user, has_effective_permission
from app.database import get_db
from app.models.company import Company, Sector
from app.models.esg import ESGIssue, ESGMetric, ESGNote, ESGYearTracked
from app.models.user import User
from app.schemas.esg import (
    ESGCompanyDetail,
    ESGCompanyScore,
    ESGIssueBrief,
    ESGIssueCreate,
    ESGIssueUpdate,
    ESGMetricBrief,
    ESGMetricUpsert,
    ESGOverviewKpis,
    ESGOverviewResponse,
    IssueSeverityStat,
    PillarStat,
)


router = APIRouter(prefix="/esg", tags=["esg"])


# =====================================================================
# Helpers
# =====================================================================

PILLARS = ["E", "S", "G"]

SEVERITY_META = [
    {"key": "low",      "label": "Низкая",       "color": "#7DC4A0"},
    {"key": "med",      "label": "Средняя",      "color": "#EF9F27"},
    {"key": "high",     "label": "Высокая",      "color": "#E24B4A"},
    {"key": "critical", "label": "Критическая", "color": "#991B1B"},
]


async def _allowed_company_filter(db: AsyncSession, user: User, query, company_col):
    if has_unrestricted_view(user):
        return query
    allowed = await allowed_company_ids(db, user)
    if not allowed:
        return query.where(company_col == None)  # noqa: E711
    return query.where(company_col.in_(allowed))


def _attainment_pct(value: Optional[Decimal], target: Optional[Decimal]) -> Optional[float]:
    if value is None or target is None or target == 0:
        return None
    try:
        return round(float(value) / float(target) * 100, 1)
    except (ValueError, ZeroDivisionError):
        return None


def _benchmark_diff_pct(value: Optional[Decimal], benchmark: Optional[Decimal]) -> Optional[float]:
    if value is None or benchmark is None or benchmark == 0:
        return None
    try:
        return round((float(value) - float(benchmark)) / float(benchmark) * 100, 1)
    except (ValueError, ZeroDivisionError):
        return None


def _metric_to_brief(m: ESGMetric, company_code: Optional[str] = None) -> ESGMetricBrief:
    return ESGMetricBrief(
        id=m.id,
        company_id=m.company_id,
        year=m.year,
        pillar=m.pillar,
        metric_code=m.metric_code,
        metric_name=m.metric_name,
        value=m.value,
        unit=m.unit,
        target=m.target,
        benchmark=m.benchmark,
        notes=m.notes,
        target_attainment_pct=_attainment_pct(m.value, m.target),
        benchmark_diff_pct=_benchmark_diff_pct(m.value, m.benchmark),
    )


def _company_score_from_metrics(metrics: List[ESGMetric]) -> dict:
    """Compute E/S/G scores (0-100) for a company from its metrics.

    Score formula per pillar:
      For each metric with target: contribution = min(100, value/target × 100)
      For each metric without target but with benchmark:
        contribution = 100 if value within ±10% of benchmark, else linear penalty
      Average across pillar's metrics.
    """
    scores = {"E": [], "S": [], "G": []}
    for m in metrics:
        if m.pillar not in scores: continue
        if m.value is None: continue
        if m.target and m.target != 0:
            contrib = min(100.0, max(0.0, float(m.value) / float(m.target) * 100))
            scores[m.pillar].append(contrib)
        elif m.benchmark and m.benchmark != 0:
            diff = abs(float(m.value) - float(m.benchmark)) / float(m.benchmark)
            contrib = max(0.0, 100.0 - diff * 200)  # 50% off → 0 score
            scores[m.pillar].append(contrib)

    out: dict[str, Optional[float]] = {}
    for p, lst in scores.items():
        out[p] = round(sum(lst) / len(lst), 1) if lst else None

    valid = [v for v in out.values() if v is not None]
    out["overall"] = round(sum(valid) / len(valid), 1) if valid else None
    return out


# =====================================================================
# Overview
# =====================================================================

@router.get("/overview", response_model=ESGOverviewResponse)
async def get_overview(
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    rankings_limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dashboard root: KPI cards + pillar stats + issue split + company rankings."""
    if not await has_effective_permission(db, user, "esg.view"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # ---- Fetch metrics
    m_q = select(ESGMetric)
    if year:
        m_q = m_q.where(ESGMetric.year == year)
    if sector_code:
        m_q = m_q.join(Company, Company.id == ESGMetric.company_id).join(
            Sector, Sector.id == Company.sector_id
        ).where(Sector.code == sector_code)
    m_q = await _allowed_company_filter(db, user, m_q, ESGMetric.company_id)
    metrics = (await db.execute(m_q)).scalars().all()

    # ---- Fetch issues (open only contribute to "open" count; all show in split)
    i_q = select(ESGIssue)
    if sector_code:
        i_q = i_q.join(Company, Company.id == ESGIssue.company_id).join(
            Sector, Sector.id == Company.sector_id
        ).where(Sector.code == sector_code)
    i_q = await _allowed_company_filter(db, user, i_q, ESGIssue.company_id)
    issues = (await db.execute(i_q)).scalars().all()

    # ---- Companies (for rankings)
    co_q = select(Company).options(selectinload(Company.sector))
    if sector_code:
        co_q = co_q.join(Sector, Sector.id == Company.sector_id).where(
            Sector.code == sector_code
        )
    co_q = await _allowed_company_filter(db, user, co_q, Company.id)
    companies = (await db.execute(co_q)).scalars().all()

    # ---- Pillar aggregations
    pillars: list[PillarStat] = []
    for p in PILLARS:
        p_metrics = [m for m in metrics if m.pillar == p]
        co_set = {m.company_id for m in p_metrics}
        attainments = []
        bench_diffs = []
        on_target = 0
        behind = 0
        for m in p_metrics:
            att = _attainment_pct(m.value, m.target)
            if att is not None:
                attainments.append(att)
                if att >= 100: on_target += 1
                else: behind += 1
            bd = _benchmark_diff_pct(m.value, m.benchmark)
            if bd is not None: bench_diffs.append(bd)

        pillars.append(PillarStat(
            pillar=p,
            metric_count=len(p_metrics),
            company_count=len(co_set),
            avg_target_attainment=round(sum(attainments) / len(attainments), 1) if attainments else None,
            avg_benchmark_diff=round(sum(bench_diffs) / len(bench_diffs), 1) if bench_diffs else None,
            on_target_count=on_target,
            behind_count=behind,
        ))

    # ---- Issue severity split
    sev_buckets = {meta["key"]: 0 for meta in SEVERITY_META}
    open_count = 0
    crit_count = 0
    for i in issues:
        if i.severity in sev_buckets: sev_buckets[i.severity] += 1
        if i.status == "open": open_count += 1
        if i.severity == "critical" and i.status != "closed": crit_count += 1

    sev_split = [
        IssueSeverityStat(
            severity=meta["key"],
            label=meta["label"],
            color=meta["color"],
            count=sev_buckets.get(meta["key"], 0),
        )
        for meta in SEVERITY_META
    ]

    # ---- Company rankings
    metrics_by_co: dict[UUID, list[ESGMetric]] = {}
    for m in metrics:
        metrics_by_co.setdefault(m.company_id, []).append(m)

    issues_by_co: dict[UUID, list[ESGIssue]] = {}
    for i in issues:
        issues_by_co.setdefault(i.company_id, []).append(i)

    rankings: list[ESGCompanyScore] = []
    overall_scores = []
    for co in companies:
        co_metrics = metrics_by_co.get(co.id, [])
        scores = _company_score_from_metrics(co_metrics)
        co_issues = issues_by_co.get(co.id, [])
        if scores["overall"] is not None:
            overall_scores.append(scores["overall"])
        years_set = {m.year for m in co_metrics}
        last_year = max(years_set) if years_set else None
        rankings.append(ESGCompanyScore(
            company_id=co.id,
            company_code=co.code,
            company_name=co.name_ru,
            sector_code=(co.sector.code if co.sector else None),
            e_score=scores["E"],
            s_score=scores["S"],
            g_score=scores["G"],
            overall_score=scores["overall"],
            metric_count=len(co_metrics),
            issues_open=sum(1 for i in co_issues if i.status == "open"),
            issues_critical=sum(1 for i in co_issues if i.severity == "critical"),
            last_year_reported=last_year,
        ))

    # Sort: highest overall_score first; companies without data sink to the bottom.
    rankings.sort(key=lambda r: (r.overall_score is None, -(r.overall_score or 0)))
    for idx, r in enumerate(rankings):
        r.rank = idx + 1
    rankings = rankings[:rankings_limit]

    # ---- KPIs
    kpis = ESGOverviewKpis(
        total_companies=len(companies),
        companies_with_data=len(metrics_by_co),
        metrics_total=len(metrics),
        issues_open=open_count,
        issues_critical=crit_count,
        avg_overall_score=round(sum(overall_scores) / len(overall_scores), 1) if overall_scores else None,
    )

    # ---- Available years + sectors
    yrs_q = await db.execute(
        select(ESGMetric.year).distinct().where(ESGMetric.year.is_not(None)),
    )
    yrs = sorted({r[0] for r in yrs_q.all() if r[0]}, reverse=True)

    secs_q = await db.execute(
        select(Sector.code, func.count(Company.id))
        .join(Company, Company.sector_id == Sector.id)
        .group_by(Sector.code),
    )
    sectors = [{"code": r[0], "count": r[1]} for r in secs_q.all()]

    return ESGOverviewResponse(
        year=year,
        sector_code=sector_code,
        kpis=kpis,
        pillars=pillars,
        issue_severity_split=sev_split,
        rankings=rankings,
        available_years=yrs,
        sectors=sectors,
        generated_at=datetime.now(timezone.utc),
    )


# =====================================================================
# Company detail
# =====================================================================

@router.get("/companies/{company_id}", response_model=ESGCompanyDetail)
async def get_company_detail(
    company_id: UUID,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Per-company ESG detail: metrics by pillar + issues + scores for a year."""
    if not await has_effective_permission(db, user, "esg.view"):
        raise HTTPException(status_code=403, detail="Forbidden")

    co_q = select(Company).options(selectinload(Company.sector)).where(Company.id == company_id)
    co_q = await _allowed_company_filter(db, user, co_q, Company.id)
    co = (await db.execute(co_q)).scalar_one_or_none()
    if not co:
        raise HTTPException(status_code=404, detail="Company not found")

    # Pick year — if not given, use the most recent year with data
    yrs_q = await db.execute(
        select(ESGMetric.year).distinct().where(ESGMetric.company_id == company_id),
    )
    available_years = sorted({r[0] for r in yrs_q.all() if r[0]}, reverse=True)

    target_year = year or (available_years[0] if available_years else datetime.now().year)

    m_q = await db.execute(
        select(ESGMetric).where(
            and_(ESGMetric.company_id == company_id, ESGMetric.year == target_year),
        ).order_by(ESGMetric.pillar, ESGMetric.metric_code),
    )
    metrics = m_q.scalars().all()

    metrics_e = [_metric_to_brief(m, co.code) for m in metrics if m.pillar == "E"]
    metrics_s = [_metric_to_brief(m, co.code) for m in metrics if m.pillar == "S"]
    metrics_g = [_metric_to_brief(m, co.code) for m in metrics if m.pillar == "G"]

    scores = _company_score_from_metrics(metrics)

    # Issues across all years (filter by status open/in_progress in UI)
    i_q = await db.execute(
        select(ESGIssue).where(ESGIssue.company_id == company_id)
        .order_by(desc(ESGIssue.created_at)),
    )
    issues = [
        ESGIssueBrief(
            id=i.id,
            company_id=i.company_id,
            company_code=co.code,
            company_name=co.name_ru,
            pillar=i.pillar,
            title=i.title,
            description=i.description,
            severity=i.severity,
            status=i.status,
            created_at=i.created_at,
        )
        for i in i_q.scalars().all()
    ]

    tr_q = await db.execute(
        select(ESGYearTracked.year).where(
            and_(ESGYearTracked.company_id == company_id, ESGYearTracked.is_active == True),
        ),
    )
    tracked = sorted({r[0] for r in tr_q.all()}, reverse=True)

    return ESGCompanyDetail(
        company_id=co.id,
        company_code=co.code,
        company_name=co.name_ru,
        sector_code=(co.sector.code if co.sector else None),
        year=target_year,
        e_score=scores["E"],
        s_score=scores["S"],
        g_score=scores["G"],
        overall_score=scores["overall"],
        metrics_e=metrics_e,
        metrics_s=metrics_s,
        metrics_g=metrics_g,
        issues=issues,
        available_years=available_years,
        tracked_years=tracked,
    )


# =====================================================================
# Metrics CRUD
# =====================================================================

@router.put("/metric", response_model=ESGMetricBrief)
async def upsert_metric(
    payload: ESGMetricUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upsert (create or update) a metric for company × year × metric_code."""
    if not await has_effective_permission(db, user, "esg.edit"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Verify company access
    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if payload.company_id not in allowed:
            raise HTTPException(status_code=403, detail="No access to this company")

    res = await db.execute(
        select(ESGMetric).where(and_(
            ESGMetric.company_id == payload.company_id,
            ESGMetric.year == payload.year,
            ESGMetric.metric_code == payload.metric_code,
        )),
    )
    m = res.scalar_one_or_none()

    if m is None:
        m = ESGMetric(
            company_id=payload.company_id,
            year=payload.year,
            pillar=payload.pillar,
            metric_code=payload.metric_code,
            metric_name=payload.metric_name,
            value=payload.value,
            unit=payload.unit,
            target=payload.target,
            benchmark=payload.benchmark,
            notes=payload.notes,
        )
        db.add(m)
    else:
        m.pillar = payload.pillar
        m.metric_name = payload.metric_name
        m.value = payload.value
        m.unit = payload.unit
        m.target = payload.target
        m.benchmark = payload.benchmark
        m.notes = payload.notes

    await db.commit()
    await db.refresh(m)
    return _metric_to_brief(m)


@router.delete("/metric/{metric_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_metric(
    metric_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "esg.edit"):
        raise HTTPException(status_code=403, detail="Forbidden")

    res = await db.execute(select(ESGMetric).where(ESGMetric.id == metric_id))
    m = res.scalar_one_or_none()
    if not m:
        return  # idempotent

    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if m.company_id not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")

    await db.delete(m)
    await db.commit()


# =====================================================================
# Issues CRUD
# =====================================================================

@router.get("/issues", response_model=List[ESGIssueBrief])
async def list_issues(
    company_id: Optional[UUID] = None,
    pillar: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "esg.view"):
        raise HTTPException(status_code=403, detail="Forbidden")

    q = select(ESGIssue)
    if company_id: q = q.where(ESGIssue.company_id == company_id)
    if pillar:     q = q.where(ESGIssue.pillar == pillar)
    if severity:   q = q.where(ESGIssue.severity == severity)
    if status:     q = q.where(ESGIssue.status == status)
    q = await _allowed_company_filter(db, user, q, ESGIssue.company_id)
    q = q.order_by(desc(ESGIssue.created_at)).limit(limit)

    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return []

    co_ids = list({r.company_id for r in rows})
    co_q = await db.execute(select(Company).where(Company.id.in_(co_ids)))
    co_lookup = {c.id: c for c in co_q.scalars().all()}

    return [
        ESGIssueBrief(
            id=r.id,
            company_id=r.company_id,
            company_code=co_lookup[r.company_id].code if r.company_id in co_lookup else None,
            company_name=co_lookup[r.company_id].name_ru if r.company_id in co_lookup else None,
            pillar=r.pillar,
            title=r.title,
            description=r.description,
            severity=r.severity,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/issue", response_model=ESGIssueBrief, status_code=http_status.HTTP_201_CREATED)
async def create_issue(
    payload: ESGIssueCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "esg.edit"):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if payload.company_id not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")

    issue = ESGIssue(
        company_id=payload.company_id,
        pillar=payload.pillar,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        status="open",
    )
    db.add(issue)
    await db.commit()
    await db.refresh(issue)

    co = (await db.execute(select(Company).where(Company.id == issue.company_id))).scalar_one_or_none()
    return ESGIssueBrief(
        id=issue.id,
        company_id=issue.company_id,
        company_code=co.code if co else None,
        company_name=co.name_ru if co else None,
        pillar=issue.pillar,
        title=issue.title,
        description=issue.description,
        severity=issue.severity,
        status=issue.status,
        created_at=issue.created_at,
    )


@router.patch("/issue/{issue_id}", response_model=ESGIssueBrief)
async def update_issue(
    issue_id: UUID,
    payload: ESGIssueUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "esg.edit"):
        raise HTTPException(status_code=403, detail="Forbidden")

    res = await db.execute(select(ESGIssue).where(ESGIssue.id == issue_id))
    i = res.scalar_one_or_none()
    if not i:
        raise HTTPException(status_code=404, detail="Issue not found")

    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if i.company_id not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")

    if payload.pillar is not None:      i.pillar = payload.pillar
    if payload.title is not None:       i.title = payload.title
    if payload.description is not None: i.description = payload.description
    if payload.severity is not None:    i.severity = payload.severity
    if payload.status is not None:      i.status = payload.status

    await db.commit()
    await db.refresh(i)

    co = (await db.execute(select(Company).where(Company.id == i.company_id))).scalar_one_or_none()
    return ESGIssueBrief(
        id=i.id,
        company_id=i.company_id,
        company_code=co.code if co else None,
        company_name=co.name_ru if co else None,
        pillar=i.pillar,
        title=i.title,
        description=i.description,
        severity=i.severity,
        status=i.status,
        created_at=i.created_at,
    )


@router.delete("/issue/{issue_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_issue(
    issue_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "esg.edit"):
        raise HTTPException(status_code=403, detail="Forbidden")

    res = await db.execute(select(ESGIssue).where(ESGIssue.id == issue_id))
    i = res.scalar_one_or_none()
    if not i: return  # idempotent

    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if i.company_id not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")

    await db.delete(i)
    await db.commit()
