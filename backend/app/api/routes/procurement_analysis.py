"""Procurement Analysis routes — thin HTTP layer (refactored 2026-05-25).

10-layer template: routes → dependencies → services → uow → repositories.

Все queries — `app/repositories/procurement_repository.py`.
Aggregation pure-functions — `app/services/procurement/_aggregators.py`.
Use-cases — `app/services/procurement/{aggregate,editor,import}_service.py`.

Endpoints (без изменений URL):
  GET    /procurement/aggregate
  POST   /procurement/closures/import-excel
  PUT    /procurement/closures/{closure_id}
  DELETE /procurement/closures
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.access import allowed_company_ids, ensure_company_access, has_unrestricted_view
from app.core.security import has_effective_permission as _has_permission
from app.database import get_db
from app.dependencies.procurement import (
    PaAggregateServiceDep,
    PaEditorServiceDep,
    PaImportServiceDep,
)
from app.models.user import User
from app.schemas.procurement_analysis import ProcurementAggregate
from app.services.procurement.import_service import PaImportSummary

router = APIRouter(prefix="/procurement", tags=["procurement-analysis"])


# ─── DTOs локального уровня ──────────────────────────────────────

class PaClosurePatch(BaseModel):
    """Editable per-closure fields. Numeric fields trigger market_avg + deviation
    recompute for affected product_code."""
    unit_price:    Optional[float] = Field(None, gt=0)
    volume:        Optional[float] = Field(None, gt=0)
    product_code:  Optional[str] = None
    product_name:  Optional[str] = None
    supplier_name: Optional[str] = None
    is_dirty:      Optional[bool] = None
    dirty_reason:  Optional[str] = None
    # Заключение центра экспертизы (по каждой закупке). null = очистить.
    conclusion_text:   Optional[str] = Field(None, max_length=8000)
    conclusion_status: Optional[str] = Field(None, max_length=32)


# ─── GET /aggregate ───────────────────────────────────────────────

@router.get("/aggregate", response_model=ProcurementAggregate)
async def get_aggregate(
    service: PaAggregateServiceDep,
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    company_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns full procurement aggregation (KPIs + rating + products + closures).

    Single-call endpoint for the Procurement Analysis dashboard: per-company
    overpay/savings, product-level price clustering, supplier audit signals,
    and ranked closure list. RBAC-scoped. Filter by year/sector_code/company_id."""
    # H-6: право на модуль (раньше отсутствовало → чувствительная аналитика
    # отдавалась без procurement.view, обход router-гейта прямым API-вызовом).
    if not await _has_permission(db, user, "procurement.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.view required")
    # Scope filter
    if company_id is not None:
        await ensure_company_access(db, user, company_id)

    scope_ids: Optional[list[UUID]] = None
    if not has_unrestricted_view(user):
        scope_ids = list(await allowed_company_ids(db, user))

    return await service.get_aggregate(
        year=year,
        sector_code=sector_code,
        company_id=company_id,
        scope_company_ids=scope_ids,
    )


# ─── POST /closures/import-excel ──────────────────────────────────

@router.post("/closures/import-excel", response_model=PaImportSummary)
async def import_closures_excel(
    service: PaImportServiceDep,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaImportSummary:
    """Bulk-import procurement_closures from xarid 22-sheet xlsx."""
    if not await _has_permission(db, user, "procurement.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.edit required")
    if not has_unrestricted_view(user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Admin scope required")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Expected .xlsx or .xls file")

    raw = await file.read()
    return await service.import_xlsx(raw)


# ─── PUT /closures/{id} ───────────────────────────────────────────

@router.put("/closures/{closure_id}")
async def update_closure(
    closure_id: UUID,
    payload: PaClosurePatch,
    service: PaEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update one closure + recompute median for affected product_codes."""
    if not await _has_permission(db, user, "procurement.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.edit required")

    # Scope-check готовится здесь т.к. требует БД-lookup'а перед service call.
    # Service получает уже отфильтрованный allowed_company_ids list (или None для admin).
    allowed: Optional[list[UUID]] = None
    if not has_unrestricted_view(user):
        allowed = list(await allowed_company_ids(db, user))

    patch = payload.model_dump(exclude_unset=True, exclude_none=False)

    # Заключение центра экспертизы: при изменении текста/статуса штампуем автора и дату
    if "conclusion_text" in patch or "conclusion_status" in patch:
        patch["conclusion_date"] = datetime.now(timezone.utc)
        patch["conclusion_author_id"] = user.id
        patch["conclusion_author_name"] = (
            getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or getattr(user, "email", None)
        )

    return await service.update_closure(closure_id, patch, allowed_company_ids=allowed)


# ─── DELETE /closures ─────────────────────────────────────────────

@router.delete("/closures")
async def clear_closures(
    service: PaEditorServiceDep,
    year: Optional[int] = None,
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Bulk-delete closures filtered by year/source (admin only)."""
    if not await _has_permission(db, user, "procurement.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.edit required")
    if not has_unrestricted_view(user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Admin scope required")
    return await service.clear_closures(year=year, source=source)
