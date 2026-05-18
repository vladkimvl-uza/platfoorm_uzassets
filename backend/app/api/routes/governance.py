"""Governance endpoints: overview dashboard + per-company detail + data/members CRUD.

Endpoints:
  GET    /governance/overview                       Overview dashboard
  GET    /governance/companies/{company_id}         Per-company detail
  PUT    /governance/data                           Upsert GovernanceData (one per company × year)
  GET    /governance/companies/{company_id}/members List board members
  POST   /governance/member                         Add a board member
  PATCH  /governance/member/{member_id}             Update board member
  DELETE /governance/member/{member_id}             Delete board member

Permissions:
  - governance.view  for all GETs
  - governance.edit  for PUT/POST/PATCH/DELETE
"""
from datetime import datetime, timezone
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
from app.models.governance import BoardMember, GovernanceData
from app.models.user import User
from app.schemas.governance import (
    BoardMemberBrief,
    BoardMemberCreate,
    BoardMemberUpdate,
    DiversityStat,
    GovernanceCompanyDetail,
    GovernanceCompanyScore,
    GovernanceDataBrief,
    GovernanceDataEdit,
    GovernanceOverviewKpis,
    GovernanceOverviewResponse,
)


router = APIRouter(prefix="/governance", tags=["governance"])


# =====================================================================
# Helpers
# =====================================================================

async def _allowed_company_filter(db: AsyncSession, user: User, query, company_col):
    if has_unrestricted_view(user):
        return query
    allowed = await allowed_company_ids(db, user)
    if not allowed:
        return query.where(company_col == None)  # noqa: E711
    return query.where(company_col.in_(allowed))


def _governance_score(d: GovernanceData) -> Optional[float]:
    """Compute composite governance score 0..100 from a GovernanceData row.

    Weights:
      - 25% independence ratio (target: >=33% independent)
      - 15% women ratio (target: >=20%)
      - 10% foreign ratio (target: >=10%)
      - 25% committees present (4 of 4)
      - 15% attendance (target: >=80%)
      - 10% meetings (target: >=4 per year)
    """
    if d.board_size is None or d.board_size == 0:
        return None

    parts: list[tuple[float, float]] = []   # (weight, score-0-1)

    # Independence (target 33%)
    if d.independent_directors_count is not None:
        ratio = d.independent_directors_count / d.board_size
        score = min(1.0, ratio / 0.33)
        parts.append((0.25, score))

    # Women (target 20%)
    if d.women_directors_count is not None:
        ratio = d.women_directors_count / d.board_size
        score = min(1.0, ratio / 0.20)
        parts.append((0.15, score))

    # Foreign (target 10%)
    if d.foreign_directors_count is not None:
        ratio = d.foreign_directors_count / d.board_size
        score = min(1.0, ratio / 0.10)
        parts.append((0.10, score))

    # Committees (4 total)
    n_committees = sum(1 for x in [
        d.has_audit_committee,
        d.has_remuneration_committee,
        d.has_nomination_committee,
        d.has_strategy_committee,
    ] if x)
    parts.append((0.25, n_committees / 4))

    # Attendance (target 80%)
    if d.avg_attendance_pct is not None:
        score = min(1.0, d.avg_attendance_pct / 80)
        parts.append((0.15, score))

    # Meetings (target 4/year)
    if d.meetings_per_year is not None:
        score = min(1.0, d.meetings_per_year / 4)
        parts.append((0.10, score))

    if not parts: return None

    total_weight = sum(w for w, _ in parts)
    weighted = sum(w * s for w, s in parts) / total_weight
    return round(weighted * 100, 1)


