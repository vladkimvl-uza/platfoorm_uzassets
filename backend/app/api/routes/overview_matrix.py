"""Overview matrix config routes — настройка квартальной матрицы «Сводного обзора».

GET  /overview-matrix/{company_id}/{year}   — конфиг (scope-доступ к компании)
PUT  /overview-matrix/{company_id}/{year}   — сохранить (право tasks.edit)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
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
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")
    await ensure_company_access(db, user, company_id)
    return await OverviewMatrixService(db).upsert(company_id, year, config, user)
