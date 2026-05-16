"""Macro scenarios endpoints (Pack 7.40).

CRUD for scenarios and per-year overrides. All writes require admin
privileges (is_owner OR 'admin.users' permission). Reads are open to any
authenticated user.

Endpoints:
  GET    /scenarios                                  List all scenarios
  POST   /scenarios                                  Create custom scenario
  PATCH  /scenarios/{id}                             Update scenario meta
  DELETE /scenarios/{id}                             Delete (seeded scenarios cannot be deleted)
  GET    /scenarios/{id}/overrides                   List overrides for scenario
  PUT    /scenarios/{id}/overrides/{year}            Upsert override for year
  DELETE /scenarios/{id}/overrides/{year}            Clear override for year
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.security import _has_permission, get_current_user
from app.database import get_db
from app.models.scenarios import MacroScenario, MacroScenarioOverride
from app.models.user import User
from app.schemas.scenarios import (
    Scenario,
    ScenarioCreate,
    ScenarioOverride,
    ScenarioOverrideUpsert,
    ScenarioUpdate,
)


router = APIRouter(prefix="/scenarios", tags=["scenarios"])


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _require_admin(user: User) -> None:
    """Pack 7.40 policy: writes are admin-only.

    Owner status OR explicit 'admin.users' permission. There is no
    separate 'analyst.macro' role — only admins grant edit rights.
    """
    if user.is_owner:
        return
    if _has_permission(user, "admin.users"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Только администратор может редактировать сценарии. "
        "Назначение прав редактирования — также только через администратора.",
    )


def _scenario_to_schema(sc: MacroScenario) -> Scenario:
    return Scenario(
        id=sc.id,
        code=sc.code,
        name_ru=sc.name_ru,
        description=sc.description,
        color_hex=sc.color_hex,
        sort_order=sc.sort_order,
        is_seeded=sc.is_seeded,
        overrides=[_override_to_schema(o) for o in sc.overrides],
    )


def _override_to_schema(ov: MacroScenarioOverride) -> ScenarioOverride:
    return ScenarioOverride(
        year=ov.year,
        inflation_pct=ov.inflation_pct,
        cb_rate_pct=ov.cb_rate_pct,
        gdp_growth_pct=ov.gdp_growth_pct,
        usd_rate=ov.usd_rate,
        eur_rate=ov.eur_rate,
        uz_budget_trln=ov.uz_budget_trln,
        notes=ov.notes,
    )


def _get_request_meta(request: Request) -> dict:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


# ─────────────────────────────────────────────────────────────────────
# Scenarios CRUD
# ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[Scenario])
async def list_scenarios(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # noqa: ARG001 — auth required
):
    """Return all scenarios with their overrides, sorted by sort_order then code."""
    q = await db.execute(
        select(MacroScenario).order_by(
            MacroScenario.sort_order.asc(), MacroScenario.code.asc()
        )
    )
    rows = q.scalars().all()
    return [_scenario_to_schema(r) for r in rows]


@router.post(
    "",
    response_model=Scenario,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_scenario(
    payload: ScenarioCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new custom scenario.

    Code must be unique. Seeded scenarios use codes like 'base',
    'optimistic', 'pessimistic'. Custom codes should be prefixed
    'custom_' or similar to avoid collisions.
    """
    _require_admin(user)

    existing = await db.execute(
        select(MacroScenario).where(MacroScenario.code == payload.code)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Сценарий с кодом '{payload.code}' уже существует",
        )

    new_row = MacroScenario(
        code=payload.code,
        name_ru=payload.name_ru,
        description=payload.description,
        color_hex=payload.color_hex,
        sort_order=payload.sort_order,
        is_seeded=False,
    )
    db.add(new_row)
    await db.flush()

    await append_audit_entry(
        db,
        actor_id=str(user.id),
        actor_email=user.email,
        action="create",
        entity_type="macro_scenario",
        entity_id=str(new_row.id),
        payload=payload.model_dump(mode="json"),
        **_get_request_meta(request),
    )
    await db.commit()
    await db.refresh(new_row)
    return _scenario_to_schema(new_row)


