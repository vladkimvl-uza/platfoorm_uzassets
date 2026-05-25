"""Use cases for External APIs (3rd-party API catalog + OpenAPI specs).

Delegates OpenAPI parsing to the existing core
`app/services/external_api_service.py` (validate_openapi, extract_version,
count_endpoints, list_endpoints, extract_servers, extract_title).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.external_api import ExternalApi
from app.schemas.external_api import (
    ExtCatalogSummary, ExtEndpoint,
    ExternalApiCreate, ExternalApiListResponse, ExternalApiRead, ExternalApiUpdate,
    OpenApiUploadRequest, OpenApiUploadResponse,
)
from app.services import external_api_service as openapi_svc
from app.uow.ports import UnitOfWorkABC


def _row_to_read(row: ExternalApi) -> ExternalApiRead:
    out = ExternalApiRead.model_validate(row)
    out.has_openapi_spec = row.openapi_spec is not None
    return out


class ExternalApisService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── CRUD ─────────────────────────────────────────────────────

    async def list_apis(
        self,
        *,
        q: Optional[str],
        status_filter: Optional[str],
    ) -> ExternalApiListResponse:
        async with self.uow:
            rows = await self.uow.external_apis.list_apis(
                q=q, status_filter=status_filter,
            )
        return ExternalApiListResponse(
            items=[_row_to_read(r) for r in rows], total=len(rows),
        )

    async def get_api(self, api_id: UUID) -> ExternalApiRead:
        async with self.uow:
            row = await self.uow.external_apis.get(api_id)
            if not row:
                raise HTTPException(404, "External API not found")
            return _row_to_read(row)

    async def create_api(
        self,
        body: ExternalApiCreate,
        *,
        created_by_id: UUID,
    ) -> ExternalApiRead:
        async with self.uow:
            exists = await self.uow.external_apis.get_by_slug(body.slug)
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
                owner_id=body.owner_id, created_by_id=created_by_id,
                contacts=[c.model_dump() for c in body.contacts] if body.contacts else None,
                tags=body.tags,
                environment_kind=body.environment_kind,
                auth_kind=body.auth_kind, auth_details=body.auth_details,
                notes=body.notes,
            )
            self.uow.external_apis.add(row)
            await self.uow.external_apis.flush()
            await self.uow.external_apis.refresh(row)
            return _row_to_read(row)

    async def update_api(
        self,
        api_id: UUID,
        body: ExternalApiUpdate,
    ) -> ExternalApiRead:
        async with self.uow:
            row = await self.uow.external_apis.get(api_id)
            if not row:
                raise HTTPException(404, "External API not found")
            data = body.model_dump(exclude_unset=True)
            for k, v in data.items():
                if k == "contacts" and v is not None:
                    row.contacts = [
                        c.model_dump() if hasattr(c, "model_dump") else c for c in v
                    ]
                elif k in ("base_url", "documentation_url", "health_check_url") and v is not None:
                    setattr(row, k, str(v))
                else:
                    setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
            await self.uow.external_apis.flush()
            await self.uow.external_apis.refresh(row)
            return _row_to_read(row)

    async def delete_api(self, api_id: UUID) -> None:
        async with self.uow:
            row = await self.uow.external_apis.get(api_id)
            if not row:
                raise HTTPException(404, "External API not found")
            await self.uow.external_apis.delete(row)
            await self.uow.external_apis.flush()

    # ─── OpenAPI spec ─────────────────────────────────────────────

    async def upload_openapi(
        self,
        api_id: UUID,
        body: OpenApiUploadRequest,
        *,
        uploaded_by_id: UUID,
    ) -> OpenApiUploadResponse:
        ok, err = openapi_svc.validate_openapi(body.spec)
        if not ok:
            raise HTTPException(400, f"Invalid OpenAPI spec: {err}")

        async with self.uow:
            row = await self.uow.external_apis.get(api_id)
            if not row:
                raise HTTPException(404, "External API not found")
            row.openapi_spec = body.spec
            row.openapi_spec_version = openapi_svc.extract_version(body.spec)
            row.openapi_uploaded_at = datetime.now(timezone.utc)
            row.openapi_uploaded_by_id = uploaded_by_id
            row.endpoint_count = openapi_svc.count_endpoints(body.spec)
            row.updated_at = row.openapi_uploaded_at
            await self.uow.external_apis.flush()
            await self.uow.external_apis.refresh(row)
            uploaded_at = row.openapi_uploaded_at
            version = row.openapi_spec_version
            endpoint_count = row.endpoint_count

        return OpenApiUploadResponse(
            version=version,
            endpoint_count=endpoint_count,
            title=openapi_svc.extract_title(body.spec),
            uploaded_at=uploaded_at,
        )

    async def remove_openapi(self, api_id: UUID) -> None:
        async with self.uow:
            row = await self.uow.external_apis.get(api_id)
            if not row:
                raise HTTPException(404, "External API not found")
            row.openapi_spec = None
            row.openapi_spec_version = None
            row.openapi_uploaded_at = None
            row.openapi_uploaded_by_id = None
            row.endpoint_count = 0
            row.updated_at = datetime.now(timezone.utc)
            await self.uow.external_apis.flush()

    async def get_catalog(self, api_id: UUID) -> ExtCatalogSummary:
        async with self.uow:
            row = await self.uow.external_apis.get(api_id)
            if not row:
                raise HTTPException(404, "External API not found")
            if not row.openapi_spec:
                raise HTTPException(404, "No OpenAPI spec uploaded for this API")
            spec = row.openapi_spec
            row_id = row.id
            row_name = row.name

        endpoints = [ExtEndpoint(**e) for e in openapi_svc.list_endpoints(spec)]
        info = spec.get("info") or {}
        return ExtCatalogSummary(
            api_id=row_id,
            title=info.get("title", row_name),
            version=info.get("version", "0.0.0"),
            description=info.get("description"),
            servers=openapi_svc.extract_servers(spec),
            total_endpoints=len(endpoints),
            endpoints=endpoints,
        )

    async def get_raw_spec(self, api_id: UUID) -> tuple[dict, str]:
        """Return (spec_dict, slug) for download endpoint."""
        async with self.uow:
            row = await self.uow.external_apis.get(api_id)
            if not row:
                raise HTTPException(404, "External API not found")
            if not row.openapi_spec:
                raise HTTPException(404, "No OpenAPI spec uploaded")
            return row.openapi_spec, row.slug
