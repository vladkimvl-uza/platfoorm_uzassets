"""System configuration endpoints (Pack 7.35).

Provides admin-only CRUD for system-wide yearly constants:
  • Среднегодовой курс UZS/USD
  • Доходная часть бюджета Республики Узбекистан, трлн сум
  • Инфляция, ставка ЦБ, рост ВВП — на будущее

All values are stored in `year_registry` (one row per year). Frontend
useCurrencyConverter composable fetches the full list on app boot and
caches it for the session. After admin edits via this API, frontend
must call /yearly-rates again to reload.

Permission: `admin.users` или владелец (is_owner=true).

Endpoints:
  GET    /system-config/yearly-rates            List all years with rates
  POST   /system-config/yearly-rates            Add new year
  PATCH  /system-config/yearly-rates/{year}     Update rates for year
  DELETE /system-config/yearly-rates/{year}     Remove year (rare)
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.security import _has_permission, get_current_user
from app.database import get_db
from app.models.user import User
from app.models.year_registry import YearRegistry
from app.schemas.system_config import (
    YearlyRate,
    YearlyRateCreate,
    YearlyRateUpdate,
)


router = APIRouter(prefix="/system-config", tags=["system-config"])


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _require_admin(user: User) -> None:
    """All write operations require admin privileges."""
    if user.is_owner:
        return
    if _has_permission(user, "admin.users"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: admin.users (or owner status)",
    )


def _to_schema(yr: YearRegistry) -> YearlyRate:
    return YearlyRate(
        year=yr.year,
        label=yr.label,
        is_closed=yr.is_closed,
        usd_rate=yr.usd_rate,
        eur_rate=yr.eur_rate,
        uz_budget_trln=yr.uz_budget_trln,
        inflation_pct=yr.inflation_pct,
        cb_rate_pct=yr.cb_rate_pct,
        gdp_growth_pct=yr.gdp_growth_pct,
    )


def _diff(before: YearRegistry, after_payload: YearlyRateUpdate) -> dict:
    """Build a diff dict for audit log — only changed fields."""
    diff: dict = {}
    fields = ["label", "is_closed", "usd_rate", "eur_rate", "uz_budget_trln",
              "inflation_pct", "cb_rate_pct", "gdp_growth_pct"]
    for f in fields:
        new = getattr(after_payload, f)
        if new is None:
            continue
        old = getattr(before, f)
        if old != new:
            diff[f] = {"from": str(old) if old is not None else None,
                       "to": str(new)}
    return diff


# ─────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────

@router.get("/yearly-rates", response_model=List[YearlyRate])
async def list_yearly_rates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return all years with their rates, sorted ascending by year.

    Read access is granted to ANY authenticated user — these are
    public/quasi-public constants used by every dashboard block. Only
    writes require admin.
    """
    q = await db.execute(
        select(YearRegistry).order_by(YearRegistry.year.asc())
    )
    rows = q.scalars().all()
    return [_to_schema(r) for r in rows]


