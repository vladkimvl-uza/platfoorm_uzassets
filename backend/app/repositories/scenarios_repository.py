"""Data access for Macro Scenarios + overrides."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.scenarios import MacroScenario, MacroScenarioOverride


class ScenariosRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_scenarios(self):
        res = await self.session.execute(
            select(MacroScenario)
            .options(selectinload(MacroScenario.overrides))
            .order_by(MacroScenario.sort_order.asc(), MacroScenario.code.asc())
        )
        return list(res.scalars().all())

    async def get_scenario(self, scenario_id: UUID) -> Optional[MacroScenario]:
        res = await self.session.execute(
            select(MacroScenario)
            .options(selectinload(MacroScenario.overrides))
            .where(MacroScenario.id == scenario_id)
        )
        return res.scalar_one_or_none()

    async def get_scenario_by_code(self, code: str) -> Optional[MacroScenario]:
        res = await self.session.execute(
            select(MacroScenario).where(MacroScenario.code == code)
        )
        return res.scalar_one_or_none()

    async def get_override(
        self, scenario_id: UUID, year: int,
    ) -> Optional[MacroScenarioOverride]:
        res = await self.session.execute(
            select(MacroScenarioOverride).where(
                MacroScenarioOverride.scenario_id == scenario_id,
                MacroScenarioOverride.year == year,
            )
        )
        return res.scalar_one_or_none()

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
