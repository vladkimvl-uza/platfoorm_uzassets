"""Production indicators API — thin HTTP layer (производственные показатели).

Вкладка «Производственные показатели» модуля Бизнес-план. Права переиспользуют
bp.* (это фасет БП). Хранение — JSONB snapshot (см. production_repository).

  GET  /production/overview?year=&period=       — свод компаний + KPI портфеля
  GET  /production/available                     — доступные (year, period)
  GET  /production/companies/{code}?year=&period= — одна компания (карточка БП)
  PUT  /production/companies/{code}              — правка одной компании (редактор)
  POST /production/import?year=&period=          — bulk-импорт «Свода» (xlsx)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import has_effective_permission
from app.dependencies.production import ProductionServiceDep
from app.models.user import User
from app.schemas.production import ProductionUpsert

log = logging.getLogger(__name__)
router = APIRouter(prefix="/production", tags=["production"])


@router.get("/overview")
async def production_overview(
    service: ProductionServiceDep,
    year: int = 2026,
    period: str = "h1",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    allowed_codes: Optional[set[str]] = None
    if not has_unrestricted_view(user):
        scope_ids = await allowed_company_ids(db, user)
        if not scope_ids:
            return {"companies": [], "kpis": {"present": 0, "with_data": 0,
                    "plan_total": 0, "expect_total": 0, "exec_pct": None,
                    "over": 0, "under": 0, "ontarget": 0, "overpar": 0},
                    "year": year, "period": period}
        allowed_codes = await service.resolve_codes_for_scope(scope_ids)
    return await service.overview(year=year, period=period, allowed_codes=allowed_codes)


@router.get("/available")
async def production_available(
    service: ProductionServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    return await service.available()


@router.get("/companies/{code}")
async def production_company_detail(
    code: str,
    service: ProductionServiceDep,
    year: int = 2026,
    period: str = "h1",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Производство одной компании — для вкладки БП в карточке компании.
    Scoped: company-scoped юзер видит только свои компании (как PUT ниже)."""
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    if not has_unrestricted_view(user):
        scope_ids = await allowed_company_ids(db, user)
        allowed_codes = await service.resolve_codes_for_scope(scope_ids) if scope_ids else set()
        if code.lower() not in allowed_codes:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this company")
    return await service.company_detail(code, year=year, period=period)


@router.put("/companies/{code}")
async def update_production_company(
    code: str,
    payload: ProductionUpsert,
    service: ProductionServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "bp.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.edit required")
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
        module="production", action="upsert_company",
        entity_id=code, entity_label=f"Производство: {co_name} · {payload.year} {payload.period}",
        company_id=None, sector_id=None, year=payload.year,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Production upsert: {code} {payload.year}/{payload.period} ({len(payload.lines)} строк)",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )
    return await service.upsert_company(code, payload)


@router.post("/import")
async def import_production_xlsx(
    service: ProductionServiceDep,
    file: UploadFile = File(...),
    year: int = 2026,
    period: str = "h1",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Bulk-импорт «Свода бизнес-плана» (лист на компанию). Как forensic
    import-excel — только для админ-периметра (кросс-компанийная запись,
    минуя модерацию); темп/исполнение из файла игнорируются, пересчёт в сервисе."""
    if not await has_effective_permission(db, user, "bp.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.edit required")
    if not has_unrestricted_view(user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Admin scope required for bulk import")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Expected .xlsx or .xls file")
    raw = await file.read()
    if not raw:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Empty file")
    return await service.import_xlsx(raw, year=year, period=period)
