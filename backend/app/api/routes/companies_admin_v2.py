"""Companies & Sectors admin v2 — thin HTTP layer (refactored 2026-05-25).

Granular admin endpoints under /companies-admin/v2 and /sectors-admin/v2.
All write ops require companies.edit / sectors.edit (owner + admin auto-bypass).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.core.security import require_permission
from app.dependencies.companies_admin_v2 import CompaniesAdminV2ServiceDep
from app.models.user import User
from app.schemas.companies_admin import (
    CompanyAdminCreate, CompanyAdminRead, CompanyAdminUpdate,
    CompanyTreeNode,
    CompanyYearOverrideRead, CompanyYearOverridesBulk,
    SectorAdminCreate, SectorAdminRead, SectorAdminUpdate,
)


router = APIRouter(tags=["companies-admin"])

companies_router = APIRouter(prefix="/companies-admin/v2", tags=["companies-admin"])
sectors_router = APIRouter(prefix="/sectors-admin/v2", tags=["sectors-admin"])


# ─── companies CRUD ──────────────────────────────────────────────

@companies_router.get("/list", response_model=list[CompanyAdminRead])
async def list_companies_admin(
    service: CompaniesAdminV2ServiceDep,
    sector: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    only_active: bool = Query(False),
    search: Optional[str] = Query(None),
    _u: User = Depends(require_permission("companies.view")),
):
    return await service.list_companies(
        sector=sector, status_filter=status_filter,
        only_active=only_active, search=search,
    )


@companies_router.get("/{code}", response_model=CompanyAdminRead)
async def get_company_admin(
    code: str,
    service: CompaniesAdminV2ServiceDep,
    _u: User = Depends(require_permission("companies.view")),
):
    return await service.get_company(code)


@companies_router.post("/create", response_model=CompanyAdminRead,
                       status_code=status.HTTP_201_CREATED)
async def create_company_admin(
    body: CompanyAdminCreate,
    service: CompaniesAdminV2ServiceDep,
    _actor: User = Depends(require_permission("companies.create")),
):
    return await service.create_company(body)


@companies_router.patch("/{code}", response_model=CompanyAdminRead)
async def update_company_admin(
    code: str,
    body: CompanyAdminUpdate,
    service: CompaniesAdminV2ServiceDep,
    _actor: User = Depends(require_permission("companies.edit")),
):
    return await service.update_company(code, body)


@companies_router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company_admin(
    code: str,
    service: CompaniesAdminV2ServiceDep,
    _actor: User = Depends(require_permission("companies.delete")),
):
    await service.delete_company(code)


# ─── year overrides ──────────────────────────────────────────────

@companies_router.get("/{code}/year-overrides",
                      response_model=list[CompanyYearOverrideRead])
async def list_year_overrides(
    code: str,
    service: CompaniesAdminV2ServiceDep,
    _u: User = Depends(require_permission("companies.view")),
):
    return await service.list_year_overrides(code)


@companies_router.put("/{code}/year-overrides",
                      response_model=list[CompanyYearOverrideRead])
async def replace_year_overrides(
    code: str,
    body: CompanyYearOverridesBulk,
    service: CompaniesAdminV2ServiceDep,
    _actor: User = Depends(require_permission("companies.edit")),
):
    return await service.replace_year_overrides(code, body)


# ─── hierarchy tree ──────────────────────────────────────────────

@companies_router.get("/tree/hierarchy", response_model=list[CompanyTreeNode])
async def hierarchy_tree(
    service: CompaniesAdminV2ServiceDep,
    _u: User = Depends(require_permission("companies.view")),
):
    return await service.hierarchy_tree()


# ─── sectors CRUD ────────────────────────────────────────────────

@sectors_router.get("/list", response_model=list[SectorAdminRead])
async def list_sectors_admin(
    service: CompaniesAdminV2ServiceDep,
    _u: User = Depends(require_permission("sectors.view")),
):
    return await service.list_sectors()


@sectors_router.post("/create", response_model=SectorAdminRead,
                     status_code=status.HTTP_201_CREATED)
async def create_sector_admin(
    body: SectorAdminCreate,
    service: CompaniesAdminV2ServiceDep,
    _actor: User = Depends(require_permission("sectors.create")),
):
    return await service.create_sector(body)


@sectors_router.patch("/{code}", response_model=SectorAdminRead)
async def update_sector_admin(
    code: str,
    body: SectorAdminUpdate,
    service: CompaniesAdminV2ServiceDep,
    _actor: User = Depends(require_permission("sectors.edit")),
):
    return await service.update_sector(code, body)


@sectors_router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sector_admin(
    code: str,
    service: CompaniesAdminV2ServiceDep,
    _actor: User = Depends(require_permission("sectors.delete")),
):
    await service.delete_sector(code)


# ─── Aggregate (for ROUTER_MODULES loader) ───────────────────────

router.include_router(companies_router)
router.include_router(sectors_router)
