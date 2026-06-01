"""Per-company activity feed (Pack 149) — thin HTTP shim (refactored 2026-05-25).

GET /companies/{code}/activity?limit=30&days=7
    Returns most recent audit-log + task-history events scoped to ONE
    company. Enforces per-company scope: 403 if user lacks access.
"""
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.dependencies.company_activity import CompanyActivityServiceDep
from app.models.user import User

router = APIRouter(prefix="/companies", tags=["company-activity"])


@router.get("/{code}/activity")
async def company_activity_feed(
    code: str,
    service: CompanyActivityServiceDep,
    limit: int = Query(30, ge=1, le=200),
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await service.get_feed(code, db, user, limit=limit, days=days)
