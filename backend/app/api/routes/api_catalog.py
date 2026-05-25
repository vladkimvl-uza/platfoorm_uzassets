"""API Catalog API — thin HTTP layer (refactored 2026-05-25).

Endpoints (URLs preserved):
  GET  /api-catalog/summary                — modules + endpoints + perms
  GET  /api-catalog/openapi.json           — raw FastAPI OpenAPI
  GET  /api-catalog/openapi.enriched.json  — + x-required-permission
  GET  /api-catalog/scopes                 — all permissions grouped
  GET  /api-catalog/postman.json           — Postman v2.1 export
  GET  /api-catalog/by-company/{id}        — per-company endpoint list
  POST /api-catalog/try                    — execute endpoint with caller's JWT
  GET  /api-catalog/status                 — public lightweight status

Service receives the FastAPI app via the request (request.app) since route
introspection is the core data source.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from app.core.security import get_current_user, require_permission
from app.dependencies.api_catalog import ApiCatalogServiceDep
from app.models.user import User
from app.schemas.api_key import (
    CatalogSummary, CompanyCatalogResponse, ScopeListResponse,
    TryRequest, TryResponse,
)


router = APIRouter(prefix="/api-catalog", tags=["api-catalog"])


@router.get("/summary", response_model=CatalogSummary)
async def catalog_summary(
    request: Request,
    service: ApiCatalogServiceDep,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    return service.build_summary(request.app)


@router.get("/openapi.json")
async def openapi_raw(
    request: Request,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    return JSONResponse(request.app.openapi())


@router.get("/openapi.enriched.json")
async def openapi_enriched(
    request: Request,
    service: ApiCatalogServiceDep,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    return JSONResponse(service.build_enriched_openapi(request.app))


@router.get("/scopes", response_model=ScopeListResponse)
async def list_scopes(
    service: ApiCatalogServiceDep,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    return await service.list_scopes()


@router.get("/postman.json")
async def export_postman(
    request: Request,
    service: ApiCatalogServiceDep,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    body, name_slug = service.build_postman_collection(request.app)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name_slug}.postman_collection.json"'},
    )


@router.get("/by-company/{company_id}", response_model=CompanyCatalogResponse)
async def catalog_by_company(
    company_id: UUID,
    request: Request,
    service: ApiCatalogServiceDep,
    tab: Optional[str] = Query(None, description="Filter by tab (financials/kpi/loans/...)"),
    user: User = Depends(get_current_user),
):
    return await service.catalog_by_company(company_id, tab=tab, app=request.app)


@router.post("/try", response_model=TryResponse)
async def try_endpoint(
    body: TryRequest,
    request: Request,
    service: ApiCatalogServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.try_endpoint(
        body, forwarded_auth=request.headers.get("authorization"),
    )


@router.get("/status")
async def catalog_status(
    request: Request,
    service: ApiCatalogServiceDep,
):
    """Public lightweight status — no auth."""
    return service.public_status(request.app)