def _co_data_to_score_row(d: GovernanceData, co: Company) -> GovernanceCompanyScore:
    bs = d.board_size or 0
    indep_pct = round(100 * d.independent_directors_count / bs, 1) if d.independent_directors_count is not None and bs else None
    wm_pct = round(100 * d.women_directors_count / bs, 1) if d.women_directors_count is not None and bs else None
    fo_pct = round(100 * d.foreign_directors_count / bs, 1) if d.foreign_directors_count is not None and bs else None

    n_committees = sum(1 for x in [
        d.has_audit_committee,
        d.has_remuneration_committee,
        d.has_nomination_committee,
        d.has_strategy_committee,
    ] if x)

    # Pull monolith-extended fields out of GovernanceData.payload (seeded from GOV_DATA).
    payload = d.payload or {}
    sector = co.sector
    sector_color = (
        co.primary_color
        or (sector.color_hex if sector else None)
        or "#888780"
    )
    # `co.code` is lowercase abbr in the seed (e.g. 'ngmk'); upper-case for display.
    abbr = (co.code or "").upper() if co.code else None

    def _bool_or_none(v):
        if v is None:
            return None
        return bool(v)

    return GovernanceCompanyScore(
        company_id=co.id,
        company_code=co.code,
        company_name=co.name_ru,
        company_abbr=abbr,
        sector_code=(sector.code if sector else None),
        sector_color=sector_color,
        year=d.year,
        board_size=d.board_size,
        independent_count=d.independent_directors_count,
        women_count=d.women_directors_count,
        foreign_count=d.foreign_directors_count,
        vacant_seats=payload.get("vacant"),
        exec_count=payload.get("exec"),
        nonexec_count=payload.get("nonexec"),
        independent_pct=indep_pct,
        women_pct=wm_pct,
        foreign_pct=fo_pct,
        committees_count=n_committees,
        has_all_4_committees=(n_committees == 4),
        has_audit_committee=d.has_audit_committee,
        has_remuneration_committee=d.has_remuneration_committee,
        has_nomination_committee=d.has_nomination_committee,
        has_strategy_committee=d.has_strategy_committee,
        has_anticorr_committee=_bool_or_none(payload.get("anticorr")),
        has_procurement_committee=_bool_or_none(payload.get("procurement")),
        has_esg_committee=_bool_or_none(payload.get("esg")),
        has_dno_insurance=_bool_or_none(payload.get("dno")),
        has_induction_program=_bool_or_none(payload.get("induction")),
        meetings_per_year=d.meetings_per_year,
        attendance_pct=d.avg_attendance_pct,
        governance_score=_governance_score(d),
        governance_score_1200=payload.get("score"),
        age_avg=payload.get("ageAvg") if payload.get("ageAvg") is not None else d.avg_age,
        age_min=payload.get("ageMin"),
        age_max=payload.get("ageMax"),
    )


def _data_to_brief(d: GovernanceData) -> GovernanceDataBrief:
    return GovernanceDataBrief.model_validate(d, from_attributes=True)


def _member_to_brief(m: BoardMember) -> BoardMemberBrief:
    return BoardMemberBrief.model_validate(m, from_attributes=True)


# =====================================================================
# Overview
# =====================================================================