@router.post(
    "/yearly-rates",
    response_model=YearlyRate,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_yearly_rate(
    payload: YearlyRateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a new year row. Fails 409 if year already exists."""
    _require_admin(user)

    existing = await db.execute(
        select(YearRegistry).where(YearRegistry.year == payload.year)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Год {payload.year} уже существует в реестре",
        )

    new_row = YearRegistry(
        year=payload.year,
        label=payload.label or str(payload.year),
        is_closed=payload.is_closed,
        usd_rate=payload.usd_rate,
        eur_rate=payload.eur_rate,
        uz_budget_trln=payload.uz_budget_trln,
        inflation_pct=payload.inflation_pct,
        cb_rate_pct=payload.cb_rate_pct,
        gdp_growth_pct=payload.gdp_growth_pct,
    )
    db.add(new_row)
    await db.flush()

    await append_audit_entry(
        db,
        actor_id=str(user.id),
        actor_email=user.email,
        action="create",
        entity_type="year_registry",
        entity_id=str(payload.year),
        payload=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    await db.refresh(new_row)
    return _to_schema(new_row)


@router.patch("/yearly-rates/{year}", response_model=YearlyRate)
async def update_yearly_rate(
    year: int,
    payload: YearlyRateUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    allow_closed: bool = False,
):
    """Partial-update one year's rates. Any field set to non-null is
    written; null/omitted fields are left untouched.

    Closed-year protection: if `is_closed=True`, edits are rejected with
    409 unless caller passes `?allow_closed=true` (frontend's
    "Разблокировать" toggle records intent in audit-trail)."""
    _require_admin(user)

    q = await db.execute(
        select(YearRegistry).where(YearRegistry.year == year)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND,
            f"Год {year} не найден в реестре",
        )

    # Block edits to closed years unless explicitly unlocked.
    # Allow toggling `is_closed` field itself (lock/unlock action).
    only_is_closed_change = (
        payload.is_closed is not None
        and all(
            getattr(payload, f) is None
            for f in (
                "label", "usd_rate", "eur_rate", "uz_budget_trln",
                "inflation_pct", "cb_rate_pct", "gdp_growth_pct",
            )
        )
    )
    if row.is_closed and not allow_closed and not only_is_closed_change:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Год {year} закрыт для редактирования. "
            f"Передайте ?allow_closed=true для подтверждения разблокировки.",
        )

    diff = _diff(row, payload)
    if not diff:
        # Nothing to do
        return _to_schema(row)

    # Apply changes
    if payload.label is not None:
        row.label = payload.label
    if payload.is_closed is not None:
        row.is_closed = payload.is_closed
    if payload.usd_rate is not None:
        row.usd_rate = payload.usd_rate
    if payload.eur_rate is not None:
        row.eur_rate = payload.eur_rate
    if payload.uz_budget_trln is not None:
        row.uz_budget_trln = payload.uz_budget_trln
    if payload.inflation_pct is not None:
        row.inflation_pct = payload.inflation_pct
    if payload.cb_rate_pct is not None:
        row.cb_rate_pct = payload.cb_rate_pct
    if payload.gdp_growth_pct is not None:
        row.gdp_growth_pct = payload.gdp_growth_pct

    await db.flush()

    await append_audit_entry(
        db,
        actor_id=str(user.id),
        actor_email=user.email,
        action="update",
        entity_type="year_registry",
        entity_id=str(year),
        diff=diff,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    await db.refresh(row)
    return _to_schema(row)


@router.delete(
    "/yearly-rates/{year}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def delete_yearly_rate(
    year: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    force: bool = False,
):
    """Hard-delete one year row. Used rarely; usually it's safer to
    leave the row and just edit values to null.

    **Cascade check**: scans known tables (financial_reports, KPI, BP,
    ratings, governance, ESG) for rows with this `year` value.
    Returns 409 with structured `detail` if any are found,
    unless caller passes `?force=true`.
    """
    _require_admin(user)

    q = await db.execute(
        select(YearRegistry).where(YearRegistry.year == year)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND,
            f"Год {year} не найден в реестре",
        )

    # ─── Cascade check across known year-scoped tables ───
    # text() avoids needing every model imported — schema is stable.
    from sqlalchemy import text
    DEPENDENT_TABLES = [
        ("financial_reports",          "Финансовые отчёты"),
        ("bp_lines",                   "Бизнес-планы"),
        ("kpi_facts",                  "KPI факты"),
        ("ratings_history",            "Рейтинги"),
        ("governance_metrics",         "Корп. управление"),
        ("esg_metrics",                "ESG метрики"),
    ]
    if not force:
        cascade_blockers: dict[str, int] = {}
        for table_name, human_label in DEPENDENT_TABLES:
            try:
                cnt = (await db.execute(
                    text(f"SELECT COUNT(*) FROM {table_name} WHERE year = :y"),
                    {"y": year},
                )).scalar() or 0
                if cnt > 0:
                    cascade_blockers[human_label] = int(cnt)
            except Exception:
                # Table doesn't exist or schema differs — skip silently
                continue
        if cascade_blockers:
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                detail=cascade_blockers,
            )

    snapshot = {
        "year": row.year,
        "usd_rate": str(row.usd_rate) if row.usd_rate is not None else None,
        "eur_rate": str(row.eur_rate) if row.eur_rate is not None else None,
        "uz_budget_trln": str(row.uz_budget_trln) if row.uz_budget_trln is not None else None,
    }

    await db.delete(row)

    await append_audit_entry(
        db,
        actor_id=str(user.id),
        actor_email=user.email,
        action="delete",
        entity_type="year_registry",
        entity_id=str(year),
        payload=snapshot,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return None
