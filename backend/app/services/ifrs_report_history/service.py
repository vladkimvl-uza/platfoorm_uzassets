"""IFRS report history service — list + upsert даты публикации (с аудитом)."""
from __future__ import annotations

from datetime import date
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ifrs_report_history import IfrsReportHistory
from app.models.user import User
from app.schemas.ifrs_report_history import (
    IfrsHistoryLastChange,
    IfrsHistoryResponse,
    IfrsHistoryRow,
)


class IfrsReportHistoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, *, scope_ids: Optional[Sequence[UUID]] = None) -> IfrsHistoryResponse:
        q = select(IfrsReportHistory)
        if scope_ids is not None:
            q = q.where(IfrsReportHistory.company_id.in_(list(scope_ids)))
        res = await self.db.execute(q)
        rows = list(res.scalars().all())
        out = [IfrsHistoryRow.model_validate(r) for r in rows]
        # последнее изменение — по max(updated_at)
        last = IfrsHistoryLastChange()
        latest = None
        for r in rows:
            if r.updated_at is not None and (latest is None or r.updated_at > latest.updated_at):
                latest = r
        if latest is not None:
            last = IfrsHistoryLastChange(by_name=latest.updated_by_name, at=latest.updated_at)
        return IfrsHistoryResponse(rows=out, last_change=last)

    async def upsert(
        self, company_id: UUID, year: int, published_on: Optional[date], user: User,
    ) -> IfrsHistoryRow:
        res = await self.db.execute(
            select(IfrsReportHistory).where(
                IfrsReportHistory.company_id == company_id,
                IfrsReportHistory.year == year,
            )
        )
        row = res.scalar_one_or_none()
        name = (
            getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or getattr(user, "email", None)
        )
        if row is None:
            row = IfrsReportHistory(
                company_id=company_id, year=year, published_on=published_on,
                updated_by=user.id, updated_by_name=name,
            )
            self.db.add(row)
        else:
            row.published_on = published_on
            row.updated_by = user.id
            row.updated_by_name = name
        await self.db.commit()
        await self.db.refresh(row)
        return IfrsHistoryRow.model_validate(row)
