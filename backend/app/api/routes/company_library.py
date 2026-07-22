"""Company Library (MDM) — thin HTTP layer (refactored 2026-05-25).

Routes (URLs preserved):
  GET    /companies/library                            paginated list + columns
  GET    /companies/library/{id}                       full detail
  PATCH  /companies/library/{id}/fields/{code}         write single field
  GET    /companies/library/{id}/activity              recent audit entries
  GET    /field-definitions                            schema of all fields
  POST   /field-definitions                            create custom field
  PATCH  /field-definitions/{code}                     update non-system
  DELETE /field-definitions/{code}                     delete custom
  GET    /library-views                                my saved views
  POST   /library-views                                save new view
  PATCH  /library-views/{id}                           update
  DELETE /library-views/{id}                           delete
  GET    /library-tabs                                 list all tabs
  POST   /library-tabs                                 create custom tab
  PATCH  /library-tabs/{code}                          update non-system
  DELETE /library-tabs/{code}                          delete custom

WebSocket (separate ws_router, mounted in main.py):
  WS     /ws/companies                                 global field-update broadcast
  WS     /ws/companies/{id}                            per-company subscription
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import ensure_company_access
from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.dependencies.company_library import CompanyLibraryServiceDep
from app.models.user import User
from app.schemas.company_library import (
    FieldDefinitionCreate,
    FieldDefinitionRead,
    FieldDefinitionUpdate,
    FieldWriteRequest,
    FieldWriteResponse,
    LibraryActivityEntry,
    LibraryCompanyDetail,
    LibraryListResponse,
    LibraryTabCreate,
    LibraryTabRead,
    LibraryTabUpdate,
    LibraryViewCreate,
    LibraryViewRead,
    LibraryViewUpdate,
)
from app.services.sync_broadcaster import GLOBAL_SCOPE, broadcaster

log = logging.getLogger(__name__)
router = APIRouter(tags=["company-library"])


# ─── /companies/library — index + detail ─────────────────────────

@router.get("/library/companies", response_model=LibraryListResponse)
async def list_library(
    service: CompanyLibraryServiceDep,
    sector: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=128),
    view_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
) -> LibraryListResponse:
    return await service.list_library(
        sector=sector, search=search, view_id=view_id,
        limit=limit, offset=offset, user_id=user.id,
    )


@router.get("/library/companies/{company_id}", response_model=LibraryCompanyDetail)
async def get_library_detail(
    company_id: UUID,
    service: CompanyLibraryServiceDep,
    user: User = Depends(get_current_user),
) -> LibraryCompanyDetail:
    return await service.get_library_detail(company_id)


@router.patch(
    "/library/companies/{company_id}/fields/{field_code}",
    response_model=FieldWriteResponse,
)
async def write_library_field(
    company_id: UUID,
    field_code: str,
    body: FieldWriteRequest,
    request: Request,
    service: CompanyLibraryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # P0 (аудит /ratings): право проверяется ПОСЛОЙНО в сервисе (ratings-поля →
    # ratings.edit + модерация как канон-путь /ratings; прочие поля → companies.edit),
    # раньше endpoint-wide companies.edit пускал рейтинги мимо ratings.edit/модерации.
    # api_key — чтобы сервис сохранил scope-ceiling API-ключа (как require_permission).
    await ensure_company_access(db, user, company_id)
    result = await service.write_field(
        company_id, field_code, body, user=user, db=db,
        api_key=getattr(request.state, "api_key", None),
    )
    if getattr(result, "queued", False):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "queued": True, "submission_id": str(result.submission_id),
                "status": result.status,
                "message": "Изменение отправлено на модерацию",
            },
        )
    return result


@router.get(
    "/library/companies/{company_id}/activity",
    response_model=list[LibraryActivityEntry],
)
async def get_library_activity(
    company_id: UUID,
    service: CompanyLibraryServiceDep,
    limit: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> list[LibraryActivityEntry]:
    return await service.get_activity(company_id, limit=limit)


# ─── /field-definitions — CRUD ───────────────────────────────────

@router.get("/field-definitions", response_model=list[FieldDefinitionRead])
async def list_field_definitions(
    service: CompanyLibraryServiceDep,
    sector: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
) -> list[FieldDefinitionRead]:
    return await service.list_field_definitions(sector=sector, scope_type=scope_type)


@router.post(
    "/field-definitions", response_model=FieldDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_field_definition(
    body: FieldDefinitionCreate,
    service: CompanyLibraryServiceDep,
    user: User = Depends(require_permission("library.fields.manage")),
) -> FieldDefinitionRead:
    return await service.create_field_definition(body, actor_id=user.id)


@router.patch("/field-definitions/{code}", response_model=FieldDefinitionRead)
async def update_field_definition(
    code: str,
    body: FieldDefinitionUpdate,
    service: CompanyLibraryServiceDep,
    user: User = Depends(require_permission("library.fields.manage")),
) -> FieldDefinitionRead:
    return await service.update_field_definition(code, body)


@router.delete(
    "/field-definitions/{code}",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
)
async def delete_field_definition(
    code: str,
    service: CompanyLibraryServiceDep,
    user: User = Depends(require_permission("library.fields.manage")),
):
    await service.delete_field_definition(code)
    return Response(status_code=204)


# ─── /library-views — CRUD (per-user) ────────────────────────────

@router.get("/library-views", response_model=list[LibraryViewRead])
async def list_my_views(
    service: CompanyLibraryServiceDep,
    user: User = Depends(get_current_user),
) -> list[LibraryViewRead]:
    return await service.list_my_views(user.id)


@router.post(
    "/library-views", response_model=LibraryViewRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_view(
    body: LibraryViewCreate,
    service: CompanyLibraryServiceDep,
    user: User = Depends(get_current_user),
) -> LibraryViewRead:
    return await service.create_view(body, user_id=user.id)


@router.patch("/library-views/{view_id}", response_model=LibraryViewRead)
async def update_view(
    view_id: UUID,
    body: LibraryViewUpdate,
    service: CompanyLibraryServiceDep,
    user: User = Depends(get_current_user),
) -> LibraryViewRead:
    return await service.update_view(view_id, body, user_id=user.id)


@router.delete(
    "/library-views/{view_id}",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
)
async def delete_view(
    view_id: UUID,
    service: CompanyLibraryServiceDep,
    user: User = Depends(get_current_user),
):
    await service.delete_view(view_id, user_id=user.id)
    return Response(status_code=204)


# ─── /library-tabs — CRUD (global) ───────────────────────────────

@router.get("/library-tabs", response_model=list[LibraryTabRead])
async def list_tabs(
    service: CompanyLibraryServiceDep,
    user: User = Depends(get_current_user),
) -> list[LibraryTabRead]:
    return await service.list_tabs()


@router.post(
    "/library-tabs", response_model=LibraryTabRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_tab(
    body: LibraryTabCreate,
    service: CompanyLibraryServiceDep,
    user: User = Depends(require_permission("library.tabs.manage")),
) -> LibraryTabRead:
    return await service.create_tab(body, actor_id=user.id)


@router.patch("/library-tabs/{code}", response_model=LibraryTabRead)
async def update_tab(
    code: str,
    body: LibraryTabUpdate,
    service: CompanyLibraryServiceDep,
    user: User = Depends(require_permission("library.tabs.manage")),
) -> LibraryTabRead:
    return await service.update_tab(code, body)


@router.delete(
    "/library-tabs/{code}",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
)
async def delete_tab(
    code: str,
    service: CompanyLibraryServiceDep,
    user: User = Depends(require_permission("library.tabs.manage")),
):
    await service.delete_tab(code)
    return Response(status_code=204)


# ─── WebSocket endpoints ─────────────────────────────────────────
# Separate router so the WS endpoints don't appear in the OpenAPI HTTP table.

ws_router = APIRouter()


@ws_router.websocket("/ws/companies")
async def ws_companies_global(ws: WebSocket) -> None:
    """Subscribe to ALL company field updates."""
    await broadcaster.connect(ws, GLOBAL_SCOPE)
    try:
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await broadcaster.disconnect(ws, GLOBAL_SCOPE)


@ws_router.websocket("/ws/companies/{company_id}")
async def ws_company_scoped(ws: WebSocket, company_id: str) -> None:
    """Subscribe to updates for one company only."""
    await broadcaster.connect(ws, company_id)
    try:
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await broadcaster.disconnect(ws, company_id)
