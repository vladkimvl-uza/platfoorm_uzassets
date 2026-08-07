"""Macro Scenarios API — thin HTTP layer (refactored 2026-05-25).

Audit-chain writes stay in route (post-commit, need actor IP/UA).

Внешние авторы (users.is_external) на write-роутах уходят в очередь модерации
(deny-by-default, Фаза 4). Право автора (`_require_admin`) проверяется ДО гейта —
иначе внешний без admin.users мог бы поставить правку в очередь. «Сценарии» —
глобальный справочник без привязки к компании → company_id=None.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.security import _has_permission, get_current_user
from app.database import get_db
from app.dependencies.scenarios import ScenariosServiceDep
from app.models.scenarios import MacroScenario
from app.models.user import User
from app.schemas.scenarios import (
    Scenario,
    ScenarioCreate,
    ScenarioOverride,
    ScenarioOverrideUpsert,
    ScenarioUpdate,
)
from app.services import moderation_service

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _require_admin(user: User) -> None:
    if user.is_owner or _has_permission(user, "admin.users"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Только администратор может редактировать сценарии. "
        "Назначение прав редактирования — также только через администратора.",
    )


async def _resolve_scenario(db: AsyncSession, scenario_id: UUID) -> MacroScenario:
    """Загрузить сценарий (404 ДО модерационной очереди — чтобы внешний автор не
    мог поставить в очередь правку/удаление несуществующего сценария)."""
    row = await db.get(MacroScenario, scenario_id)
    if row is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Сценарий не найден")
    return row


def _request_meta(request: Request) -> dict:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.get("", response_model=list[Scenario])
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
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="scenarios", action="create",
        entity_id=None, entity_label=f"Сценарий: {payload.name_ru}",
        company_id=None, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Создание сценария «{payload.name_ru}»",
    )
    if queued:
        # status_code роута = 201 → очередь отдаём явным JSONResponse(202),
        # иначе dict вернулся бы как 201 и фронт не распознал бы очередь.
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
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
    existing = await _resolve_scenario(db, scenario_id)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="scenarios", action="edit",
        entity_id=str(scenario_id), entity_label=f"Сценарий: {existing.name_ru}",
        company_id=None, sector_id=None, year=None,
        # exclude_unset: в очередь едут ТОЛЬКО реально присланные поля — apply
        # (update_scenario пишет лишь non-None) иначе затёр бы остальные None-ами.
        payload=payload.model_dump(mode="json", exclude_unset=True),
        diff_summary=f"Изменение сценария «{existing.name_ru}»",
    )
    if queued:
        # response_model=Scenario (200) → очередь отдаём JSONResponse(202).
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
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
    existing = await _resolve_scenario(db, scenario_id)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="scenarios", action="delete",
        entity_id=str(scenario_id), entity_label=f"Сценарий: {existing.name_ru}",
        company_id=None, sector_id=None, year=None,
        payload={"scenario_id": str(scenario_id)},
        diff_summary=f"Удаление сценария «{existing.name_ru}»",
    )
    if queued:
        # status_code роута = 204 (без тела) → очередь отдаём JSONResponse(202).
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
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
    existing = await _resolve_scenario(db, scenario_id)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="scenarios", action="edit",
        # target_entity_id несёт "<scenario_id>:<year>" — дискриминатор
        # override-операции в apply-хендлере (см. scenarios apply).
        entity_id=f"{scenario_id}:{year}",
        entity_label=f"Сценарий «{existing.name_ru}» · override {year}",
        company_id=None, sector_id=None, year=year,
        # PUT-override = полная замена значений года (None = «очистить поле»);
        # дампим payload целиком, apply присваивает все поля 1:1 с живым роутом.
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Override сценария «{existing.name_ru}» за {year}",
    )
    if queued:
        # response_model=ScenarioOverride (200) → очередь отдаём JSONResponse(202).
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
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
    existing = await _resolve_scenario(db, scenario_id)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="scenarios", action="delete",
        entity_id=f"{scenario_id}:{year}",
        entity_label=f"Сценарий «{existing.name_ru}» · override {year}",
        company_id=None, sector_id=None, year=year,
        payload={"scenario_id": str(scenario_id), "year": year},
        diff_summary=f"Удаление override сценария «{existing.name_ru}» за {year}",
    )
    if queued:
        # status_code роута = 204 (без тела) → очередь отдаём JSONResponse(202).
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
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
