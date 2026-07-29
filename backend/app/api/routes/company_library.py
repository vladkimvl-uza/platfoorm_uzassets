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

from app.core import jwt as app_jwt
from app.core.access import allowed_company_ids, ensure_company_access
from app.core.i18n import current_locale, tr
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LibraryListResponse:
    # Per-company scope: библиотека несёт фин/рейтинг/kpi-колонки всех компаний —
    # company-scoped юзер не должен видеть чужие (тот же scope, что и WS-стрим).
    allowed = await allowed_company_ids(db, user)
    return await service.list_library(
        sector=sector, search=search, view_id=view_id,
        limit=limit, offset=offset, user_id=user.id, allowed_ids=allowed,
    )


@router.get("/library/companies/{company_id}", response_model=LibraryCompanyDetail)
async def get_library_detail(
    company_id: UUID,
    service: CompanyLibraryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LibraryCompanyDetail:
    await ensure_company_access(db, user, company_id)
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
                "message": tr("Изменение отправлено на модерацию", current_locale()),
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LibraryActivityEntry]:
    await ensure_company_access(db, user, company_id)
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
#
# These streams carry live financial/rating field values, so the socket must be
# authenticated. Browsers can't set an Authorization header on a WS handshake, so
# the client first calls POST /companies/ws-ticket (with its normal bearer token)
# to mint a 30-sec ws_ticket, then offers it as the 2nd Sec-WebSocket-Protocol
# value — keeping it out of the URL/logs (mirrors the /notifications/ws pattern).

ws_router = APIRouter()

_WS_TICKET_PROTO = "uza-ws-ticket-v1"


@router.post("/companies/ws-ticket")
async def post_company_ws_ticket(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mint a 30-sec ticket for the company-library sync WebSockets.

    Embeds the user's per-company scope (`scp`) so the stream delivers ONLY the
    companies they may see — a company-scoped user must not receive other
    companies' live financial/rating field updates over the global socket.
    scope None (unrestricted) → no `scp` claim; a list (incl. empty) → restricted.
    """
    scope = await allowed_company_ids(db, user)
    extra = None if scope is None else {"scp": [str(x) for x in scope]}
    return {
        "ticket": app_jwt.create_ws_ticket(subject=str(user.id), extra_claims=extra),
        "expires_in": 30,
    }


async def _ws_ticket_payload(ws: WebSocket) -> Optional[dict]:
    """Validate the ws_ticket from Sec-WebSocket-Protocol and return its decoded
    payload (carrying the `scp` scope claim). On failure close 4401 → None. Never raises."""
    protos = ws.scope.get("subprotocols") or []
    ticket = protos[1] if len(protos) >= 2 and protos[0] == _WS_TICKET_PROTO else None
    if ticket:
        try:
            return app_jwt.decode_token(ticket, expected_type="ws_ticket")
        except Exception:
            pass
    try:
        await ws.close(code=4401)
    except Exception:
        pass
    return None


def _scope_from_payload(payload: dict) -> Optional[set[str]]:
    """`scp` absent/None → unrestricted (None); list → allowed company-id set."""
    scp = payload.get("scp")
    return None if scp is None else {str(x) for x in scp}


@ws_router.websocket("/ws/companies")
async def ws_companies_global(ws: WebSocket) -> None:
    """Subscribe to field updates for the companies the user may see (auth required).
    The global stream is filtered per-connection by the ticket's `scp` scope."""
    payload = await _ws_ticket_payload(ws)
    if payload is None:
        return
    allowed = _scope_from_payload(payload)
    await broadcaster.connect(
        ws, GLOBAL_SCOPE, subprotocol=_WS_TICKET_PROTO, allowed_codes=allowed,
    )
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
    """Subscribe to updates for one company only (auth + per-company scope)."""
    payload = await _ws_ticket_payload(ws)
    if payload is None:
        return
    allowed = _scope_from_payload(payload)
    if allowed is not None and company_id not in allowed:
        try:
            await ws.close(code=4403)
        except Exception:
            pass
        return
    await broadcaster.connect(
        ws, company_id, subprotocol=_WS_TICKET_PROTO, allowed_codes=allowed,
    )
    try:
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await broadcaster.disconnect(ws, company_id)
