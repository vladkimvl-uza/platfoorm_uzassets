"""FinModel v2 REST API — thin HTTP layer (refactored 2026-05-25).

Permission: `finmodel.view` for reads, `finmodel.edit` for writes.
NOTE on isolation (handoff Decision 1): module reads `companies` table for
naming only. No FKs to KPI/Credit/Library — pure financial-truth storage.

Core engines NOT touched:
- `app/services/finmodel_engine.py` — FormulaEngine (compute/balance_check)
- `app/services/finmodel_importer.py` — parse_excel, build_commit_payload
- `app/services/finmodel_validator.py` — validate()
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status as http_status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import has_effective_permission
from app.database import get_db
from app.dependencies.finmodel import FinModelServiceDep
from app.models.user import User
from app.schemas.finmodel import (
    AuditList, CellBatchWrite, CellValueRead, CellWrite,
    CommentCreate, CommentRead, ForecastRequest, MacroCompanyWrite,
    MacroEffective, MacroGlobalRead, ScenarioCreate, ScenarioRead,
    TemplateRowRead, ValidationIssue, YearDataRead, YearLockRead, YearLockUpdate,
)


router = APIRouter(prefix="/finmodel", tags=["finmodel-v2"])


async def _require(db: AsyncSession, user: User, perm: str) -> None:
    if not await has_effective_permission(db, user, perm):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"{perm} required")


class ImportCommitRequest(BaseModel):
    preview: dict
    selected_years: Optional[List[int]] = None
    skip_unmatched: bool = True


# ─── reads ────────────────────────────────────────────────────────

@router.get("/template", response_model=List[TemplateRowRead])
async def get_template(
    service: FinModelServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.get_template()


@router.get("/macro/global", response_model=List[MacroGlobalRead])
async def list_macro_global(
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    return await service.list_macro_global()


@router.get("/{company_id}/scenarios", response_model=List[ScenarioRead])
async def list_scenarios(
    company_id: UUID,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    return await service.list_scenarios(company_id)


@router.get("/{company_id}/comments", response_model=List[CommentRead])
async def list_comments(
    company_id: UUID,
    service: FinModelServiceDep,
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    return await service.list_comments(company_id, year)


@router.get("/{company_id}", response_model=List[YearLockRead])
async def list_years(
    company_id: UUID,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    return await service.list_years(company_id)


@router.get("/{company_id}/{year}", response_model=YearDataRead)
async def get_year(
    company_id: UUID,
    year: int,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    return await service.get_year(company_id, year)


@router.get("/{company_id}/{year}/export.csv")
async def export_year_csv(
    company_id: UUID,
    year: int,
    service: FinModelServiceDep,
    include_macro: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    csv_bytes = await service.export_year_csv(
        company_id, year, include_macro=include_macro,
    )
    filename = f"finmodel_{company_id}_{year}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{company_id}/{year}/audit", response_model=AuditList)
async def get_audit(
    company_id: UUID,
    year: int,
    service: FinModelServiceDep,
    row_code: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    return await service.get_audit(
        company_id, year, row_code=row_code, limit=limit,
    )


@router.get("/{company_id}/{year}/validate", response_model=List[ValidationIssue])
async def validate_year(
    company_id: UUID,
    year: int,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    return await service.validate_year(company_id, year)


# ─── writes (cells, macro) ────────────────────────────────────────

@router.patch("/{company_id}/{year}/cell", response_model=CellValueRead)
async def patch_cell(
    company_id: UUID,
    year: int,
    body: CellWrite,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.patch_cell(company_id, year, body, user_id=user.id)


@router.patch("/{company_id}/{year}/cells/batch", response_model=List[CellValueRead])
async def patch_cells_batch(
    company_id: UUID,
    year: int,
    body: CellBatchWrite,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.patch_cells_batch(company_id, year, body, user_id=user.id)


@router.get("/{company_id}/{year}/macro", response_model=MacroEffective)
async def get_macro(
    company_id: UUID,
    year: int,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.view")
    return await service.get_macro(company_id, year)


@router.put("/{company_id}/{year}/macro", response_model=MacroEffective)
async def put_macro(
    company_id: UUID,
    year: int,
    body: MacroCompanyWrite,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.put_macro(company_id, year, body, user_id=user.id)


# ─── year lifecycle ──────────────────────────────────────────────

@router.post("/{company_id}/year/{year}", response_model=YearLockRead,
             status_code=http_status.HTTP_201_CREATED)
async def create_year(
    company_id: UUID,
    year: int,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.create_year(company_id, year)


@router.delete("/{company_id}/year/{year}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_year(
    company_id: UUID,
    year: int,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    await service.delete_year(company_id, year, user_id=user.id)


@router.post("/{company_id}/year/{year}/copy-from/{src_year}",
             response_model=YearLockRead)
async def copy_year(
    company_id: UUID,
    year: int,
    src_year: int,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.copy_year(company_id, year, src_year, user_id=user.id)


@router.post("/{company_id}/year/{year}/lock", response_model=YearLockRead)
async def lock_year(
    company_id: UUID,
    year: int,
    body: YearLockUpdate,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.lock_year(company_id, year, body, user_id=user.id)


@router.post("/{company_id}/year/{year}/unlock", response_model=YearLockRead)
async def unlock_year(
    company_id: UUID,
    year: int,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.admin")
    return await service.unlock_year(company_id, year)


# ─── scenarios ────────────────────────────────────────────────────

@router.post("/{company_id}/scenarios", response_model=ScenarioRead,
             status_code=http_status.HTTP_201_CREATED)
async def create_scenario(
    company_id: UUID,
    body: ScenarioCreate,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.create_scenario(company_id, body, user_id=user.id)


@router.post("/{company_id}/scenarios/{scenario_id}/activate",
             response_model=ScenarioRead)
async def activate_scenario(
    company_id: UUID,
    scenario_id: UUID,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.activate_scenario(company_id, scenario_id, user_id=user.id)


@router.delete("/{company_id}/scenarios/{scenario_id}",
               status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_scenario(
    company_id: UUID,
    scenario_id: UUID,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    await service.delete_scenario(company_id, scenario_id)


# ─── comments ─────────────────────────────────────────────────────

@router.post("/{company_id}/{year}/comment", response_model=CommentRead,
             status_code=http_status.HTTP_201_CREATED)
async def add_comment(
    company_id: UUID,
    year: int,
    body: CommentCreate,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.add_comment(company_id, year, body, user_id=user.id)


@router.delete("/{company_id}/{year}/comment/{comment_id}",
               status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_comment(
    company_id: UUID,
    year: int,
    comment_id: UUID,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    await service.delete_comment(company_id, comment_id)


# ─── Excel import ────────────────────────────────────────────────

@router.post("/{company_id}/import-excel/preview", response_model=dict)
async def import_excel_preview(
    company_id: UUID,
    service: FinModelServiceDep,
    file: UploadFile = File(...),
    sheet: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                            "Ожидается .xlsx или .xlsm файл")
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "Файл больше 10MB")
    return await service.import_excel_preview(company_id, raw, sheet_name=sheet)


@router.post("/{company_id}/import-excel/commit", response_model=dict)
async def import_excel_commit(
    company_id: UUID,
    body: ImportCommitRequest,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.import_excel_commit(
        company_id,
        preview=body.preview,
        selected_years=body.selected_years,
        skip_unmatched=body.skip_unmatched,
        user_id=user.id,
    )


# ─── forecast ─────────────────────────────────────────────────────

@router.post("/{company_id}/forecast", response_model=dict)
async def regenerate_forecast(
    company_id: UUID,
    body: ForecastRequest,
    service: FinModelServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "finmodel.edit")
    return await service.regenerate_forecast(company_id, body, user_id=user.id)
