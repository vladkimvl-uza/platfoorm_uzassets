"""Per-company activity feed (Pack 149) — thin HTTP shim (refactored 2026-05-25).

GET /companies/{code}/activity?limit=30&days=7
    Returns most recent audit-log + task-history events scoped to ONE
    company. Enforces per-company scope: 403 if user lacks access.

GET /companies/{code}/sector-ranking?year=
    Рейтинг компаний ОДНОГО сектора (виджет карточки). Намеренно шире области
    пользователя: сотрудник компании видит соседей по сектору (решение
    владельца 29.07.2026) — но только название и % выполнения, и каждая строка
    несёт `accessible`: без доступа переход в чужую компанию не предлагается.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, ensure_company_access
from app.dependencies.company_activity import CompanyActivityServiceDep
from app.dependencies.dashboard import DashboardServiceDep
from app.models.company import Company, Sector
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


@router.get("/{code}/sector-ranking")
async def company_sector_ranking(
    code: str,
    dashboard: DashboardServiceDep,
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Рейтинг сектора для карточки компании.

    Цифры берём из того же расчёта, что и дашборд (`completion.by_company`,
    взвешенный прогресс) — иначе виджет и дашборд показывали бы разные проценты
    по одной компании. Область запроса — весь сектор, а не область
    пользователя: раньше сотрудник компании видел в «рейтинге» одну свою строку.
    """
    row = (await db.execute(
        select(Company.id, Company.sector_id, Sector.code.label("sector_code"))
        .outerjoin(Sector, Sector.id == Company.sector_id)
        .where(Company.code == code.lower())
    )).first()
    if row is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
    # Доступ проверяем к САМОЙ карточке: рейтинг — её блок.
    await ensure_company_access(db, user, row.id)
    if not row.sector_code:
        return {"sector_code": None, "items": []}

    data = await dashboard.shareholder_dashboard(
        year=year, sector_code=row.sector_code,
        direction_code=None, company_code=None,
        scope_company_ids=None,          # намеренно: сектор целиком
    )
    allowed = await allowed_company_ids(db, user)   # None = без ограничений
    allowed_codes: Optional[set[str]] = None
    if allowed is not None:
        rows = (await db.execute(
            select(Company.code).where(Company.id.in_(allowed))
        )).scalars().all() if allowed else []
        allowed_codes = {str(c).lower() for c in rows}

    items = []
    for entry in (data.get("completion", {}).get("by_company") or []):
        c_code = str(entry.get("code") or "").lower()
        items.append({
            "code": entry.get("code"),
            "name": entry.get("name"),
            "progress_pct": entry.get("progress_pct"),
            "tasks_total": entry.get("tasks_total"),
            "is_mine": c_code == code.lower(),
            # Клик по чужой компании не должен уводить туда, куда доступа нет.
            "accessible": allowed_codes is None or c_code in allowed_codes,
        })
    return {"sector_code": row.sector_code, "items": items}
