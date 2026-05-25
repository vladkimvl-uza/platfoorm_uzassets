"""Lightweight user search — thin HTTP shim (refactored 2026-05-25).

Pack 149. Any authenticated user can call this. Returns only public-safe
fields (id, email, full_name, initials, department) for autocomplete +
@-mention pickers in task/project/comments editors.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.dependencies.user_search import UserSearchServiceDep
from app.models.user import User


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search")
async def search_users(
    service: UserSearchServiceDep,
    q: str = Query("", max_length=128,
                   description="Подстрока для поиска по email / full_name / username"),
    limit: int = Query(10, ge=1, le=50),
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    return await service.search(
        db, q=q, active_only=active_only, limit=limit,
    )