@router.get("/overview", response_model=GovernanceOverviewResponse)
async def get_overview(
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    rankings_limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dashboard root: KPI cards + diversity split + company rankings."""
    if not await has_effective_permission(db, user, "governance.view"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Companies
    co_q = select(Company).options(selectinload(Company.sector))
    if sector_code:
        co_q = co_q.join(Sector, Sector.id == Company.sector_id).where(Sector.code == sector_code)
    co_q = await _allowed_company_filter(db, user, co_q, Company.id)
    companies = (await db.execute(co_q)).scalars().all()

    # Governance data — pick most-recent year per company if year not specified
    d_q = select(GovernanceData)
    if year:
        d_q = d_q.where(GovernanceData.year == year)
    if sector_code:
        d_q = d_q.join(Company, Company.id == GovernanceData.company_id).join(Sector, Sector.id == Company.sector_id).where(Sector.code == sector_code)
    d_q = await _allowed_company_filter(db, user, d_q, GovernanceData.company_id)
    all_data = (await db.execute(d_q)).scalars().all()

    # Group by company; if year filter not set, keep latest per company
    by_co: dict[UUID, GovernanceData] = {}
    for d in all_data:
        existing = by_co.get(d.company_id)
        if existing is None or (d.year or 0) > (existing.year or 0):
            by_co[d.company_id] = d

    # Build company rankings
    rankings: list[GovernanceCompanyScore] = []
    co_lookup = {co.id: co for co in companies}
    for co_id, d in by_co.items():
        co = co_lookup.get(co_id)
        if not co: continue
        rankings.append(_co_data_to_score_row(d, co))

    # Sort by the monolith raw score (0..1200) when available; otherwise fall back
    # to the computed 0..100 composite. This matches the monolith dashboard order.
    def _sort_key(r: GovernanceCompanyScore):
        primary = r.governance_score_1200 if r.governance_score_1200 is not None else r.governance_score
        return (primary is None, -(primary or 0))
    rankings.sort(key=_sort_key)
    for idx, r in enumerate(rankings):
        r.rank = idx + 1
    rankings = rankings[:rankings_limit]

    # KPIs — average across all companies with data
    if rankings:
        bsizes = [r.board_size for r in rankings if r.board_size]
        ipcts = [r.independent_pct for r in rankings if r.independent_pct is not None]
        wpcts = [r.women_pct for r in rankings if r.women_pct is not None]
        fpcts = [r.foreign_pct for r in rankings if r.foreign_pct is not None]
        attns = [r.attendance_pct for r in rankings if r.attendance_pct is not None]
        meets = [r.meetings_per_year for r in rankings if r.meetings_per_year is not None]

        kpis = GovernanceOverviewKpis(
            total_companies=len(companies),
            companies_with_data=len(rankings),
            avg_board_size=round(sum(bsizes) / len(bsizes), 1) if bsizes else None,
            avg_independent_pct=round(sum(ipcts) / len(ipcts), 1) if ipcts else None,
            avg_women_pct=round(sum(wpcts) / len(wpcts), 1) if wpcts else None,
            avg_foreign_pct=round(sum(fpcts) / len(fpcts), 1) if fpcts else None,
            avg_attendance_pct=round(sum(attns) / len(attns), 1) if attns else None,
            avg_meetings_per_year=round(sum(meets) / len(meets), 1) if meets else None,
            committees_audit_count=sum(1 for d in by_co.values() if d.has_audit_committee),
            committees_remuneration_count=sum(1 for d in by_co.values() if d.has_remuneration_committee),
            committees_nomination_count=sum(1 for d in by_co.values() if d.has_nomination_committee),
            committees_strategy_count=sum(1 for d in by_co.values() if d.has_strategy_committee),
        )
    else:
        kpis = GovernanceOverviewKpis(total_companies=len(companies))

    # Diversity split (independent / state-rep / executive / other) — based on board members table
    bm_q = select(BoardMember)
    if sector_code:
        bm_q = bm_q.join(Company, Company.id == BoardMember.company_id).join(Sector, Sector.id == Company.sector_id).where(Sector.code == sector_code)
    bm_q = await _allowed_company_filter(db, user, bm_q, BoardMember.company_id)
    bm_q = bm_q.where(
        (BoardMember.term_end_date == None) | (BoardMember.term_end_date >= datetime.now(timezone.utc).date()),  # noqa: E711
    )
    members = (await db.execute(bm_q)).scalars().all()

    by_role: dict[str, int] = {}
    for m in members:
        rt = m.role_type or "other"
        by_role[rt] = by_role.get(rt, 0) + 1

    total_members = sum(by_role.values()) or 1
    diversity_split = []
    role_palette = [
        ("independent",   "Независимые",       "#1D9E75"),
        ("chairman",      "Председатели",      "#7F77DD"),
        ("non_executive", "Неисполнительные", "#378ADD"),
        ("executive",     "Исполнительные",   "#EF9F27"),
        ("state_rep",     "Гос. представители", "#A855F7"),
        ("other",         "Прочие",            "#94A3B8"),
    ]
    for key, label, color in role_palette:
        cnt = by_role.get(key, 0)
        diversity_split.append(DiversityStat(
            label=label,
            color=color,
            pct=round(100 * cnt / total_members, 1),
            count=cnt,
        ))

    # Available years + sectors
    yrs_q = await db.execute(
        select(GovernanceData.year).distinct().where(GovernanceData.year.is_not(None)),
    )
    yrs = sorted({r[0] for r in yrs_q.all() if r[0]}, reverse=True)

    secs_q = await db.execute(
        select(Sector.code, func.count(Company.id))
        .join(Sector, Sector.id == Company.sector_id)
        .where(Company.sector_id.is_not(None))
        .group_by(Sector.code),
    )
    sectors = [{"code": r[0], "count": r[1]} for r in secs_q.all()]

    return GovernanceOverviewResponse(
        year=year,
        sector_code=sector_code,
        kpis=kpis,
        diversity_split=diversity_split,
        rankings=rankings,
        available_years=yrs,
        sectors=sectors,
        generated_at=datetime.now(timezone.utc),
    )


# =====================================================================
# Company detail
# =====================================================================

@router.get("/companies/{company_id}", response_model=GovernanceCompanyDetail)
async def get_company_detail(
    company_id: UUID,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "governance.view"):
        raise HTTPException(status_code=403, detail="Forbidden")

    co_q = select(Company).options(selectinload(Company.sector)).where(Company.id == company_id)
    co_q = await _allowed_company_filter(db, user, co_q, Company.id)
    co = (await db.execute(co_q)).scalar_one_or_none()
    if not co:
        raise HTTPException(status_code=404, detail="Company not found")

    # Available years
    yrs_q = await db.execute(
        select(GovernanceData.year).where(GovernanceData.company_id == company_id)
        .order_by(desc(GovernanceData.year)),
    )
    available_years = [r[0] for r in yrs_q.all() if r[0]]

    target_year = year or (available_years[0] if available_years else datetime.now().year)

    d_q = await db.execute(
        select(GovernanceData).where(
            and_(GovernanceData.company_id == company_id, GovernanceData.year == target_year),
        ),
    )
    d = d_q.scalar_one_or_none()

    # Board members (active only)
    bm_q = await db.execute(
        select(BoardMember).where(BoardMember.company_id == company_id)
        .order_by(asc(BoardMember.role_type), asc(BoardMember.full_name)),
    )
    members = [_member_to_brief(m) for m in bm_q.scalars().all()]

    indep_pct = wm_pct = fo_pct = score = None
    if d:
        bs = d.board_size or 0
        if bs:
            if d.independent_directors_count is not None:
                indep_pct = round(100 * d.independent_directors_count / bs, 1)
            if d.women_directors_count is not None:
                wm_pct = round(100 * d.women_directors_count / bs, 1)
            if d.foreign_directors_count is not None:
                fo_pct = round(100 * d.foreign_directors_count / bs, 1)
        score = _governance_score(d)

    return GovernanceCompanyDetail(
        company_id=co.id,
        company_code=co.code,
        company_name=co.name_ru,
        sector_code=(co.sector.code if co.sector else None),
        year=target_year,
        data=_data_to_brief(d) if d else None,
        board_members=members,
        score=score,
        independent_pct=indep_pct,
        women_pct=wm_pct,
        foreign_pct=fo_pct,
        available_years=available_years,
    )


# =====================================================================
# GovernanceData upsert
# =====================================================================

@router.put("/data", response_model=GovernanceDataBrief)
async def upsert_governance_data(
    payload: GovernanceDataEdit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upsert governance_data for company × year (one row per pair)."""
    if not await has_effective_permission(db, user, "governance.edit"):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if payload.company_id not in allowed:
            raise HTTPException(status_code=403, detail="No access to this company")

    # Sanity: independent + women + foreign count <= board_size
    if payload.board_size is not None:
        for fld in ("independent_directors_count", "women_directors_count", "foreign_directors_count"):
            v = getattr(payload, fld)
            if v is not None and v > payload.board_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"{fld} ({v}) cannot exceed board_size ({payload.board_size})",
                )

    # ── Moderation gate ────────────────────────────────────────
    from fastapi.responses import JSONResponse
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="governance", action="upsert_data",
        entity_id=None,
        entity_label=f"Governance data {payload.year}",
        company_id=payload.company_id, sector_id=None, year=payload.year,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Сохранение governance-данных за {payload.year}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    res = await db.execute(
        select(GovernanceData).where(and_(
            GovernanceData.company_id == payload.company_id,
            GovernanceData.year == payload.year,
        )),
    )
    d = res.scalar_one_or_none()
    if d is None:
        d = GovernanceData(
            company_id=payload.company_id,
            year=payload.year,
        )
        db.add(d)

    d.board_size = payload.board_size
    d.independent_directors_count = payload.independent_directors_count
    d.women_directors_count = payload.women_directors_count
    d.foreign_directors_count = payload.foreign_directors_count
    d.avg_age = payload.avg_age
    d.has_audit_committee = payload.has_audit_committee
    d.has_remuneration_committee = payload.has_remuneration_committee
    d.has_nomination_committee = payload.has_nomination_committee
    d.has_strategy_committee = payload.has_strategy_committee
    d.meetings_per_year = payload.meetings_per_year
    d.avg_attendance_pct = payload.avg_attendance_pct
    if payload.payload is not None: d.payload = payload.payload
    d.notes = payload.notes

    await db.commit()
    await db.refresh(d)
    return _data_to_brief(d)


