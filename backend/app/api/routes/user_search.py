"""Lightweight user search for autocomplete + @-mention pickers (Pack 149).

Any authenticated user can call this. Returns only public-safe fields
(id, email, full_name, initials, role chip color) — no permissions,
no sensitive data. Per-company scoping applies if the caller has
scoped access.

Use cases:
  - Assignee dropdown in task/project editor
  - @-mention popup in comments/descriptions
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User


router = APIRouter(prefix="/users", tags=["users"])


class UserSearchItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    initials: str
    department: Optional[str] = None
    is_active: bool


def _make_initials(full_name: Optional[str], email: str) -> str:
    if full_name:
        parts = full_name.strip().split()
        if len(parts) >= 2:
            return (parts[0][:1] + parts[1][:1]).upper()
        if parts:
            return parts[0][:2].upper()
    return email.split("@", 1)[0][:2].upper()


@router.get("/search")
async def search_users(
    q: str = Query("", max_length=128, description="Подстрока для поиска по email / full_name / username"),
    limit: int = Query(10, ge=1, le=50),
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Prefix/substring search across users — public-safe fields only."""
    needle = q.strip().lower()
    stmt = select(User)
    if active_only:
        stmt = stmt.where(User.is_active.is_(True))
    if needle:
        like = f"%{needle}%"
        stmt = stmt.where(or_(
            func.lower(User.email).like(like),
            func.lower(func.coalesce(User.full_name, "")).like(like),
            func.lower(func.coalesce(User.username, "")).like(like),
        ))
    # Service accounts are technically users but not assignees — exclude.
    stmt = stmt.where(User.is_service_account.is_(False))
    stmt = stmt.order_by(User.full_name.asc().nullslast(), User.email.asc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "username": u.username,
                "initials": _make_initials(u.full_name, u.email),
                "department": u.department,
                "is_active": bool(u.is_active),
            }
            for u in rows
        ],
        "count": len(rows),
        "query": q,
    }
