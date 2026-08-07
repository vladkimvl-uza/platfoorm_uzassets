"""IFRS report history routes — даты публикации МСФО-отчётности по компаниям.

GET  /ifrs-report-history             — все строки (scope) + последнее изменение
PUT  /ifrs-report-history/{cid}/{yr}  — задать/очистить дату (право financials.edit)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import JSONResponse
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
    # Область автора проверяем ДО модерации: иначе внешний автор мог бы отправить
    # в очередь (а после аппрува — записать) дату публикации чужой компании вне
    # доступа. ensure_company_access заодно даёт company_id для scope модератора.
    await ensure_company_access(db, user, company_id)

    # Модерация (deny-by-default Phase 4): внешний автор → в очередь. Компания
    # едет реальным UUID в company_id → target_company_id, поэтому scope-гейт
    # модератора работает без добавления модуля в _effective_company_id.
    # partial-safe dump (exclude_unset): отсутствие published_on == null == очистка.
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user, module="ifrs_report_history", action="edit",
        entity_id=f"{company_id}:{year}",
        entity_label=f"Дата публикации МСФО: {company_id} · {year}",
        company_id=company_id, sector_id=None, year=year,
        payload={"company_id": str(company_id), "year": year,
                 **payload.model_dump(mode="json", exclude_unset=True)},
        diff_summary=f"Дата публикации МСФО-отчётности: {company_id} {year}",
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})

    return await IfrsReportHistoryService(db).upsert(company_id, year, payload.published_on, user)
