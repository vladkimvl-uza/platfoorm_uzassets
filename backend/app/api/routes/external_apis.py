"""External APIs API — thin HTTP layer (refactored 2026-05-25)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from app.core.security import require_permission
from app.dependencies.external_apis import ExternalApisServiceDep
from app.models.user import User
from app.schemas.external_api import (
    ExtCatalogSummary,
    ExternalApiCreate,
    ExternalApiListResponse,
    ExternalApiRead,
    ExternalApiUpdate,
    OpenApiUploadRequest,
    OpenApiUploadResponse,
)

router = APIRouter(prefix="/external-apis", tags=["external-apis"])


# ─── CRUD ─────────────────────────────────────────────────────────

@router.get("", response_model=ExternalApiListResponse)
async def list_external_apis(
    service: ExternalApisServiceDep,
    q: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    _u: User = Depends(require_permission("external_apis.read")),
):
    return await service.list_apis(q=q, status_filter=status_filter)


@router.post("", response_model=ExternalApiRead, status_code=status.HTTP_201_CREATED)
async def create_external_api(
    body: ExternalApiCreate,
    service: ExternalApisServiceDep,
    user: User = Depends(require_permission("external_apis.manage")),
):
    return await service.create_api(body, created_by_id=user.id)


@router.get("/{api_id}", response_model=ExternalApiRead)
async def get_external_api(
    api_id: UUID,
    service: ExternalApisServiceDep,
    _u: User = Depends(require_permission("external_apis.read")),
):
    return await service.get_api(api_id)


@router.patch("/{api_id}", response_model=ExternalApiRead)
async def update_external_api(
    api_id: UUID,
    body: ExternalApiUpdate,
    service: ExternalApisServiceDep,
    _u: User = Depends(require_permission("external_apis.manage")),
):
    return await service.update_api(api_id, body)


@router.delete("/{api_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_external_api(
    api_id: UUID,
    service: ExternalApisServiceDep,
    _u: User = Depends(require_permission("external_apis.manage")),
):
    await service.delete_api(api_id)


# ─── OpenAPI spec upload + catalog ────────────────────────────────

@router.post("/{api_id}/openapi", response_model=OpenApiUploadResponse)
async def upload_openapi(
    api_id: UUID,
    body: OpenApiUploadRequest,
    service: ExternalApisServiceDep,
    user: User = Depends(require_permission("external_apis.manage")),
):
    return await service.upload_openapi(api_id, body, uploaded_by_id=user.id)


@router.delete("/{api_id}/openapi", status_code=status.HTTP_204_NO_CONTENT)
async def remove_openapi(
    api_id: UUID,
    service: ExternalApisServiceDep,
    _u: User = Depends(require_permission("external_apis.manage")),
):
    await service.remove_openapi(api_id)


@router.get("/{api_id}/catalog", response_model=ExtCatalogSummary)
async def get_catalog(
    api_id: UUID,
    service: ExternalApisServiceDep,
    _u: User = Depends(require_permission("external_apis.read")),
):
    return await service.get_catalog(api_id)


@router.get("/{api_id}/openapi.json")
async def download_openapi(
    api_id: UUID,
    service: ExternalApisServiceDep,
    _u: User = Depends(require_permission("external_apis.read")),
):
    spec, slug = await service.get_raw_spec(api_id)
    return JSONResponse(
        spec,
        headers={"Content-Disposition": f'attachment; filename="{slug}.openapi.json"'},
    )
