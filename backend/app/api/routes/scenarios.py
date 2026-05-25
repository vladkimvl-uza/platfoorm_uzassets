"""Macro Scenarios API — thin HTTP layer (refactored 2026-05-25).

Audit-chain writes stay in route (post-commit, need actor IP/UA).
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.security import _has_permission, get_current_user
from app.database import get_db
from app.dependencies.scenarios import ScenariosServiceDep
from app.models.user import User
from app.schemas.scenarios import (
    Scenario, ScenarioCreate, ScenarioOverride, ScenarioOverrideUpsert, ScenarioUpdate,
)


router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _require_admin(user: User) -> None:
    if user.is_owner or _has_permission(user, "admin.users"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Только администратор может редактировать сценарии. "
        "Назначение прав редактирования — также только через администратора.",
    )


def _request_meta(request: Request) -> dict:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.get("", response_model=List[Scenario])
async def list_scenarios(
    service: ScenariosServiceDep,
    _user: User = Depends(get_current_user),
):
    return await service.list_scenarios()


@router.post("", response_model=Scenario, status_code=http_status.HTTP_201_CREATED)
async def create_scenario(
    payload: ScenarioCreate,
    request: Request,
    service: ScenariosServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    scenario, snapshot = await service.create_scenario(payload)
    await append_audit_entry(
        db,
        actor_id=str(user.id), actor_email=user.email,
        action="create", entity_type="macro_scenario",
        entity_id=str(scenario.id),
        payload=snapshot,
        **_request_meta(request),
    )
    await db.commit()
    return scenario


@router.patch("/{scenario_id}", response_model=Scenario)
async def update_scenario(
    scenario_id: UUID,
    payload: ScenarioUpdate,
    request: Request,
    service: ScenariosServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    scenario, diff = await service.update_scenario(scenario_id, payload)
    if diff:
        await append_audit_entry(
            db,
            actor_id=str(user.id), actor_email=user.email,
            action="update", entity_type="macro_scenario",
            entity_id=str(scenario_id),
            diff=diff,
            **_request_meta(request),
        )
        await db.commit()
    return scenario


@router.delete("/{scenario_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_scenario(
    scenario_id: UUID,
    request: Request,
    service: ScenariosServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    snapshot = await service.delete_scenario(scenario_id)
    await append_audit_entry(
        db,
        actor_id=str(user.id), actor_email=user.email,
        action="delete", entity_type="macro_scenario",
        entity_id=str(scenario_id),
        payload=snapshot,
        **_request_meta(request),
    )
    await db.commit()
    return None


@router.put("/{scenario_id}/overrides/{year}", response_model=ScenarioOverride)
async def upsert_override(
    scenario_id: UUID,
    year: int,
    payload: ScenarioOverrideUpsert,
    request: Request,
    service: ScenariosServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    override, is_create = await service.upsert_override(scenario_id, year, payload)
    await append_audit_entry(
        db,
        actor_id=str(user.id), actor_email=user.email,
        action="create" if is_create else "update",
        entity_type="macro_scenario_override",
        entity_id=f"{scenario_id}:{year}",
        payload=payload.model_dump(mode="json", exclude_none=False),
        **_request_meta(request),
    )
    await db.commit()
    return override


@router.delete("/{scenario_id}/overrides/{year}",
               status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_override(
    scenario_id: UUID,
    year: int,
    request: Request,
    service: ScenariosServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    await service.delete_override(scenario_id, year)
    await append_audit_entry(
        db,
        actor_id=str(user.id), actor_email=user.email,
        action="delete", entity_type="macro_scenario_override",
        entity_id=f"{scenario_id}:{year}",
        payload={"year": year},
        **_request_meta(request),
    )
    await db.commit()
    return None
