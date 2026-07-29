"""Persistence layer for the lightweight user-search endpoint."""
from __future__ import annotations

from collections.abc import Sequence

from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Group, User, UserGroupRole


class UserSearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        needle: str,
        active_only: bool,
        limit: int,
        company_id: Optional[UUID] = None,
    ) -> Sequence[User]:
        stmt = select(User)
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        if company_id is not None:
            # Сотрудники компании: привязка в профиле ЛИБО членство в группе
            # этой компании. Пикер ответственного в карточке компании должен
            # предлагать своих людей, а не весь справочник платформы.
            member_of = (
                select(UserGroupRole.user_id)
                .join(Group, Group.id == UserGroupRole.group_id)
                .where(Group.company_id == company_id)
            )
            stmt = stmt.where(or_(
                User.organization_id == company_id,
                User.id.in_(member_of),
            ))
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
