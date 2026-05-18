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
from datetime import date, datetime, timezone
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
from app.models.agency_rating import AgencyRating, ESG_AGENCIES
from app.models.company import Company, Sector
from app.models.esg import ESGIssue, ESGMetric, ESGNote, ESGYearTracked
from app.models.user import User
from app.schemas.esg import (
    AgencyCoverageStat,
    AgencyRatingCell,
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
    RecentRatingUpdate,
    SectorBreakdownItem,
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

# Monolith canonical 3 ESG agencies (`ESG_AGENCIES` in showESGView).
# `AgencyRating.is_esg` lets through Sustainalytics / MSCI too, but the
# Executive Cockpit columns are these three.
ESG_OVERVIEW_AGENCIES = ["Sustainable Fitch", "S&P ESG", "CDP"]

AGENCY_COLORS = {
    "Sustainable Fitch": "#1D9E75",
    "S&P ESG":           "#378ADD",
    "CDP":               "#EF9F27",
    "Sustainalytics":    "#7F77DD",
    "MSCI":              "#A855F7",
}

SECTOR_LABELS_RU = {
    "mining":       "Горнодобыча",
    "oil_gas":      "Нефтегаз",
    "oilgas":       "Нефтегаз",
    "energy":       "Энергетика",
    "transport":    "Транспорт",
    "telecom":      "Телеком",
    "finance":      "Финансы",
    "chemical":     "Химия",
    "construction": "Строительство",
    "other":        "Другие",
}

SECTOR_FALLBACK_COLORS = {
    "mining":       "#9B8EC4",
    "oil_gas":      "#1D9E75",
    "oilgas":       "#1D9E75",
    "energy":       "#EF9F27",
    "transport":    "#378ADD",
    "telecom":      "#D4537E",
    "finance":      "#534AB7",
    "chemical":     "#A855F7",
    "construction": "#888780",
    "other":        "#888780",
}


def _esg_rating_to_score(rating: Optional[str]) -> Optional[float]:
    """Monolith `_esgRatingToScore` — convert rating text to 0..10 score."""
    if not rating:
        return None
    rv = str(rating).strip().upper()
    # Pure numeric ratings: SF 1..5 = (5-n)*2; integer 0..100 = n/10
    try:
        n = int(rv)
        if 0 <= n <= 5 and len(rv) <= 3:
            return float((5 - n) * 2)
        if 0 <= n <= 100:
            return n / 10.0
    except ValueError:
        pass
    # Letter ratings (S&P/Fitch/Moody's analogue)
    letter_map = {
        "AAA": 10, "AA+": 9.5, "AA": 9, "AA-": 8.5,
        "A+":  8.2, "A":  7.7, "A-": 7.2,
        "BBB+": 6.6, "BBB": 6, "BBB-": 5.4,
        "BB+":  4.8, "BB":  4.2, "BB-":  3.6,
        "B+":   3.2, "B":   2.7, "B-":   2.2,
        "CCC+": 1.8, "CCC": 1.4, "CCC-": 1,
        "CC":   0.7, "C":   0.4, "D":    0, "F": 0,
    }
    return letter_map.get(rv)


def _esg_score_to_letter(s: Optional[float]) -> str:
    if s is None:
        return "—"
    if s >= 9.3:  return "AA"
    if s >= 8.5:  return "AA-"
    if s >= 8.0:  return "A+"
    if s >= 7.5:  return "A"
    if s >= 7.0:  return "A-"
    if s >= 6.5:  return "BBB+"
    if s >= 5.8:  return "BBB"
    if s >= 5.2:  return "BBB-"
    if s >= 4.6:  return "BB+"
    if s >= 4.0:  return "BB"
    if s >= 3.4:  return "BB-"
    if s >= 3.0:  return "B+"
    if s >= 2.5:  return "B"
    if s >= 2.0:  return "B-"
    if s >= 1.6:  return "CCC+"
    if s >= 1.2:  return "CCC"
    if s >= 0.8:  return "CCC-"
    if s >= 0.4:  return "CC"
    return "C"


def _is_recent_rating(text_date: Optional[str], parsed_date: Optional["date"]) -> bool:
    """Monolith `isRecentlyUpdated` — rating refreshed in current or previous year."""
    cy = datetime.now(timezone.utc).year
    if parsed_date is not None:
        return parsed_date.year >= (cy - 1)
    if not text_date:
        return False
    s = str(text_date)
    return str(cy) in s or str(cy - 1) in s


def _sector_label(code: Optional[str]) -> str:
    if not code:
        return SECTOR_LABELS_RU["other"]
    norm = code.lower().replace("-", "_")
    return SECTOR_LABELS_RU.get(norm, code)


def _sector_fallback_color(code: Optional[str]) -> str:
    if not code:
        return "#888780"
    norm = code.lower().replace("-", "_")
    return SECTOR_FALLBACK_COLORS.get(norm, "#888780")


def _company_abbr(co: Company) -> str:
    code = (co.code or "").strip()
    if not code:
        return "?"
    return code.upper() if len(code) <= 6 else code[:4].upper()


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

    # ---- Fetch ESG agency ratings (Sustainable Fitch / S&P ESG / CDP / …)
    r_q = select(AgencyRating).where(AgencyRating.is_esg == True)  # noqa: E712
    r_q = await _allowed_company_filter(db, user, r_q, AgencyRating.company_id)
    ratings_rows = (await db.execute(r_q)).scalars().all()
    ratings_by_co: dict[UUID, dict[str, AgencyRating]] = {}
    for r in ratings_rows:
        ratings_by_co.setdefault(r.company_id, {})[r.agency] = r

    rankings: list[ESGCompanyScore] = []
    overall_scores = []
    composite_scores: list[tuple[Company, float]] = []
    recent_updates_payload: list[tuple[Company, AgencyRating]] = []

    for co in companies:
        co_metrics = metrics_by_co.get(co.id, [])
        scores = _company_score_from_metrics(co_metrics)
        co_issues = issues_by_co.get(co.id, [])
        if scores["overall"] is not None:
            overall_scores.append(scores["overall"])
        years_set = {m.year for m in co_metrics}
        last_year = max(years_set) if years_set else None

        sector_code = co.sector.code if co.sector else None
        sector_color = (co.primary_color
                        or (co.sector.color_hex if co.sector else None)
                        or _sector_fallback_color(sector_code))

        # Build per-agency cells (monolith _esgBadge / gR)
        co_ratings = ratings_by_co.get(co.id, {})
        cells: list[AgencyRatingCell] = []
        co_composite_parts: list[float] = []
        co_recent = 0
        for ag in ESG_OVERVIEW_AGENCIES:
            ar = co_ratings.get(ag)
            if ar is None:
                cells.append(AgencyRatingCell(agency=ag))
                continue
            is_recent = _is_recent_rating(ar.rating_date_text, ar.rating_date)
            if is_recent:
                co_recent += 1
                recent_updates_payload.append((co, ar))
            cells.append(AgencyRatingCell(
                agency=ag,
                rating=ar.rating,
                score=ar.score,
                outlook=ar.outlook,
                rating_date_text=ar.rating_date_text,
                report_url=ar.report_url,
                is_recent=is_recent,
            ))
            s = _esg_rating_to_score(ar.rating)
            if s is not None:
                co_composite_parts.append(s)

        composite = (sum(co_composite_parts) / len(co_composite_parts)) if co_composite_parts else None
        has_any = any(c.rating for c in cells)
        if composite is not None:
            composite_scores.append((co, composite))

        rankings.append(ESGCompanyScore(
            company_id=co.id,
            company_code=co.code,
            company_name=co.name_ru,
            company_abbr=_company_abbr(co),
            sector_code=sector_code,
            sector_color=sector_color,
            e_score=scores["E"],
            s_score=scores["S"],
            g_score=scores["G"],
            overall_score=scores["overall"],
            metric_count=len(co_metrics),
            issues_open=sum(1 for i in co_issues if i.status == "open"),
            issues_critical=sum(1 for i in co_issues if i.severity == "critical"),
            last_year_reported=last_year,
            ratings_by_agency=cells,
            composite_esg_score=round(composite, 2) if composite is not None else None,
            has_any_rating=has_any,
            recent_updates_count=co_recent,
        ))

    # Sort: prefer composite agency-based score; fall back to overall_score; nulls last.
    def _rank_sort_key(r: ESGCompanyScore):
        primary = r.composite_esg_score if r.composite_esg_score is not None else (
            r.overall_score / 10 if r.overall_score is not None else None
        )
        return (primary is None, -(primary or 0))

    rankings.sort(key=_rank_sort_key)
    for idx, r in enumerate(rankings):
        r.rank = idx + 1
    rankings = rankings[:rankings_limit]

    # ---- KPIs (Coverage / Leader / Без рейтинга / Обновления)
    covered = sum(1 for r in rankings if r.has_any_rating)
    total = len(companies)
    coverage_pct = round(100 * covered / total) if total else 0
    unrated = total - covered
    recent_total = sum(r.recent_updates_count for r in rankings)

    leader_co = None
    leader_comp = None
    if composite_scores:
        composite_scores.sort(key=lambda x: -x[1])
        leader_co, leader_comp = composite_scores[0]
    leader_ratings = 0
    if leader_co is not None:
        leader_ratings = sum(1 for c in (ratings_by_co.get(leader_co.id) or {}).values()
                             if c.agency in ESG_OVERVIEW_AGENCIES)

    kpis = ESGOverviewKpis(
        total_companies=total,
        companies_with_data=len(metrics_by_co),
        metrics_total=len(metrics),
        issues_open=open_count,
        issues_critical=crit_count,
        avg_overall_score=round(sum(overall_scores) / len(overall_scores), 1) if overall_scores else None,
        covered_count=covered,
        coverage_pct=coverage_pct,
        leader_company_id=leader_co.id if leader_co else None,
        leader_company_name=leader_co.name_ru if leader_co else None,
        leader_composite=round(leader_comp, 2) if leader_comp is not None else None,
        leader_rating_letter=_esg_score_to_letter(leader_comp) if leader_comp is not None else None,
        leader_ratings_count=leader_ratings,
        unrated_count=unrated,
        recent_updates_count=recent_total,
    )

    # ---- Agency coverage (for donut)
    agency_coverage: list[AgencyCoverageStat] = []
    for ag in ESG_OVERVIEW_AGENCIES:
        cnt = sum(1 for co_id in ratings_by_co
                  if ag in ratings_by_co[co_id] and ratings_by_co[co_id][ag].rating)
        agency_coverage.append(AgencyCoverageStat(
            agency=ag, count=cnt, color=AGENCY_COLORS.get(ag, "#888780"),
        ))

    # ---- Sector breakdown
    by_sector: dict[str, list[ESGCompanyScore]] = {}
    for r in rankings:
        key = r.sector_code or "other"
        by_sector.setdefault(key, []).append(r)
    sector_breakdown: list[SectorBreakdownItem] = []
    for sec_code, rows in by_sector.items():
        rated = [r for r in rows if r.composite_esg_score is not None]
        if rated:
            top = max(rated, key=lambda r: r.composite_esg_score or 0)
            top_co_id = top.company_id
            top_name = top.company_name
            top_comp = top.composite_esg_score
        else:
            top_co_id = top_name = top_comp = None
        sector_breakdown.append(SectorBreakdownItem(
            code=sec_code,
            label=_sector_label(sec_code),
            color=_sector_fallback_color(sec_code),
            total=len(rows),
            covered=sum(1 for r in rows if r.has_any_rating),
            coverage_pct=round(100 * sum(1 for r in rows if r.has_any_rating) / len(rows)) if rows else 0,
            leader_company_id=top_co_id,
            leader_company_name=top_name,
            leader_composite=top_comp,
        ))
    sector_breakdown.sort(key=lambda s: (-s.coverage_pct, -s.total))

    # ---- Recent updates (sorted by parsed date desc; fallback to insertion order)
    recent_updates_payload.sort(
        key=lambda t: (t[1].rating_date or date.min),
        reverse=True,
    )
    recent_updates: list[RecentRatingUpdate] = []
    for co, ar in recent_updates_payload[:10]:
        sector_code = co.sector.code if co.sector else None
        recent_updates.append(RecentRatingUpdate(
            company_id=co.id,
            company_code=co.code,
            company_name=co.name_ru or co.code,
            sector_code=sector_code,
            sector_color=(co.primary_color
                          or (co.sector.color_hex if co.sector else None)
                          or _sector_fallback_color(sector_code)),
            agency=ar.agency,
            agency_color=AGENCY_COLORS.get(ar.agency, "#888780"),
            rating=ar.rating,
            score=ar.score,
            rating_date_text=ar.rating_date_text,
            report_url=ar.report_url,
        ))

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
        agency_coverage=agency_coverage,
        sector_breakdown=sector_breakdown,
        recent_updates=recent_updates,
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

    # ── Moderation gate ────────────────────────────────────────
    from fastapi.responses import JSONResponse
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="esg", action="upsert_metric",
        entity_id=None,
        entity_label=f"ESG metric {payload.metric_code} {payload.year}",
        company_id=payload.company_id, sector_id=None, year=payload.year,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"ESG · {payload.pillar} · {payload.metric_code}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

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

    # ── Moderation gate ────────────────────────────────────────
    from fastapi.responses import JSONResponse
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="esg", action="create_issue",
        entity_id=None, entity_label=f"ESG issue: {payload.title}",
        company_id=payload.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"ESG · {payload.pillar} · {payload.severity} · {payload.title}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

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

    # ── Moderation gate ────────────────────────────────────────
    from fastapi.responses import JSONResponse
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="esg", action="update_issue",
        entity_id=str(issue_id), entity_label=f"ESG issue: {i.title}",
        company_id=i.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json", exclude_unset=True),
        diff_summary=f"Обновление ESG-issue '{i.title}'",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

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
