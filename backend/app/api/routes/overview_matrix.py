"""Overview matrix config routes — настройка квартальной матрицы «Сводного обзора».

GET  /overview-matrix/{company_id}/{year}   — конфиг (scope-доступ к компании)
PUT  /overview-matrix/{company_id}/{year}   — сохранить (право tasks.edit)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.core.security import has_effective_permission
from app.models.user import User
from app.schemas.overview_matrix import MatrixConfig, MatrixConfigResponse
from app.services.overview_matrix.service import OverviewMatrixService

router = APIRouter(prefix="/overview-matrix", tags=["overview-matrix"])


@router.get("/{company_id}/{year}", response_model=MatrixConfigResponse)
async def get_matrix_config(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixConfigResponse:
    await ensure_company_access(db, user, company_id)
    return await OverviewMatrixService(db).get(company_id, year)


@router.put("/{company_id}/{year}", response_model=MatrixConfigResponse)
async def save_matrix_config(
    company_id: UUID,
    year: int,
    config: MatrixConfig,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixConfigResponse:
    # Author-гейт ДО модерации: иначе внешний автор мог бы отправить в очередь
    # (а после аппрува — записать) конфиг матрицы чужой/недоступной компании.
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")
    await ensure_company_access(db, user, company_id)

    # Модерация (deny-by-default Phase 4). Полная замена config — action="replace".
    # company_id — реальный UUID → scope штатно через target_company_id.
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user, module="overview_matrix", action="replace",
        entity_id=f"{company_id}:{year}",
        entity_label=f"Матрица обзора: {company_id} · {year}",
        company_id=company_id, sector_id=None, year=year,
        payload={"company_id": str(company_id), "year": year,
                 "config": config.model_dump(mode="json")},
        diff_summary=f"Матрица квартального обзора: {company_id} {year}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )
    return await OverviewMatrixService(db).upsert(company_id, year, config, user)
