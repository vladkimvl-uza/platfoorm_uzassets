"""Companies API — list, detail, financials, governance.

All endpoints require authentication. Permission `companies.view_all` lets the
user see every company; `companies.view` restricts to the user's organization.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit_chain import append_audit_entry
from app.core.security import get_current_user, _has_permission
from app.database import get_db
from app.models.announcement import Announcement
from app.models.company import Company, Sector
from app.models.financial import FinancialReport, FinancialLine
from app.models.governance import GovernanceData
from app.models.user import User
from app.schemas.company import (
    CompanyDetail, CompanyListItem, CompanyListResponse,
    DashboardStats, FinancialLineBrief, FinancialReportBrief,
    GovernanceBrief, SectorBrief,
    SectorCreatePayload, SectorUpdatePayload,
    CompanyCreatePayload, CompanyUpdatePayload,
)

router = APIRouter(prefix="/companies", tags=["companies"])


# =====================================================================
# GET /companies — list with filters
# =====================================================================

@router.get("", response_model=CompanyListResponse)
async def list_companies(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    sector: Optional[str] = Query(None, description="Sector code filter, e.g. 'mining'"),
    search: Optional[str] = Query(None, description="Search term — matches code, name_ru, name_short"),
    active_only: bool = Query(True),
    custom_only: Optional[bool] = Query(None, description="Filter by is_custom flag (true/false/null=all)"),
    sort_by: str = Query("sort_order", regex="^(sort_order|code|name_ru|governance_score|latest_revenue)$"),
    sort_dir: str = Query("asc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CompanyListResponse:
    """List companies with sector + search + sort.

    The user must have either `companies.view` or `companies.view_all`.
    Without `view_all`, results are filtered to the user's organization.
    """
    # --- Permission check ---
    can_view_all = _has_permission(user, "companies.view_all")
    can_view_own = _has_permission(user, "companies.view")
    if not (can_view_all or can_view_own):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No permission to view companies")

    # --- Build query ---
    q = select(Company).options(selectinload(Company.sector))

    if active_only:
        q = q.where(Company.is_active.is_(True))

    if custom_only is not None:
        q = q.where(Company.is_custom.is_(custom_only))

    if sector:
        q = q.join(Sector, Company.sector_id == Sector.id).where(Sector.code == sector.lower())

    if search:
        s = f"%{search.strip().lower()}%"
        q = q.where(or_(
            func.lower(Company.code).like(s),
            func.lower(Company.name_ru).like(s),
            func.lower(Company.name_short).like(s),
        ))

    # --- Access scope filter ---
    # Three levels of company visibility:
    #   1. Owner OR companies.view_all permission → see ALL companies
    #   2. allowed_companies set on user (UUID list in JSONB) → see ONLY those
    #   3. organization_id set → see ONLY that single company (legacy)
    #   4. Otherwise → empty result (no implicit access)
    if not (can_view_all or user.is_owner):
        # Build a list of company IDs / codes the user is permitted to see
        allowed_ids: list = list(user.allowed_companies or [])
        if user.organization_id is not None and str(user.organization_id) not in [str(x) for x in allowed_ids]:
            allowed_ids.append(str(user.organization_id))

        if allowed_ids:
            # allowed_companies may be either UUIDs or codes — handle both
            id_filters = []
            for x in allowed_ids:
                xs = str(x)
                # Heuristic: UUID has dashes, code is short alphanumeric
                if len(xs) == 36 and xs.count("-") == 4:
                    id_filters.append(Company.id == xs)
                else:
                    id_filters.append(func.lower(Company.code) == xs.lower())
            q = q.where(or_(*id_filters))
        else:
            # User has NO scoped access — return empty
            q = q.where(Company.id == None)  # noqa: E711  intentionally falsy

    # Total count BEFORE limit/offset
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # --- Sort ---
    sort_col_map = {
        "sort_order": Company.sort_order,
        "code":       Company.code,
        "name_ru":    Company.name_ru,
    }
    sort_col = sort_col_map.get(sort_by, Company.sort_order)
    q = q.order_by(asc(sort_col) if sort_dir == "asc" else desc(sort_col), Company.code)
    q = q.limit(limit).offset(offset)

    rows = (await db.execute(q)).scalars().all()
    company_ids = [c.id for c in rows]

    # --- Aggregate enrichments in 2 batched queries (avoid N+1) ---

    # Latest financial report per company
    latest_fin: dict[str, tuple[int, Optional[float]]] = {}
    if company_ids:
        # Find the most recent year per company that has a REVENUE line
        fin_q = (
            select(
                FinancialReport.company_id,
                FinancialReport.year,
                FinancialLine.value,
            )
            .join(FinancialLine, FinancialLine.report_id == FinancialReport.id)
            .where(
                FinancialReport.company_id.in_(company_ids),
                FinancialLine.line_code == "REVENUE",
            )
            .order_by(FinancialReport.company_id, desc(FinancialReport.year))
        )
        fin_rows = (await db.execute(fin_q)).all()
        for cid, year, value in fin_rows:
            if cid not in latest_fin:  # first row per company is most recent
                latest_fin[str(cid)] = (year, value)

    # Latest governance score per company
    gov_score: dict[str, int] = {}
    if company_ids:
        gov_q = (
            select(GovernanceData.company_id, GovernanceData.year, GovernanceData.payload)
            .where(GovernanceData.company_id.in_(company_ids))
            .order_by(GovernanceData.company_id, desc(GovernanceData.year))
        )
        gov_rows = (await db.execute(gov_q)).all()
        for cid, year, payload in gov_rows:
            cid_str = str(cid)
            if cid_str not in gov_score and isinstance(payload, dict):
                score = payload.get("score")
                if isinstance(score, (int, float)):
                    gov_score[cid_str] = int(score)

    # --- Build response items ---
    items: List[CompanyListItem] = []
    for c in rows:
        fin = latest_fin.get(str(c.id))
        items.append(CompanyListItem(
            id=c.id,
            code=c.code,
            name_ru=c.name_ru,
            name_short=c.name_short,
            sector_code=c.sector.code if c.sector else None,
            sector_name=c.sector.name_ru if c.sector else None,
            sector_color=c.sector.color_hex if c.sector else None,
            is_active=c.is_active,
            is_custom=c.is_custom,
            governance_score=gov_score.get(str(c.id)),
            latest_revenue=fin[1] if fin else None,
            latest_revenue_year=fin[0] if fin else None,
            has_financials=str(c.id) in latest_fin,
            has_governance=str(c.id) in gov_score,
        ))

    # Apply post-aggregation sort if requested
    if sort_by == "governance_score":
        items.sort(key=lambda x: (x.governance_score or -1), reverse=(sort_dir == "desc"))
    elif sort_by == "latest_revenue":
        items.sort(key=lambda x: (x.latest_revenue or 0), reverse=(sort_dir == "desc"))

    # Sectors list for filter dropdown
    sec_q = select(Sector).order_by(Sector.sort_order)
    sectors = [SectorBrief.model_validate(s) for s in (await db.execute(sec_q)).scalars().all()]

    return CompanyListResponse(items=items, total=total, sectors=sectors)


# =====================================================================
# GET /companies/{code} — single company detail
# =====================================================================

@router.get("/{code}", response_model=CompanyDetail)
async def get_company(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanyDetail:
    if not (_has_permission(user, "companies.view") or _has_permission(user, "companies.view_all")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No permission to view companies")

    q = select(Company).where(Company.code == code.lower()).options(selectinload(Company.sector))
    company = (await db.execute(q)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Company with code '{code}' not found")

    # Access-scope check: org users see only their allowed companies
    if not _user_can_see_company(user, company):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this company")

    return CompanyDetail(
        id=company.id, code=company.code,
        name_ru=company.name_ru, name_uz=company.name_uz, name_en=company.name_en,
        name_short=company.name_short, legal_form=company.legal_form, inn=company.inn,
        sector=SectorBrief.model_validate(company.sector) if company.sector else None,
        description=company.description, logo_url=company.logo_url, website=company.website,
        address=company.address, ceo_name=company.ceo_name,
        employees_count=company.employees_count, founded_year=company.founded_year,
        is_active=company.is_active, is_custom=company.is_custom, extra=company.extra,
        created_at=company.created_at, updated_at=company.updated_at,
    )


# =====================================================================
# GET /companies/{code}/financials — all financial reports for one company
# =====================================================================

@router.get("/{code}/financials", response_model=List[FinancialReportBrief])
async def get_company_financials(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[FinancialReportBrief]:
    if not _has_permission(user, "financials.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: financials.view")

    company_q = select(Company).where(Company.code == code.lower())
    company = (await db.execute(company_q)).scalar_one_or_none()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Company '{code}' not found")

    if not _user_can_see_company(user, company):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this company")

    company_id = company.id

    reports_q = (
        select(FinancialReport)
        .where(FinancialReport.company_id == company_id)
        .options(selectinload(FinancialReport.lines))
        .order_by(desc(FinancialReport.year), FinancialReport.quarter.asc().nulls_first())
    )
    reports = (await db.execute(reports_q)).scalars().all()

    return [
        FinancialReportBrief(
            year=r.year, quarter=r.quarter,
            standard=r.standard, report_type=r.report_type,
            currency=r.currency, unit_scale=r.unit_scale,
            source=r.source, is_audited=r.is_audited, notes=r.notes,
            lines=[
                FinancialLineBrief(
                    line_code=l.line_code,
                    line_name=l.line_name,
                    value=l.value,
                    sort_order=l.sort_order,
                ) for l in sorted(r.lines, key=lambda x: x.sort_order)
            ],
        )
        for r in reports
    ]


# =====================================================================
# GET /companies/{code}/governance — board / governance history
# =====================================================================

@router.get("/{code}/governance", response_model=List[GovernanceBrief])
async def get_company_governance(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[GovernanceBrief]:
    if not _has_permission(user, "governance.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: governance.view")

    company_q = select(Company).where(Company.code == code.lower())
    company = (await db.execute(company_q)).scalar_one_or_none()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Company '{code}' not found")

    if not _user_can_see_company(user, company):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this company")

    company_id = company.id

    q = (select(GovernanceData)
         .where(GovernanceData.company_id == company_id)
         .order_by(desc(GovernanceData.year)))
    rows = (await db.execute(q)).scalars().all()

    return [
        GovernanceBrief(
            year=r.year,
            board_size=r.board_size,
            independent_directors_count=r.independent_directors_count,
            women_directors_count=r.women_directors_count,
            foreign_directors_count=r.foreign_directors_count,
            avg_age=r.avg_age,
            has_audit_committee=r.has_audit_committee,
            has_strategy_committee=r.has_strategy_committee,
            meetings_per_year=r.meetings_per_year,
            avg_attendance_pct=r.avg_attendance_pct,
            score=r.payload.get("score") if isinstance(r.payload, dict) else None,
            payload=r.payload,
        )
        for r in rows
    ]


# =====================================================================
# DELETE company (soft-deactivate by default; cascade=true wipes everything)
# =====================================================================

@router.delete("/{code}", status_code=204)
async def delete_company(
    code: str,
    cascade: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a company.

    Default (cascade=false): SOFT-deactivate — sets is_active=false. Company
    keeps its historical data (financial reports, ratings, tasks) but is
    hidden from active lists.

    cascade=true: HARD delete — removes the company AND all its dependent
    data via the FK ON DELETE CASCADE constraints. This is irreversible.
    Requires the user to be owner OR have admin.users permission.

    The default soft-delete is what most users want — it's reversible
    (just set is_active=true again to bring the company back). Cascade
    delete is for true cleanup of test/duplicate companies.
    """
    if not (user.is_owner or _has_permission(user, "companies.delete") or _has_permission(user, "admin.users")):
        raise HTTPException(403, "Permission required: companies.delete or admin.users")

    res = await db.execute(select(Company).where(func.lower(Company.code) == code.lower()))
    co = res.scalar_one_or_none()
    if not co:
        raise HTTPException(404, f"Company '{code}' not found")

    # Per-company scope check
    if not _user_can_see_company(user, co):
        raise HTTPException(403, "No access to this company")

    if cascade:
        if not user.is_owner:
            raise HTTPException(
                403,
                "Cascade delete requires owner status. "
                "Use soft-delete (?cascade=false) for permanent deactivation.",
            )
        co_label = f"{co.code} ({co.name_short or co.name_ru})"
        await db.delete(co)  # FK ON DELETE CASCADE handles dependents
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="companies.delete_cascade",
            entity_type="company", entity_id=str(co.id),
            notes=f"HARD DELETE {co_label} + all dependents",
        )
        await db.commit()
    else:
        co.is_active = False
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="companies.deactivate",
            entity_type="company", entity_id=str(co.id),
            notes=f"soft-deactivated {co.code}",
        )
        await db.commit()


