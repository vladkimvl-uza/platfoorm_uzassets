"""Directions — lookup + admin CRUD (Pack 149) — thin HTTP shim
(refactored 2026-05-25).

GET   /directions                — list (any user with tasks.view)
POST  /directions                — create custom (admin / companies.edit)
PATCH /directions/{id}           — rename / re-sort
GET   /directions/{id}/usage     — task/project usage count
DELETE /directions/{id}          — remove + optional reassign
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.dependencies.directions import DirectionsServiceDep
from app.models.user import User
from app.services.directions.service import DirectionIn, DirectionPatch


router = APIRouter(prefix="/directions", tags=["directions"])


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
    return await service.create_direction(payload, db, user)


@router.patch("/{direction_id}")
async def update_direction(
    direction_id: uuid.UUID,
    payload: DirectionPatch,
    service: DirectionsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
    await service.delete_direction(direction_id, reassign_to, db, user)