@router.patch("/{scenario_id}", response_model=Scenario)
async def update_scenario(
    scenario_id: UUID,
    payload: ScenarioUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update scenario metadata (name, description, color, sort).

    Code cannot be changed once created — to rename, delete and recreate.
    """
    _require_admin(user)

    q = await db.execute(
        select(MacroScenario).where(MacroScenario.id == scenario_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND,
            "Сценарий не найден",
        )

    diff: dict = {}
    if payload.name_ru is not None and payload.name_ru != row.name_ru:
        diff["name_ru"] = {"from": row.name_ru, "to": payload.name_ru}
        row.name_ru = payload.name_ru
    if payload.description is not None and payload.description != row.description:
        diff["description"] = {"from": row.description, "to": payload.description}
        row.description = payload.description
    if payload.color_hex is not None and payload.color_hex != row.color_hex:
        diff["color_hex"] = {"from": row.color_hex, "to": payload.color_hex}
        row.color_hex = payload.color_hex
    if payload.sort_order is not None and payload.sort_order != row.sort_order:
        diff["sort_order"] = {"from": row.sort_order, "to": payload.sort_order}
        row.sort_order = payload.sort_order

    if not diff:
        return _scenario_to_schema(row)

    await db.flush()
    await append_audit_entry(
        db,
        actor_id=str(user.id),
        actor_email=user.email,
        action="update",
        entity_type="macro_scenario",
        entity_id=str(scenario_id),
        diff=diff,
        **_get_request_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return _scenario_to_schema(row)


@router.delete(
    "/{scenario_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def delete_scenario(
    scenario_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a scenario and all its overrides. Seeded scenarios (Base /
    Optimistic / Pessimistic) cannot be deleted — only custom ones."""
    _require_admin(user)

    q = await db.execute(
        select(MacroScenario).where(MacroScenario.id == scenario_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND,
            "Сценарий не найден",
        )

    if row.is_seeded:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            "Системные сценарии (Базовый/Оптимистичный/Пессимистичный) "
            "удалить нельзя. Можно очистить значения override'ов.",
        )

    snapshot = {
        "code": row.code,
        "name_ru": row.name_ru,
        "n_overrides": len(row.overrides),
    }
    await db.delete(row)

    await append_audit_entry(
        db,
        actor_id=str(user.id),
        actor_email=user.email,
        action="delete",
        entity_type="macro_scenario",
        entity_id=str(scenario_id),
        payload=snapshot,
        **_get_request_meta(request),
    )
    await db.commit()
    return None


# ─────────────────────────────────────────────────────────────────────
# Overrides
# ─────────────────────────────────────────────────────────────────────

@router.put(
    "/{scenario_id}/overrides/{year}",
    response_model=ScenarioOverride,
)
async def upsert_override(
    scenario_id: UUID,
    year: int,
    payload: ScenarioOverrideUpsert,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create or update one year's override for a scenario.

    NULL fields explicitly clear the override (fall back to base).
    The `year` in path takes precedence over any year in payload.
    """
    _require_admin(user)

    # Verify scenario exists
    sq = await db.execute(
        select(MacroScenario).where(MacroScenario.id == scenario_id)
    )
    scenario = sq.scalar_one_or_none()
    if scenario is None:
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND,
            "Сценарий не найден",
        )

    # Find existing override
    oq = await db.execute(
        select(MacroScenarioOverride).where(
            MacroScenarioOverride.scenario_id == scenario_id,
            MacroScenarioOverride.year == year,
        )
    )
    ov = oq.scalar_one_or_none()

    is_create = ov is None
    if is_create:
        ov = MacroScenarioOverride(scenario_id=scenario_id, year=year)
        db.add(ov)

    ov.inflation_pct = payload.inflation_pct
    ov.cb_rate_pct = payload.cb_rate_pct
    ov.gdp_growth_pct = payload.gdp_growth_pct
    ov.usd_rate = payload.usd_rate
    ov.eur_rate = payload.eur_rate
    ov.uz_budget_trln = payload.uz_budget_trln
    ov.notes = payload.notes

    await db.flush()

    await append_audit_entry(
        db,
        actor_id=str(user.id),
        actor_email=user.email,
        action="create" if is_create else "update",
        entity_type="macro_scenario_override",
        entity_id=f"{scenario_id}:{year}",
        payload=payload.model_dump(mode="json", exclude_none=False),
        **_get_request_meta(request),
    )
    await db.commit()
    await db.refresh(ov)
    return _override_to_schema(ov)


@router.delete(
    "/{scenario_id}/overrides/{year}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def delete_override(
    scenario_id: UUID,
    year: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove the override row for one year. After delete, this year
    will fall back fully to year_registry base values for this scenario."""
    _require_admin(user)

    oq = await db.execute(
        select(MacroScenarioOverride).where(
            MacroScenarioOverride.scenario_id == scenario_id,
            MacroScenarioOverride.year == year,
        )
    )
    ov = oq.scalar_one_or_none()
    if ov is None:
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND,
            f"Override на год {year} для этого сценария не существует",
        )

    await db.delete(ov)

    await append_audit_entry(
        db,
        actor_id=str(user.id),
        actor_email=user.email,
        action="delete",
        entity_type="macro_scenario_override",
        entity_id=f"{scenario_id}:{year}",
        payload={"year": year},
        **_get_request_meta(request),
    )
    await db.commit()
    return None
