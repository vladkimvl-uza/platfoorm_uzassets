"""Report wizard config routes — сохранённый «Мастер отчёта» по компании+году.

GET  /report-wizard/{code}/{year}   — конфиг (scope-доступ к компании)
PUT  /report-wizard/{code}/{year}   — сохранить (право tasks.edit)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.core.security import has_effective_permission
from app.models.company import Company
from app.models.user import User
from app.schemas.report_wizard import ReportWizardResponse, ReportWizardSave
from app.services.report_wizard.service import ReportWizardService

router = APIRouter(prefix="/report-wizard", tags=["report-wizard"])


async def _company_id(db: AsyncSession, code: str) -> UUID:
    res = await db.execute(select(Company.id).where(Company.code == code))
    cid = res.scalar_one_or_none()
    if cid is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Company '{code}' not found")
    return cid


@router.get("/{code}/{year}", response_model=ReportWizardResponse)
async def get_report_wizard(
    code: str,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportWizardResponse:
    cid = await _company_id(db, code)
    await ensure_company_access(db, user, cid)
    return await ReportWizardService(db).get(cid, year)


@router.put("/{code}/{year}", response_model=ReportWizardResponse)
async def save_report_wizard(
    code: str,
    year: int,
    payload: ReportWizardSave,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportWizardResponse:
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")
    cid = await _company_id(db, code)
    await ensure_company_access(db, user, cid)
    return await ReportWizardService(db).upsert(cid, year, payload.config, user)