# =====================================================================
# Board members
# =====================================================================

@router.get("/companies/{company_id}/members", response_model=List[BoardMemberBrief])
async def list_board_members(
    company_id: UUID,
    include_past: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "governance.view"):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if company_id not in allowed:
            raise HTTPException(status_code=404, detail="Company not found")

    q = select(BoardMember).where(BoardMember.company_id == company_id)
    if not include_past:
        today = datetime.now(timezone.utc).date()
        q = q.where(
            (BoardMember.term_end_date == None) | (BoardMember.term_end_date >= today),  # noqa: E711
        )
    q = q.order_by(asc(BoardMember.role_type), asc(BoardMember.full_name))

    rows = (await db.execute(q)).scalars().all()
    return [_member_to_brief(m) for m in rows]


@router.post("/member", response_model=BoardMemberBrief, status_code=http_status.HTTP_201_CREATED)
async def create_board_member(
    payload: BoardMemberCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "governance.edit"):
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
        module="governance", action="create_member",
        entity_id=None, entity_label=f"Член СД: {payload.full_name}",
        company_id=payload.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Добавление члена СД: {payload.full_name} ({payload.role_type})",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    m = BoardMember(
        company_id=payload.company_id,
        full_name=payload.full_name,
        position=payload.position,
        role_type=payload.role_type,
        is_independent=payload.is_independent,
        is_woman=payload.is_woman,
        is_foreign=payload.is_foreign,
        appointed_date=payload.appointed_date,
        term_end_date=payload.term_end_date,
        bio=payload.bio,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _member_to_brief(m)


