"""Persistence layer for per-company activity feed (Pack 149).

Raw SQL throughout — joins task_history + audit_log against company-scoped
tasks/projects. No ORM models needed for the historical lookup.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company


class CompanyActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_company_by_code(self, code: str):
        return (await self._session.execute(
            select(Company).where(Company.code == code.lower())
        )).scalar_one_or_none()

    async def task_history(
        self, *, company_id: UUID, since: datetime, limit: int,
    ) -> Sequence[Any]:
        return (await self._session.execute(text("""
            SELECT th.created_at AS ts,
                   th.action,
                   th.field_name,
                   th.old_value, th.new_value,
                   t.id::text AS entity_id, t.title,
                   COALESCE(u.full_name, u.email) AS actor
            FROM task_history th
            JOIN tasks t ON t.id = th.task_id
            LEFT JOIN users u ON u.id = th.actor_id
            WHERE t.company_id = :co AND th.created_at >= :since
            ORDER BY th.created_at DESC
            LIMIT :lim
        """), {"co": company_id, "since": since, "lim": limit})).mappings().all()

    async def audit_log(
        self, *, company_id: UUID, since: datetime, limit: int,
    ) -> Sequence[Any]:
        return (await self._session.execute(text("""
            SELECT al.created_at AS ts,
                   al.action,
                   al.actor_email AS actor,
                   al.entity_type,
                   al.entity_id,
                   COALESCE(al.notes, '') AS notes,
                   al.is_critical,
                   al.http_path
            FROM audit_log al
            WHERE al.created_at >= :since
              AND (
                al.entity_id IN (
                  SELECT id::text FROM tasks    WHERE company_id = :co
                  UNION ALL
                  SELECT id::text FROM projects WHERE company_id = :co
                )
                OR al.entity_id = :co_str
              )
            ORDER BY al.created_at DESC
            LIMIT :lim
        """), {"co": company_id, "co_str": str(company_id),
               "since": since, "lim": limit})).mappings().all()

    async def task_history_count(
        self, *, company_id: UUID, since: datetime,
    ) -> int:
        return int((await self._session.execute(text("""
            SELECT COUNT(*) FROM task_history th
            JOIN tasks t ON t.id = th.task_id
            WHERE t.company_id = :co AND th.created_at >= :since
        """), {"co": company_id, "since": since})).scalar() or 0)

    async def audit_log_count(
        self, *, company_id: UUID, since: datetime,
    ) -> int:
        return int((await self._session.execute(text("""
            SELECT COUNT(*) FROM audit_log al
            WHERE al.created_at >= :since
              AND (
                al.entity_id IN (
                  SELECT id::text FROM tasks    WHERE company_id = :co
                  UNION ALL
                  SELECT id::text FROM projects WHERE company_id = :co
                )
                OR al.entity_id = :co_str
              )
        """), {"co": company_id, "co_str": str(company_id),
               "since": since})).scalar() or 0)
