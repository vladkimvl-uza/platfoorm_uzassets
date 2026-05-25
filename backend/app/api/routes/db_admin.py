"""Database admin console (Pack 149) — thin HTTP shim (refactored 2026-05-25).

Endpoints (prefix /admin/db, всё под is_owner OR is_admin gate):

  GET    /admin/db/schema              — таблицы, колонки, FK, индексы, row counts
  POST   /admin/db/query               — выполнить произвольный SQL
  GET    /admin/db/table/{name}/rows   — пагинированный browser
  PATCH  /admin/db/table/{name}/row    — UPDATE по PK
  DELETE /admin/db/table/{name}/row    — DELETE по PK

Безопасность:
  - is_owner OR is_admin
  - Все операции пишутся в audit_log через append_audit_entry
  - statement_timeout = 30s
  - max 10k строк в результате
  - Подключение через DATABASE_URL_ADMIN (superuser) для DDL
  - Каждый запрос АУДИТИРУЕТСЯ независимо от того, прошёл он или упал
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.dependencies.db_admin import DbAdminServiceDep
from app.models.user import User
from app.services.db_admin_console.service import (
    QueryRequest, QueryResponse, RowMutateRequest,
    SchemaOverview, TableRowsResponse,
)


router = APIRouter(prefix="/admin/db", tags=["db-admin"])


@router.get("/schema", response_model=SchemaOverview)
async def get_schema(
    request: Request,
    service: DbAdminServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SchemaOverview:
    return await service.get_schema(db, current_user, request)


@router.post("/query", response_model=QueryResponse)
async def execute_query(
    body: QueryRequest,
    request: Request,
    service: DbAdminServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    return await service.execute_query(body, db, current_user, request)


@router.get("/table/{name}/rows", response_model=TableRowsResponse)
async def browse_table(
    name: str,
    request: Request,
    service: DbAdminServiceDep,
    limit: int = 50,
    offset: int = 0,
    order_by: Optional[str] = None,
    order_dir: str = "ASC",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRowsResponse:
    return await service.browse_table(
        name, db, current_user, request,
        limit=limit, offset=offset,
        order_by=order_by, order_dir=order_dir,
    )


@router.patch("/table/{name}/row")
async def update_row(
    name: str,
    body: RowMutateRequest,
    request: Request,
    service: DbAdminServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await service.update_row(name, body, db, current_user, request)


@router.delete("/table/{name}/row")
async def delete_row(
    name: str,
    request: Request,
    service: DbAdminServiceDep,
    pk_column: str = "id",
    pk_value: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await service.delete_row(
        name, pk_column, pk_value, db, current_user, request,
    )