@router.patch("/member/{member_id}", response_model=BoardMemberBrief)
async def update_board_member(
    member_id: UUID,
    payload: BoardMemberUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "governance.edit"):
        raise HTTPException(status_code=403, detail="Forbidden")

    res = await db.execute(select(BoardMember).where(BoardMember.id == member_id))
    m = res.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if m.company_id not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")

    # ── Moderation gate ────────────────────────────────────────
    from fastapi.responses import JSONResponse
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="governance", action="update_member",
        entity_id=str(member_id), entity_label=f"Член СД: {m.full_name}",
        company_id=m.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json", exclude_unset=True),
        diff_summary=f"Обновление члена СД '{m.full_name}'",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    for field in (
        "full_name", "position", "role_type",
        "is_independent", "is_woman", "is_foreign",
        "appointed_date", "term_end_date", "bio",
    ):
        v = getattr(payload, field)
        if v is not None:
            setattr(m, field, v)

    await db.commit()
    await db.refresh(m)
    return _member_to_brief(m)


@router.delete("/member/{member_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_board_member(
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "governance.edit"):
        raise HTTPException(status_code=403, detail="Forbidden")

    res = await db.execute(select(BoardMember).where(BoardMember.id == member_id))
    m = res.scalar_one_or_none()
    if not m: return  # idempotent

    if not has_unrestricted_view(user):
        allowed = await allowed_company_ids(db, user)
        if m.company_id not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")

    await db.delete(m)
    await db.commit()
