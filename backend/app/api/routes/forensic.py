"""Forensic & Procurement audit API — thin HTTP layer (refactored 2026-05-25).

Endpoints:
  GET    /forensic/overview                  — full list of companies + KPIs
  PUT    /forensic/companies/{code}          — patch single co × year
  DELETE /forensic/data?year=N               — clear year data
  POST   /forensic/import-excel              — bulk upsert from xlsx

Moderation gate for /companies/{code} stays in route (post-commit
side-effect requiring request actor).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status as http_status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import has_effective_permission
from app.dependencies.forensic import ForensicServiceDep
from app.models.user import User


log = logging.getLogger(__name__)
router = APIRouter(prefix="/forensic", tags=["forensic"])


# ─── pydantic ─────────────────────────────────────────────────────

class YearPatch(BaseModel):
    """Editable per-(company, year) fields."""
    plan: Optional[float] = None
    fact: Optional[float] = None
    n9p:  Optional[float] = None
    n9f:  Optional[float] = None
    q1p:  Optional[float] = None
    q1f:  Optional[float] = None
    q2p:  Optional[float] = None
    q2f:  Optional[float] = None
    q3p:  Optional[float] = None
    q3f:  Optional[float] = None
    q4p:  Optional[float] = None
    q4f:  Optional[float] = None


class CompanyPatch(BaseModel):
    """Per-(company, year) plan/fact + metadata edit."""
    year: int = Field(..., ge=2000, le=2100)
    year_fields: Optional[YearPatch] = None
    plan_status:      Optional[str] = None
    forensic_status:  Optional[str] = None
    auditor:          Optional[str] = None
    audit_years:      Optional[str] = None


# ─── overview ─────────────────────────────────────────────────────

@router.get("/overview")
async def forensic_overview(
    service: ForensicServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "procurement.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.view required")

    allowed_codes: Optional[set[str]] = None
    if not has_unrestricted_view(user):
        scope_ids = await allowed_company_ids(db, user)
        if not scope_ids:
            return {
                "companies": [],
                "kpis": {
                    "total_companies": 0,
                    "plan_approved": 0,
                    "forensic_done": 0,
                    "with_auditor": 0,
                },
            }
        allowed_codes = await service.resolve_codes_for_scope(scope_ids)
    return await service.overview(allowed_codes=allowed_codes)


# ─── update ───────────────────────────────────────────────────────

@router.put("/companies/{code}")
async def update_forensic_company(
    code: str,
    payload: CompanyPatch,
    service: ForensicServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "procurement.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.edit required")

    if not has_unrestricted_view(user):
        scope_ids = await allowed_company_ids(db, user)
        if not scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No company access")
        allowed_codes = await service.resolve_codes_for_scope(scope_ids)
        if code.lower() not in allowed_codes:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this company")

    co_name = await service.get_company_label(code)
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="procurement", action="update_company",
        entity_id=code, entity_label=f"Закупки: {co_name} · {payload.year}",
        company_id=None, sector_id=None, year=payload.year,
        payload=payload.model_dump(mode="json", exclude_none=True),
        diff_summary=f"Forensic update: {code} year {payload.year}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    return await service.update_company(code, payload)


# ─── clear year ───────────────────────────────────────────────────

@router.delete("/data")
async def clear_forensic_year(
    service: ForensicServiceDep,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "procurement.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.edit required")
    if not has_unrestricted_view(user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Admin scope required to clear data")
    return await service.clear_year(year)


# ─── import-excel ─────────────────────────────────────────────────

@router.post("/import-excel")
async def import_forensic_excel(
    service: ForensicServiceDep,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "procurement.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.edit required")
    if not has_unrestricted_view(user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Admin scope required for bulk import")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Expected .xlsx or .xls file")
    raw = await file.read()
    if not raw:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Empty file")
    return await service.import_excel(raw)
