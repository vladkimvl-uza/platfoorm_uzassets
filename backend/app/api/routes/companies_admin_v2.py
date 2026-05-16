"""Companies & Sectors admin v2 routes (Pack 9.2).

Granular admin: colors, badges, year overrides, hierarchy, tags, currency.
All routes require `companies.edit` (owner + admin auto-bypass).

Mounted under /companies-admin/v2 and /sectors-admin/v2.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.company import Company, CompanyYearOverride, Sector
from app.models.user import User
from app.schemas.companies_admin import (
    Badge,
    CompanyAdminCreate,
    CompanyAdminRead,
    CompanyAdminUpdate,
    CompanyTreeNode,
    CompanyYearOverrideRead,
    CompanyYearOverrideUpsert,
    CompanyYearOverridesBulk,
    SectorAdminCreate,
    SectorAdminRead,
    SectorAdminUpdate,
)


router = APIRouter(tags=["companies-admin"])


# ════════════════════════════════════════════════════════════
#   Helpers
# ════════════════════════════════════════════════════════════

async def _to_admin_read(db: AsyncSession, c: Company) -> CompanyAdminRead:
    sector_code = None
    sector_name = None
    if c.sector_id:
        s = (await db.execute(select(Sector).where(Sector.id == c.sector_id))).scalar_one_or_none()
        if s:
            sector_code = s.code
            sector_name = s.name_ru

    parent_code = None
    if c.parent_id:
        p = (await db.execute(select(Company.code).where(Company.id == c.parent_id))).scalar_one_or_none()
        parent_code = p

    children_count = (await db.execute(
        select(func.count(Company.id)).where(Company.parent_id == c.id),
    )).scalar() or 0
    yo_count = (await db.execute(
        select(func.count(CompanyYearOverride.id)).where(CompanyYearOverride.company_id == c.id),
    )).scalar() or 0

    return CompanyAdminRead(
        id=c.id, code=c.code, name_ru=c.name_ru, name_short=c.name_short,
        name_uz=c.name_uz, name_en=c.name_en, legal_form=c.legal_form, inn=c.inn,
        sector_id=c.sector_id, sector_code=sector_code, sector_name=sector_name,
        description=c.description, logo_url=c.logo_url, website=c.website, address=c.address,
        ceo_name=c.ceo_name, employees_count=c.employees_count, founded_year=c.founded_year,
        is_active=c.is_active, is_custom=c.is_custom, sort_order=c.sort_order,
        primary_color=c.primary_color, secondary_color=c.secondary_color,
        badges=[Badge(**b) for b in (c.badges or [])] if c.badges else None,
        status=c.status,
        is_pinned=c.is_pinned, include_in_rollups=c.include_in_rollups,
        module_flags=c.module_flags,
        parent_id=c.parent_id, parent_code=parent_code,
        portfolio_start_year=c.portfolio_start_year,
        primary_currency=c.primary_currency, fy_start_month=c.fy_start_month,
        track_inflation=c.track_inflation,
        bloomberg_ticker=c.bloomberg_ticker, isin=c.isin, lei=c.lei,
        tags=c.tags, aliases=c.aliases,
        children_count=children_count, year_overrides_count=yo_count,
    )


async def _sector_to_read(db: AsyncSession, s: Sector) -> SectorAdminRead:
    cnt = (await db.execute(
        select(func.count(Company.id)).where(Company.sector_id == s.id),
    )).scalar() or 0
    return SectorAdminRead(
        id=s.id, code=s.code, name_ru=s.name_ru, name_uz=s.name_uz, name_en=s.name_en,
        color_hex=s.color_hex, color_secondary=s.color_secondary, icon_name=s.icon_name,
        short_badge=s.short_badge, sort_order=s.sort_order, aliases=s.aliases,
        companies_count=cnt,
    )


# ════════════════════════════════════════════════════════════
#   Companies CRUD
# ════════════════════════════════════════════════════════════

companies_router = APIRouter(prefix="/companies-admin/v2", tags=["companies-admin"])


@companies_router.get("/list", response_model=list[CompanyAdminRead])
async def list_companies_admin(
    sector: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    only_active: bool = Query(False),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("companies.view")),
):
    q = select(Company)
    conds = []
    if sector:
        s_id = (await db.execute(select(Sector.id).where(Sector.code == sector))).scalar_one_or_none()
        if s_id:
            conds.append(Company.sector_id == s_id)
    if status_filter:
        conds.append(Company.status == status_filter)
    if only_active:
        conds.append(Company.is_active.is_(True))
    if search:
        like = f"%{search.lower()}%"
        conds.append(func.lower(Company.code).like(like) | func.lower(Company.name_ru).like(like) | func.lower(Company.name_short).like(like))
    if conds:
        q = q.where(and_(*conds))
    q = q.order_by(Company.is_pinned.desc(), Company.sort_order, Company.name_ru)
    rows = (await db.execute(q)).scalars().all()
    return [await _to_admin_read(db, c) for c in rows]


@companies_router.get("/{code}", response_model=CompanyAdminRead)
async def get_company_admin(
    code: str,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("companies.view")),
):
    c = (await db.execute(select(Company).where(Company.code == code))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return await _to_admin_read(db, c)


@companies_router.post("/create", response_model=CompanyAdminRead, status_code=status.HTTP_201_CREATED)
async def create_company_admin(
    body: CompanyAdminCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("companies.create")),
):
    existing = (await db.execute(select(Company).where(Company.code == body.code))).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Company '{body.code}' already exists")

    sector_id = None
    if body.sector_code:
        sector_id = (await db.execute(select(Sector.id).where(Sector.code == body.sector_code))).scalar_one_or_none()

    parent_id = None
    if body.parent_code:
        parent_id = (await db.execute(select(Company.id).where(Company.code == body.parent_code))).scalar_one_or_none()

    c = Company(
        code=body.code, name_ru=body.name_ru, name_short=body.name_short,
        name_uz=body.name_uz, name_en=body.name_en,
        sector_id=sector_id, legal_form=body.legal_form, inn=body.inn,
        founded_year=body.founded_year, parent_id=parent_id,
        portfolio_start_year=body.portfolio_start_year,
        status=body.status or "active",
        is_active=True, is_custom=True,
    )
    db.add(c)
    await db.flush()
    await db.commit()
    return await _to_admin_read(db, c)


@companies_router.patch("/{code}", response_model=CompanyAdminRead)
async def update_company_admin(
    code: str,
    body: CompanyAdminUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("companies.edit")),
):
    c = (await db.execute(select(Company).where(Company.code == code))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    data = body.model_dump(exclude_unset=True)

    # Translate sector_code → sector_id
    if "sector_code" in data:
        sc = data.pop("sector_code")
        if sc:
            sid = (await db.execute(select(Sector.id).where(Sector.code == sc))).scalar_one_or_none()
            c.sector_id = sid
        else:
            c.sector_id = None

    # Translate parent_code → parent_id (with cycle check)
    if "parent_code" in data:
        pc = data.pop("parent_code")
        if pc:
            if pc == code:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Company cannot be its own parent")
            pid = (await db.execute(select(Company.id).where(Company.code == pc))).scalar_one_or_none()
            if pid is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Parent company '{pc}' not found")
            # Simple cycle check: walk up from candidate parent, ensure we don't hit `c`
            current = pid
            for _ in range(10):
                row = (await db.execute(select(Company.parent_id).where(Company.id == current))).scalar_one_or_none()
                if row is None:
                    break
                if row == c.id:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hierarchy cycle detected")
                current = row
            c.parent_id = pid
        else:
            c.parent_id = None

    # Badges may arrive as list of Badge objects from pydantic
    if "badges" in data:
        badges = data.pop("badges")
        c.badges = [b.model_dump() if hasattr(b, "model_dump") else b for b in badges] if badges else None

    for k, v in data.items():
        setattr(c, k, v)

    await db.flush()
    await db.commit()
    return await _to_admin_read(db, c)


@companies_router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company_admin(
    code: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("companies.delete")),
):
    c = (await db.execute(select(Company).where(Company.code == code))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    children = (await db.execute(
        select(func.count(Company.id)).where(Company.parent_id == c.id),
    )).scalar() or 0
    if children:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Has {children} subsidiaries — reassign first")
    await db.delete(c)
    await db.commit()


# ────── Year overrides ──────

@companies_router.get("/{code}/year-overrides", response_model=list[CompanyYearOverrideRead])
async def list_year_overrides(
    code: str,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("companies.view")),
):
    c = (await db.execute(select(Company).where(Company.code == code))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    rows = (await db.execute(
        select(CompanyYearOverride).where(CompanyYearOverride.company_id == c.id)
        .order_by(CompanyYearOverride.year),
    )).scalars().all()
    return [
        CompanyYearOverrideRead(
            id=r.id, company_id=r.company_id, year=r.year, is_hidden=r.is_hidden,
            name_override=r.name_override,
            sector_override_id=r.sector_override_id,
            sector_override_code=(
                (await db.execute(select(Sector.code).where(Sector.id == r.sector_override_id))).scalar_one_or_none()
                if r.sector_override_id else None
            ),
            exclusion_reason=r.exclusion_reason, notes=r.notes,
        )
        for r in rows
    ]


@companies_router.put("/{code}/year-overrides", response_model=list[CompanyYearOverrideRead])
async def replace_year_overrides(
    code: str,
    body: CompanyYearOverridesBulk,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("companies.edit")),
):
    c = (await db.execute(select(Company).where(Company.code == code))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    await db.execute(delete(CompanyYearOverride).where(CompanyYearOverride.company_id == c.id))

    for o in body.overrides:
        sector_override_id = None
        if o.sector_override_code:
            sector_override_id = (await db.execute(
                select(Sector.id).where(Sector.code == o.sector_override_code),
            )).scalar_one_or_none()
        db.add(CompanyYearOverride(
            company_id=c.id, year=o.year,
            is_hidden=o.is_hidden, name_override=o.name_override,
            sector_override_id=sector_override_id,
            exclusion_reason=o.exclusion_reason, notes=o.notes,
        ))

    await db.flush()
    await db.commit()
    return await list_year_overrides(code, db, actor)


# ────── Hierarchy tree ──────

@companies_router.get("/tree/hierarchy", response_model=list[CompanyTreeNode])
async def hierarchy_tree(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("companies.view")),
):
    rows = (await db.execute(
        select(Company).order_by(Company.sort_order, Company.name_ru),
    )).scalars().all()

    sector_codes: dict[UUID, str] = {}
    sids = list({c.sector_id for c in rows if c.sector_id})
    if sids:
        for s_id, s_code in (await db.execute(
            select(Sector.id, Sector.code).where(Sector.id.in_(sids)),
        )).all():
            sector_codes[s_id] = s_code

    by_id: dict[UUID, CompanyTreeNode] = {}
    roots: list[CompanyTreeNode] = []

    for c in rows:
        node = CompanyTreeNode(
            id=c.id, code=c.code, name_short=c.name_short, name_ru=c.name_ru,
            sector_code=sector_codes.get(c.sector_id),
            primary_color=c.primary_color,
            badges=[Badge(**b) for b in (c.badges or [])] if c.badges else None,
            status=c.status,
            children=[],
        )
        by_id[c.id] = node

    for c in rows:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id].children.append(node)
        else:
            roots.append(node)

    return roots


# ════════════════════════════════════════════════════════════
#   Sectors CRUD
# ════════════════════════════════════════════════════════════

sectors_router = APIRouter(prefix="/sectors-admin/v2", tags=["sectors-admin"])


@sectors_router.get("/list", response_model=list[SectorAdminRead])
async def list_sectors_admin(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("sectors.view")),
):
    rows = (await db.execute(select(Sector).order_by(Sector.sort_order, Sector.name_ru))).scalars().all()
    return [await _sector_to_read(db, s) for s in rows]


@sectors_router.post("/create", response_model=SectorAdminRead, status_code=status.HTTP_201_CREATED)
async def create_sector_admin(
    body: SectorAdminCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("sectors.create")),
):
    existing = (await db.execute(select(Sector).where(Sector.code == body.code))).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Sector '{body.code}' already exists")
    s = Sector(**body.model_dump())
    db.add(s)
    await db.flush()
    await db.commit()
    return await _sector_to_read(db, s)


@sectors_router.patch("/{code}", response_model=SectorAdminRead)
async def update_sector_admin(
    code: str,
    body: SectorAdminUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("sectors.edit")),
):
    s = (await db.execute(select(Sector).where(Sector.code == code))).scalar_one_or_none()
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sector not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.flush()
    await db.commit()
    return await _sector_to_read(db, s)


@sectors_router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sector_admin(
    code: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("sectors.delete")),
):
    s = (await db.execute(select(Sector).where(Sector.code == code))).scalar_one_or_none()
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sector not found")
    cnt = (await db.execute(
        select(func.count(Company.id)).where(Company.sector_id == s.id),
    )).scalar() or 0
    if cnt:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Has {cnt} companies — reassign first")
    await db.delete(s)
    await db.commit()


# ════════════════════════════════════════════════════════════
#   Aggregate router (for ROUTER_MODULES loader)
# ════════════════════════════════════════════════════════════

router.include_router(companies_router)
router.include_router(sectors_router)
