"""Directions — lookup + admin CRUD (Pack 149) — thin HTTP shim
(refactored 2026-05-25).

GET   /directions                — list (any user with tasks.view)
POST  /directions                — create custom (admin / companies.edit)
PATCH /directions/{id}           — rename / re-sort
GET   /directions/{id}/usage     — task/project usage count
DELETE /directions/{id}          — remove + optional reassign

Внешние авторы (users.is_external) на write-роутах уходят в очередь модерации
(deny-by-default, Фаза 4). Право автора (`_require_admin`) проверяется ДО гейта —
иначе внешний без companies.edit/tasks.manage мог бы поставить правку в очередь.
«Направления» — глобальный справочник без привязки к компании → company_id=None.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.dependencies.directions import DirectionsServiceDep
from app.models.user import User
from app.repositories.directions_repository import DirectionsRepository
from app.services.directions.service import (
    DirectionIn,
    DirectionPatch,
    _require_admin,
)

router = APIRouter(prefix="/directions", tags=["directions"])


async def _resolve_direction_label(db: AsyncSession, direction_id: uuid.UUID) -> str:
    """Название направления (404 ДО модерационной очереди — чтобы внешний автор
    не мог поставить в очередь правку/удаление несуществующего направления)."""
    d = await DirectionsRepository(db).get_by_id(direction_id)
    if not d:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Direction not found")
    return d.name_ru


@router.get("")
async def list_directions(
    service: DirectionsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.list_directions(db, user)


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_direction(
    payload: DirectionIn,
    service: DirectionsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Право автора проверяем ДО модерации (тот же гейт, что в сервисе).
    _require_admin(user)

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user, module="directions", action="create",
        entity_id=None, entity_label=f"Направление: {payload.name_ru}",
        company_id=None, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Создание направления «{payload.name_ru}»",
    )
    if queued:
        # status_code роута = 201, поэтому очередь отдаём явным JSONResponse(202),
        # иначе plain dict вернулся бы как 201 и фронт не распознал бы очередь.
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    return await service.create_direction(payload, db, user)


@router.patch("/{direction_id}")
async def update_direction(
    direction_id: uuid.UUID,
    payload: DirectionPatch,
    service: DirectionsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    label = await _resolve_direction_label(db, direction_id)

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user, module="directions", action="edit",
        entity_id=str(direction_id), entity_label=f"Направление: {label}",
        company_id=None, sector_id=None, year=None,
        # exclude_unset: в очередь едут ТОЛЬКО реально присланные поля, чтобы
        # apply (service.update делает model_dump(exclude_unset)) не затёр
        # остальные поля None-ами при частичном патче.
        payload=payload.model_dump(mode="json", exclude_unset=True),
        diff_summary=f"Изменение направления «{label}»",
    )
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    return await service.update_direction(direction_id, payload, db, user)


@router.get("/{direction_id}/usage")
async def direction_usage(
    direction_id: uuid.UUID,
    service: DirectionsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.direction_usage(direction_id, db, user)


@router.delete("/{direction_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_direction(
    direction_id: uuid.UUID,
    service: DirectionsServiceDep,
    reassign_to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    label = await _resolve_direction_label(db, direction_id)

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user, module="directions", action="delete",
        entity_id=str(direction_id), entity_label=f"Направление: {label}",
        company_id=None, sector_id=None, year=None,
        payload={"reassign_to": reassign_to},
        diff_summary=(f"Удаление направления «{label}»"
                      + (f" → {reassign_to}" if reassign_to else "")),
    )
    if queued:
        # status_code роута = 204 (без тела) → очередь отдаём JSONResponse(202).
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    await service.delete_direction(direction_id, reassign_to, db, user)
