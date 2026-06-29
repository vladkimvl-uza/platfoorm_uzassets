"""Watch/Follow «отслеживание» проектов и задач."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import ensure_company_access
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.models.user import User
from app.services import watch_service

router = APIRouter(prefix="/watches", tags=["watches"])


class WatchPayload(BaseModel):
    entity_type: str
    entity_id: str


def _validate(et: str) -> None:
    if et not in watch_service.ENTITY_TYPES:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid entity_type")


@router.post("", status_code=http_status.HTTP_204_NO_CONTENT)
async def follow(
    payload: WatchPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate(payload.entity_type)
    # Scope-проверка: нельзя подписаться на сущность недоступной компании
    # (иначе IDOR + утечка метаданных через /watches/me).
    cid = await watch_service.entity_company_id(db, payload.entity_type, payload.entity_id)
    if cid is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "entity not found")
    await ensure_company_access(db, user, cid)
    await watch_service.follow(db, user.id, payload.entity_type, payload.entity_id, source="manual")


@router.delete("", status_code=http_status.HTTP_204_NO_CONTENT)
async def unfollow(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate(entity_type)
    await watch_service.unfollow(db, user.id, entity_type, entity_id)


@router.get("/status")
async def watch_status(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate(entity_type)
    return {
        "watching": await watch_service.is_watching(db, user.id, entity_type, entity_id),
        "count": await watch_service.watcher_count(db, entity_type, entity_id),
    }


@router.get("/me")
async def my_watched(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")
    return await watch_service.list_watched(db, user)
