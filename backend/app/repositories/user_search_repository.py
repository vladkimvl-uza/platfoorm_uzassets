"""Persistence layer for the lightweight user-search endpoint."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserSearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self, *, needle: str, active_only: bool, limit: int
    ) -> Sequence[User]:
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
        # Service accounts excluded — not real assignees.
        stmt = stmt.where(User.is_service_account.is_(False))
        stmt = stmt.order_by(
            User.full_name.asc().nullslast(), User.email.asc()
        ).limit(limit)
        return (await self._session.execute(stmt)).scalars().all()
