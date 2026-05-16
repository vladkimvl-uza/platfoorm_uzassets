"""External APIs routes (Pack 12.2)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.models.external_api import ExternalApi
from app.models.user import User
from app.schemas.external_api import (
    ExtCatalogSummary, ExtEndpoint,
    ExternalApiCreate, ExternalApiListResponse, ExternalApiRead, ExternalApiUpdate,
    OpenApiUploadRequest, OpenApiUploadResponse,
)
from app.services import external_api_service as svc


router = APIRouter(prefix="/external-apis", tags=["external-apis"])


def _row_to_read(row: ExternalApi) -> ExternalApiRead:
    """Convert ORM row to schema, populating computed has_openapi_spec."""
    out = ExternalApiRead.model_validate(row)
    out.has_openapi_spec = row.openapi_spec is not None
    return out


# ════════════════════════════════════════════════════════════
#   CRUD
# ════════════════════════════════════════════════════════════

@router.get("", response_model=ExternalApiListResponse)
async def list_external_apis(
    q:           Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("external_apis.read")),
):
    base = select(ExternalApi)
    if q:
        like = f"%{q.lower()}%"
        base = base.where(or_(
            ExternalApi.slug.ilike(like),
            ExternalApi.name.ilike(like),
            ExternalApi.description.ilike(like),
        ))
    if status_filter:
        base = base.where(ExternalApi.status == status_filter)
    rows = (await db.execute(base.order_by(ExternalApi.name))).scalars().all()
    return ExternalApiListResponse(items=[_row_to_read(r) for r in rows], total=len(rows))


@router.post("", response_model=ExternalApiRead, status_code=status.HTTP_201_CREATED)
async def create_external_api(
    body: ExternalApiCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("external_apis.manage")),
):
    exists = (await db.execute(
        select(ExternalApi).where(ExternalApi.slug == body.slug),
    )).scalars().first()
    if exists:
        raise HTTPException(409, f"Slug already taken: {body.slug}")

    now = datetime.now(timezone.utc)
    row = ExternalApi(
        created_at=now, updated_at=now,
        slug=body.slug, name=body.name, description=body.description,
        base_url=str(body.base_url),
        documentation_url=str(body.documentation_url) if body.documentation_url else None,
        health_check_url=str(body.health_check_url) if body.health_check_url else None,
        status=body.status,
        owner_id=body.owner_id, created_by_id=user.id,
        contacts=[c.model_dump() for c in body.contacts] if body.contacts else None,
        tags=body.tags,
        environment_kind=body.environment_kind,
        auth_kind=body.auth_kind, auth_details=body.auth_details,
        notes=body.notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _row_to_read(row)


@router.get("/{api_id}", response_model=ExternalApiRead)
async def get_external_api(
    api_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("external_apis.read")),
):
    row = await db.get(ExternalApi, api_id)
    if not row:
        raise HTTPException(404, "External API not found")
    return _row_to_read(row)


@router.patch("/{api_id}", response_model=ExternalApiRead)
async def update_external_api(
    api_id: UUID,
    body: ExternalApiUpdate,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("external_apis.manage")),
):
    row = await db.get(ExternalApi, api_id)
    if not row:
        raise HTTPException(404, "External API not found")

    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k == "contacts" and v is not None:
            row.contacts = [c.model_dump() if hasattr(c, "model_dump") else c for c in v]
        elif k in ("base_url", "documentation_url", "health_check_url") and v is not None:
            setattr(row, k, str(v))
        else:
            setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return _row_to_read(row)


@router.delete("/{api_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_external_api(
    api_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("external_apis.manage")),
):
    row = await db.get(ExternalApi, api_id)
    if not row:
        raise HTTPException(404, "External API not found")
    await db.delete(row)
    await db.commit()


# ════════════════════════════════════════════════════════════
#   OpenAPI spec upload + catalog
# ════════════════════════════════════════════════════════════

@router.post("/{api_id}/openapi", response_model=OpenApiUploadResponse)
async def upload_openapi(
    api_id: UUID,
    body: OpenApiUploadRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("external_apis.manage")),
):
    row = await db.get(ExternalApi, api_id)
    if not row:
        raise HTTPException(404, "External API not found")

    ok, err = svc.validate_openapi(body.spec)
    if not ok:
        raise HTTPException(400, f"Invalid OpenAPI spec: {err}")

    row.openapi_spec = body.spec
    row.openapi_spec_version = svc.extract_version(body.spec)
    row.openapi_uploaded_at = datetime.now(timezone.utc)
    row.openapi_uploaded_by_id = user.id
    row.endpoint_count = svc.count_endpoints(body.spec)
    row.updated_at = row.openapi_uploaded_at
    await db.commit()
    await db.refresh(row)

    return OpenApiUploadResponse(
        version=row.openapi_spec_version,
        endpoint_count=row.endpoint_count,
        title=svc.extract_title(body.spec),
        uploaded_at=row.openapi_uploaded_at,
    )


@router.delete("/{api_id}/openapi", status_code=status.HTTP_204_NO_CONTENT)
async def remove_openapi(
    api_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("external_apis.manage")),
):
    row = await db.get(ExternalApi, api_id)
    if not row:
        raise HTTPException(404, "External API not found")
    row.openapi_spec = None
    row.openapi_spec_version = None
    row.openapi_uploaded_at = None
    row.openapi_uploaded_by_id = None
    row.endpoint_count = 0
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/{api_id}/catalog", response_model=ExtCatalogSummary)
async def get_catalog(
    api_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("external_apis.read")),
):
    row = await db.get(ExternalApi, api_id)
    if not row:
        raise HTTPException(404, "External API not found")
    if not row.openapi_spec:
        raise HTTPException(404, "No OpenAPI spec uploaded for this API")

    spec = row.openapi_spec
    endpoints = [ExtEndpoint(**e) for e in svc.list_endpoints(spec)]
    info = spec.get("info") or {}

    return ExtCatalogSummary(
        api_id=row.id,
        title=info.get("title", row.name),
        version=info.get("version", "0.0.0"),
        description=info.get("description"),
        servers=svc.extract_servers(spec),
        total_endpoints=len(endpoints),
        endpoints=endpoints,
    )


@router.get("/{api_id}/openapi.json")
async def download_openapi(
    api_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("external_apis.read")),
):
    """Return the raw uploaded OpenAPI spec for download / external tooling."""
    from fastapi.responses import JSONResponse
    row = await db.get(ExternalApi, api_id)
    if not row:
        raise HTTPException(404, "External API not found")
    if not row.openapi_spec:
        raise HTTPException(404, "No OpenAPI spec uploaded")
    return JSONResponse(
        row.openapi_spec,
        headers={"Content-Disposition": f'attachment; filename="{row.slug}.openapi.json"'},
    )
