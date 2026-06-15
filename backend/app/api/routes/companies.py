"""Companies + Sectors API — thin HTTP layer (refactored 2026-05-25).

Audit-chain writes stay in route file (post-commit side-effects requiring
the actor's email/IP context).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.audit_chain import append_audit_entry
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.dependencies.companies import CompaniesServiceDep, SectorsServiceDep
from app.models.user import User
from app.schemas.company import (
    CompanyCreatePayload,
    CompanyDetail,
    CompanyListResponse,
    CompanyUpdatePayload,
    FinancialReportBrief,
    GovernanceBrief,
    SectorBrief,
    SectorCreatePayload,
    SectorUpdatePayload,
)

router = APIRouter(prefix="/companies", tags=["companies"])


# ─── helpers ──────────────────────────────────────────────────────

async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    """None = unrestricted (owner or companies.view_all)."""
    if user.is_owner or await has_effective_permission(db, user, "companies.view_all"):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


async def _can_view(db: AsyncSession, user: User) -> bool:
    return (await has_effective_permission(db, user, "companies.view")) or \
           (await has_effective_permission(db, user, "companies.view_all"))


# ─── Companies ────────────────────────────────────────────────────

@router.get("", response_model=CompanyListResponse)
async def list_companies(
    service: CompaniesServiceDep,
    sector: Optional[str] = Query(None, description="Sector code filter"),
    search: Optional[str] = Query(None, description="Search across code/name_ru/name_short"),
    active_only: bool = Query(True),
    custom_only: Optional[bool] = Query(None),
    sort_by: str = Query("sort_order",
                         regex="^(sort_order|code|name_ru|governance_score|latest_revenue)$"),
    sort_dir: str = Query("asc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    hidden_for_year: Optional[int] = Query(None, description="Исключить компании, скрытые в этом году"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanyListResponse:
    """List companies, scoped to caller's company-access set (RBAC).

    Supports filter by sector, search across code/name fields, and sort by
    governance_score / latest_revenue / sort_order. Returns 403 if the caller
    lacks `companies.view` and has no per-company scope grant."""
    if not await _can_view(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No permission to view companies")
    return await service.list_companies(
        active_only=active_only, custom_only=custom_only,
        sector_code=sector, search=search,
        scope_company_ids=await _scope(db, user),
        sort_by=sort_by, sort_dir=sort_dir,
        limit=limit, offset=offset,
        hidden_for_year=hidden_for_year,
    )


@router.get("/{code}", response_model=CompanyDetail)
async def get_company(
    code: str,
    service: CompaniesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanyDetail:
    """Fetch full company profile by code (e.g. 'navoiyazot'). RBAC-scoped.

    Returns 404 if the company doesn't exist OR isn't in the caller's scope."""
    if not await _can_view(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No permission to view companies")
    return await service.get_company_by_code(code, scope_company_ids=await _scope(db, user))


_EMP_PALETTE = ["#7F77DD", "#1D9E75", "#378ADD", "#EF9F27", "#D4537E", "#0E7490", "#9333EA"]


def _emp_initials(full_name: Optional[str], email: str) -> str:
    if full_name and full_name.strip():
        parts = full_name.strip().split()
        return "".join(p[0].upper() for p in parts[:2]) or "?"
    local = (email or "").split("@", 1)[0]
    parts = local.replace(".", " ").replace("_", " ").split()
    return ("".join(p[0].upper() for p in parts[:2]) or local[:2].upper()) if local else "?"


def _emp_accent(seed: str) -> str:
    h = 0
    for ch in seed:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _EMP_PALETTE[h % len(_EMP_PALETTE)]


@router.get("/{code}/employees")
async def get_company_employees(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Сотрудники компании на платформе (привязка через User.organization_id).

    Возвращает идентичность + роль/отдел/должность + последнюю активность для
    премиум-раздела «Сотрудники» в карточке компании. RBAC-scoped по company.view."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import selectinload

    from app.models.audit import AuditLog
    from app.models.company import Company

    if not await _can_view(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No permission to view companies")

    company = (await db.execute(
        select(Company).where(Company.code == code)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Компания не найдена")

    # Scope: если у юзера ограниченный доступ — компания должна быть в нём
    scope = await _scope(db, user)
    if scope is not None and company.id not in scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Компания не найдена")

    rows = (await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.organization_id == company.id)
        .order_by(User.is_active.desc(), User.full_name)
    )).scalars().all()

    employees = []
    for u in rows:
        role_label = None
        if getattr(u, "roles", None):
            r0 = u.roles[0]
            role_label = getattr(r0, "name_ru", None) or getattr(r0, "code", None)
        elif getattr(u, "is_owner", False):
            role_label = "Владелец"

        last_dt = (await db.execute(
            select(func.max(AuditLog.created_at)).where(AuditLog.actor_id == u.id)
        )).scalar()

        email = u.email or ""
        employees.append({
            "id": str(u.id),
            "full_name": u.full_name or email.split("@", 1)[0] or "—",
            "email": email,
            "initials": _emp_initials(u.full_name, email),
            "accent": _emp_accent(str(u.id)),
            "role": role_label,
            "is_owner": bool(getattr(u, "is_owner", False)),
            "department": getattr(u, "department", None),
            "job_title": getattr(u, "job_title", None),
            "avatar_url": getattr(u, "avatar_url", None),
            "is_active": bool(getattr(u, "is_active", True)),
            "last_active": last_dt.isoformat() if last_dt else None,
        })

    return {
        "company_code": company.code,
        "company_name": company.name_ru,
        "total": len(employees),
        "employees": employees,
    }


@router.get("/{code}/financials", response_model=list[FinancialReportBrief])
async def get_company_financials(
    code: str,
    service: CompaniesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "financials.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: financials.view")
    return await service.get_company_financials(code, scope_company_ids=await _scope(db, user))


@router.get("/{code}/governance", response_model=list[GovernanceBrief])
async def get_company_governance(
    code: str,
    service: CompaniesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "governance.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: governance.view")
    return await service.get_company_governance(code, scope_company_ids=await _scope(db, user))


# ─── Mutations ────────────────────────────────────────────────────

@router.post("", response_model=CompanyDetail, status_code=201)
async def create_company(
    payload: CompanyCreatePayload,
    service: CompaniesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new company. Requires `companies.create` or `admin.users`.

    Scoped (non-owner) users cannot create companies — only org-wide editors
    or the platform owner can. Auto-creates the company-library row + audit log."""
    if not (user.is_owner
            or await has_effective_permission(db, user, "companies.create")
            or await has_effective_permission(db, user, "admin.users")):
        raise HTTPException(403, "Permission required: companies.create")

    # scoped users cannot create new companies — КРОМЕ обладателей
    # `companies.create` (напр. роль organization), которым это явно разрешено
    # (по запросу: создание компаний из BP/KPI). Company-scope продолжает
    # ограничивать, какие компании пользователь видит, но не мешает завести новую.
    if not user.is_owner \
            and not await has_effective_permission(db, user, "companies.view_all") \
            and not await has_effective_permission(db, user, "companies.create"):
        scope = await allowed_company_ids(db, user)
        if scope is not None:
            raise HTTPException(
                403,
                "Scoped users cannot create new companies. Contact an administrator.",
            )

    detail, grp_code = await service.create_company(payload)

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="companies.create",
        entity_type="company", entity_id=str(detail.id),
        notes=f"code={detail.code}, name_ru={detail.name_ru!r}, group={grp_code}",
    )
    await db.commit()
    return detail


@router.patch("/{code}", response_model=CompanyDetail)
async def update_company(
    code: str,
    payload: CompanyUpdatePayload,
    service: CompaniesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update company fields. Partial — only non-null payload fields are applied.

    Requires `companies.edit` or `admin.users`. Writes an audit entry summarising
    the field-level diff."""
    if not (user.is_owner
            or await has_effective_permission(db, user, "companies.edit")
            or await has_effective_permission(db, user, "admin.users")):
        raise HTTPException(403, "Permission required: companies.edit")

    detail, changes = await service.update_company(
        code, payload, scope_company_ids=await _scope(db, user),
    )
    if changes:
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="companies.update",
            entity_type="company", entity_id=str(detail.id),
            notes=", ".join(changes)[:500],
        )
        await db.commit()
    return detail


@router.delete("/{code}", status_code=204)
async def delete_company(
    code: str,
    service: CompaniesServiceDep,
    cascade: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-deactivate by default; cascade=true wipes everything (owner only)."""
    if not (user.is_owner
            or await has_effective_permission(db, user, "companies.delete")
            or await has_effective_permission(db, user, "admin.users")):
        raise HTTPException(403, "Permission required: companies.delete or admin.users")

    co, label = await service.delete_company(
        code, cascade=cascade, actor_is_owner=user.is_owner,
        scope_company_ids=await _scope(db, user),
    )
    if cascade:
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="companies.delete_cascade",
            entity_type="company", entity_id=str(co.id),
            notes=f"HARD DELETE {label} + all dependents",
        )
    else:
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="companies.deactivate",
            entity_type="company", entity_id=str(co.id),
            notes=f"soft-deactivated {label}",
        )
    await db.commit()


@router.delete("/{code}/financials", status_code=204)
async def delete_company_financials(
    code: str,
    service: CompaniesServiceDep,
    standard: Optional[str] = None,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Wipe financial reports for a company, optionally filtered by standard/year."""
    if not (user.is_owner or await has_effective_permission(db, user, "financials.edit")):
        raise HTTPException(403, "Permission required: financials.edit")

    co_id, deleted = await service.delete_company_financials(
        code, standard=standard, year=year,
        scope_company_ids=await _scope(db, user),
    )
    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="financials.delete_bulk",
        entity_type="company", entity_id=str(co_id),
        notes=f"company={code}, standard={standard or 'all'}, year={year or 'all'}, deleted={deleted}",
    )
    await db.commit()


# ─── Sectors ──────────────────────────────────────────────────────

@router.get("/sectors/list", response_model=list[SectorBrief])
async def list_sectors(
    service: SectorsServiceDep,
    include_counts: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (await has_effective_permission(db, user, "companies.view")
            or await has_effective_permission(db, user, "sectors.view")
            or await has_effective_permission(db, user, "companies.view_all")
            or user.is_owner):
        raise HTTPException(403, "Permission required: companies.view or sectors.view")
    return await service.list_sectors(include_counts=include_counts)


@router.post("/sectors", response_model=SectorBrief, status_code=201)
async def create_sector(
    payload: SectorCreatePayload,
    service: SectorsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (user.is_owner
            or await has_effective_permission(db, user, "sectors.create")
            or await has_effective_permission(db, user, "admin.users")):
        raise HTTPException(403, "Permission required: sectors.create")

    s = await service.create_sector(payload)
    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="sectors.create",
        entity_type="sector", entity_id=str(s.id),
        notes=f"code={s.code}, name_ru={s.name_ru!r}",
    )
    await db.commit()
    return s


@router.patch("/sectors/{code}", response_model=SectorBrief)
async def update_sector(
    code: str,
    payload: SectorUpdatePayload,
    service: SectorsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (user.is_owner
            or await has_effective_permission(db, user, "sectors.edit")
            or await has_effective_permission(db, user, "admin.users")):
        raise HTTPException(403, "Permission required: sectors.edit")

    s, changes = await service.update_sector(code, payload)
    if changes:
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="sectors.update",
            entity_type="sector", entity_id=str(s.id),
            notes=f"sector={code}, " + ", ".join(changes)[:480],
        )
        await db.commit()
    return s


@router.delete("/sectors/{code}", status_code=204)
async def delete_sector(
    code: str,
    service: SectorsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (user.is_owner
            or await has_effective_permission(db, user, "sectors.delete")
            or await has_effective_permission(db, user, "admin.users")):
        raise HTTPException(403, "Permission required: sectors.delete")

    sid = await service.delete_sector(code)
    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="sectors.delete",
        entity_type="sector", entity_id=str(sid),
        notes=f"deleted sector code={code}",
    )
    await db.commit()