@router.delete("/{code}/financials", status_code=204)
async def delete_company_financials(
    code: str,
    standard: Optional[str] = None,   # IFRS | NSBU | None=both
    year: Optional[int] = None,        # specific year or None=all
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Wipe all financial reports + lines for a company, optionally
    filtered by standard (IFRS/NSBU) and/or year. Useful before re-import.
    """
    if not (user.is_owner or _has_permission(user, "financials.edit")):
        raise HTTPException(403, "Permission required: financials.edit")

    res = await db.execute(select(Company).where(func.lower(Company.code) == code.lower()))
    co = res.scalar_one_or_none()
    if not co:
        raise HTTPException(404, f"Company '{code}' not found")

    # Per-company scope check
    if not _user_can_see_company(user, co):
        raise HTTPException(403, "No access to this company")

    q = select(FinancialReport).where(FinancialReport.company_id == co.id)
    if standard:
        q = q.where(FinancialReport.standard == standard)
    if year:
        q = q.where(FinancialReport.year == year)

    reports = list((await db.execute(q)).scalars().all())
    deleted = len(reports)
    for r in reports:
        await db.delete(r)  # cascades to financial_lines
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="financials.delete_bulk",
        entity_type="company", entity_id=str(co.id),
        notes=f"company={co.code}, standard={standard or 'all'}, year={year or 'all'}, deleted={deleted}",
    )
    await db.commit()


# =====================================================================
# CREATE / UPDATE company
# =====================================================================


async def _resolve_sector(db: AsyncSession, sector_code: Optional[str]) -> Optional[Sector]:
    if not sector_code:
        return None
    s_res = await db.execute(select(Sector).where(Sector.code == sector_code))
    sector = s_res.scalar_one_or_none()
    if not sector:
        raise HTTPException(400, f"Unknown sector code: {sector_code}")
    return sector


def _user_can_see_company(user: User, co: Company) -> bool:
    """Per-company visibility check.

    Owners and `companies.view_all` see everything. Otherwise the company
    must appear in the user's allowed_companies list (by id or by code)
    or match their organization_id.

    Сравнение нормализованное с обеих сторон (strip + lower), чтобы UUID,
    записанные admin'ом в верхнем регистре в JSONB, не выпадали.
    """
    if user.is_owner:
        return True
    if _has_permission(user, "companies.view_all"):
        return True

    allowed = list(user.allowed_companies or [])
    co_id_str = str(co.id).strip().lower()
    co_code = (co.code or "").strip().lower()

    for x in allowed:
        xs = str(x).strip().lower()
        if not xs:
            continue
        if xs == co_id_str or xs == co_code:
            return True

    if user.organization_id is not None and str(user.organization_id).strip().lower() == co_id_str:
        return True

    return False


@router.post("", response_model=CompanyDetail, status_code=201)
async def create_company(
    payload: CompanyCreatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (user.is_owner or _has_permission(user, "companies.create") or _has_permission(user, "admin.users")):
        raise HTTPException(403, "Permission required: companies.create")

    # Scoped users (organization role with allowed_companies set) cannot create
    # new companies — they don't have visibility to a freshly-created company
    # anyway, and this prevents them from polluting the canonical company list.
    if (user.allowed_companies or user.organization_id) and not user.is_owner \
            and not _has_permission(user, "companies.view_all"):
        raise HTTPException(
            403,
            "Scoped users cannot create new companies. Contact an administrator.",
        )

    # Conflict check
    dup = await db.execute(select(Company).where(func.lower(Company.code) == payload.code.lower()))
    if dup.scalar_one_or_none():
        raise HTTPException(409, f"Company with code '{payload.code}' already exists")

    sector = await _resolve_sector(db, payload.sector_code)

    # Defensive: trim + fall back to name_ru if name_short missing/empty
    name_ru_clean = (payload.name_ru or "").strip()
    if not name_ru_clean:
        raise HTTPException(422, "name_ru is required")
    name_short_clean = (payload.name_short or "").strip() or name_ru_clean[:128]

    co = Company(
        code=payload.code.lower(),
        name_ru=name_ru_clean,
        name_short=name_short_clean,
        name_uz=payload.name_uz, name_en=payload.name_en,
        sector_id=sector.id if sector else None,
        legal_form=payload.legal_form, inn=payload.inn,
        description=payload.description, website=payload.website,
        address=payload.address, ceo_name=payload.ceo_name,
        employees_count=payload.employees_count, founded_year=payload.founded_year,
        is_active=True, is_custom=True,
        sort_order=10000,  # Custom companies sort to the end
    )
    db.add(co)
    await db.commit()
    await db.refresh(co)

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="companies.create",
        entity_type="company", entity_id=str(co.id),
        notes=f"code={co.code}, name_ru={co.name_ru!r}",
    )
    await db.commit()

    # Re-fetch with sector eager-loaded for the response model
    return await get_company(co.code, db, user)


@router.patch("/{code}", response_model=CompanyDetail)
async def update_company(
    code: str,
    payload: CompanyUpdatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (user.is_owner or _has_permission(user, "companies.edit") or _has_permission(user, "admin.users")):
        raise HTTPException(403, "Permission required: companies.edit")

    res = await db.execute(select(Company).where(func.lower(Company.code) == code.lower()))
    co = res.scalar_one_or_none()
    if not co:
        raise HTTPException(404, f"Company '{code}' not found")

    # Per-company scope check — scoped users can edit only allowed companies
    if not _user_can_see_company(user, co):
        raise HTTPException(403, "No access to this company")

    changes: list[str] = []

    # Defensive: name_short and name_ru are core display fields. Reject empty
    # strings (after trim) — would orphan the company display in lists.
    if payload.name_ru is not None:
        nru = payload.name_ru.strip()
        if not nru:
            raise HTTPException(422, "name_ru cannot be empty")
        payload.name_ru = nru
    if payload.name_short is not None:
        ns = payload.name_short.strip()
        if not ns:
            # Empty string → fall back to current name_ru (or current name_short)
            ns = (payload.name_ru or co.name_ru or co.name_short or co.code)[:128]
        payload.name_short = ns

    # Direct field updates (only those that are not None in the payload)
    field_map = {
        "name_ru": payload.name_ru, "name_short": payload.name_short,
        "name_uz": payload.name_uz, "name_en": payload.name_en,
        "legal_form": payload.legal_form, "inn": payload.inn,
        "description": payload.description, "website": payload.website,
        "address": payload.address, "ceo_name": payload.ceo_name,
        "employees_count": payload.employees_count, "founded_year": payload.founded_year,
        "is_active": payload.is_active, "sort_order": payload.sort_order,
    }
    for field, value in field_map.items():
        if value is None:
            continue
        old = getattr(co, field)
        if old != value:
            setattr(co, field, value)
            changes.append(f"{field}: {old!r} → {value!r}")

    # Sector change goes via code → id resolution
    if payload.sector_code is not None:
        sector = await _resolve_sector(db, payload.sector_code) if payload.sector_code else None
        new_sector_id = sector.id if sector else None
        if co.sector_id != new_sector_id:
            co.sector_id = new_sector_id
            changes.append(f"sector_code: → {payload.sector_code!r}")

    await db.commit()

    if changes:
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="companies.update",
            entity_type="company", entity_id=str(co.id),
            notes=", ".join(changes)[:500],
        )
        await db.commit()

    return await get_company(co.code, db, user)


# =====================================================================
# SECTORS CRUD
# =====================================================================

@router.get("/sectors/list", response_model=List[SectorBrief])
async def list_sectors(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    include_counts: bool = False,
):
    """List all sectors. Available to anyone with `companies.view` (most users).
    Pass include_counts=true to get per-sector company counts."""
    if not _has_permission(user, "companies.view") and not _has_permission(user, "sectors.view") \
            and not _has_permission(user, "companies.view_all") and not user.is_owner:
        raise HTTPException(403, "Permission required: companies.view or sectors.view")

    if include_counts:
        q = (
            select(Sector, func.count(Company.id).label("cnt"))
            .outerjoin(Company, (Company.sector_id == Sector.id) & (Company.is_active.is_(True)))
            .group_by(Sector.id)
            .order_by(Sector.sort_order)
        )
        rows = (await db.execute(q)).all()
        return [
            SectorBrief(
                id=r.Sector.id, code=r.Sector.code,
                name_ru=r.Sector.name_ru, name_uz=r.Sector.name_uz, name_en=r.Sector.name_en,
                color_hex=r.Sector.color_hex, sort_order=r.Sector.sort_order,
                company_count=r.cnt or 0,
            )
            for r in rows
        ]
    else:
        q = await db.execute(select(Sector).order_by(Sector.sort_order))
        return [SectorBrief.model_validate(s) for s in q.scalars().all()]


@router.post("/sectors", response_model=SectorBrief, status_code=201)
async def create_sector(
    payload: SectorCreatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (user.is_owner or _has_permission(user, "sectors.create") or _has_permission(user, "admin.users")):
        raise HTTPException(403, "Permission required: sectors.create")

    dup = await db.execute(select(Sector).where(Sector.code == payload.code))
    if dup.scalar_one_or_none():
        raise HTTPException(409, f"Sector '{payload.code}' already exists")

    s = Sector(
        code=payload.code,
        name_ru=payload.name_ru, name_uz=payload.name_uz, name_en=payload.name_en,
        color_hex=payload.color_hex, sort_order=payload.sort_order,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="sectors.create",
        entity_type="sector", entity_id=str(s.id),
        notes=f"code={s.code}, name_ru={s.name_ru!r}",
    )
    await db.commit()
    return SectorBrief.model_validate(s)


@router.patch("/sectors/{code}", response_model=SectorBrief)
async def update_sector(
    code: str,
    payload: SectorUpdatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (user.is_owner or _has_permission(user, "sectors.edit") or _has_permission(user, "admin.users")):
        raise HTTPException(403, "Permission required: sectors.edit")

    res = await db.execute(select(Sector).where(Sector.code == code))
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(404, f"Sector '{code}' not found")

    changes: list[str] = []
    for field in ("name_ru", "name_uz", "name_en", "color_hex", "sort_order"):
        v = getattr(payload, field)
        if v is None:
            continue
        old = getattr(s, field)
        if old != v:
            setattr(s, field, v)
            changes.append(f"{field}: {old!r}→{v!r}")

    await db.commit()
    if changes:
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="sectors.update",
            entity_type="sector", entity_id=str(s.id),
            notes=f"sector={code}, " + ", ".join(changes)[:480],
        )
        await db.commit()
    return SectorBrief.model_validate(s)


@router.delete("/sectors/{code}", status_code=204)
async def delete_sector(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a sector. Fails if any active companies still belong to it
    — repoint them to a different sector first."""
    if not (user.is_owner or _has_permission(user, "sectors.delete") or _has_permission(user, "admin.users")):
        raise HTTPException(403, "Permission required: sectors.delete")

    res = await db.execute(select(Sector).where(Sector.code == code))
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(404, f"Sector '{code}' not found")

    # Check for dependent active companies
    dep_q = await db.execute(
        select(func.count()).select_from(Company)
        .where(Company.sector_id == s.id, Company.is_active.is_(True))
    )
    dep_count = dep_q.scalar_one() or 0
    if dep_count > 0:
        raise HTTPException(
            409,
            f"Sector '{code}' is in use by {dep_count} active company(ies). "
            "Repoint them to a different sector first."
        )

    await db.delete(s)
    await db.commit()
    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="sectors.delete",
        entity_type="sector", entity_id=str(s.id),
        notes=f"deleted sector code={code}",
    )
    await db.commit()
