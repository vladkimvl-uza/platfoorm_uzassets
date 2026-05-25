"""Data access for SystemConfig / YearRegistry."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.year_registry import YearRegistry


class SystemConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_years(self) -> list[YearRegistry]:
        res = await self.session.execute(
            select(YearRegistry).order_by(YearRegistry.year.asc())
        )
        return list(res.scalars().all())

    async def get_year(self, year: int) -> Optional[YearRegistry]:
        res = await self.session.execute(
            select(YearRegistry).where(YearRegistry.year == year)
        )
        return res.scalar_one_or_none()

    async def count_in_table_by_year(self, table_name: str, year: int) -> int:
        """Best-effort count for cascade check. Returns 0 if table missing."""
        try:
            res = await self.session.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE year = :y"),
                {"y": year},
            )
            return int(res.scalar() or 0)
        except Exception:
            return 0

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
