"""IFRS report history routes — даты публикации МСФО-отчётности по компаниям.

GET  /ifrs-report-history             — все строки (scope) + последнее изменение
PUT  /ifrs-report-history/{cid}/{yr}  — задать/очистить дату (право financials.edit)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, ensure_company_access, has_unrestricted_view
from app.core.security import has_effective_permission
from app.models.user import User
from app.schemas.ifrs_report_history import (
    IfrsHistoryResponse,
    IfrsHistoryRow,
    IfrsHistoryUpsert,
)
from app.services.ifrs_report_history.service import IfrsReportHistoryService

router = APIRouter(prefix="/ifrs-report-history", tags=["ifrs-report-history"])


@router.get("", response_model=IfrsHistoryResponse)
async def list_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IfrsHistoryResponse:
    if not await has_effective_permission(db, user, "financials.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: financials.view")
    scope: Optional[list[UUID]] = None
    if not has_unrestricted_view(user):
        scope = list(await allowed_company_ids(db, user))
    return await IfrsReportHistoryService(db).list(scope_ids=scope)


@router.put("/{company_id}/{year}", response_model=IfrsHistoryRow)
async def upsert_history(
    company_id: UUID,
    year: int,
    payload: IfrsHistoryUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IfrsHistoryRow:
    if not await has_effective_permission(db, user, "financials.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: financials.edit")
    await ensure_company_access(db, user, company_id)
    return await IfrsReportHistoryService(db).upsert(company_id, year, payload.published_on, user)
