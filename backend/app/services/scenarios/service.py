"""Use cases for Macro Scenarios + Overrides."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.scenarios import MacroScenario, MacroScenarioOverride
from app.schemas.scenarios import (
    Scenario,
    ScenarioCreate,
    ScenarioOverride,
    ScenarioOverrideUpsert,
    ScenarioUpdate,
)
from app.uow.ports import UnitOfWorkABC


def _override_to_schema(ov: MacroScenarioOverride) -> ScenarioOverride:
    return ScenarioOverride(
        year=ov.year,
        inflation_pct=ov.inflation_pct,
        cb_rate_pct=ov.cb_rate_pct,
        gdp_growth_pct=ov.gdp_growth_pct,
        usd_rate=ov.usd_rate,
        eur_rate=ov.eur_rate,
        uz_budget_trln=ov.uz_budget_trln,
        notes=ov.notes,
    )


def _scenario_to_schema(sc: MacroScenario) -> Scenario:
    return Scenario(
        id=sc.id, code=sc.code, name_ru=sc.name_ru,
        description=sc.description, color_hex=sc.color_hex,
        sort_order=sc.sort_order, is_seeded=sc.is_seeded,
        overrides=[_override_to_schema(o) for o in sc.overrides],
    )


class ScenariosService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def list_scenarios(self) -> list[Scenario]:
        async with self.uow:
            rows = await self.uow.scenarios.list_scenarios()
        return [_scenario_to_schema(r) for r in rows]

    async def create_scenario(self, payload: ScenarioCreate) -> tuple[Scenario, dict]:
        async with self.uow:
            existing = await self.uow.scenarios.get_scenario_by_code(payload.code)
            if existing is not None:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Сценарий с кодом '{payload.code}' уже существует",
                )
            new_row = MacroScenario(
                code=payload.code, name_ru=payload.name_ru,
                description=payload.description,
                color_hex=payload.color_hex,
                sort_order=payload.sort_order,
                is_seeded=False,
            )
            self.uow.scenarios.add(new_row)
            await self.uow.scenarios.flush()
            await self.uow.scenarios.refresh(new_row)
            scenario_id = new_row.id
            full = await self.uow.scenarios.get_scenario(scenario_id)
            return _scenario_to_schema(full), payload.model_dump(mode="json")

    async def update_scenario(
        self, scenario_id: UUID, payload: ScenarioUpdate,
    ) -> tuple[Scenario, dict]:
        """Returns (scenario, diff). diff={} means no changes."""
        async with self.uow:
            row = await self.uow.scenarios.get_scenario(scenario_id)
            if row is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Сценарий не найден",
                )
            diff: dict = {}
            if payload.name_ru is not None and payload.name_ru != row.name_ru:
                diff["name_ru"] = {"from": row.name_ru, "to": payload.name_ru}
                row.name_ru = payload.name_ru
            if payload.description is not None and payload.description != row.description:
                diff["description"] = {"from": row.description, "to": payload.description}
                row.description = payload.description
            if payload.color_hex is not None and payload.color_hex != row.color_hex:
                diff["color_hex"] = {"from": row.color_hex, "to": payload.color_hex}
                row.color_hex = payload.color_hex
            if payload.sort_order is not None and payload.sort_order != row.sort_order:
                diff["sort_order"] = {"from": row.sort_order, "to": payload.sort_order}
                row.sort_order = payload.sort_order

            if not diff:
                return _scenario_to_schema(row), {}

            await self.uow.scenarios.flush()
            await self.uow.scenarios.refresh(row)
            return _scenario_to_schema(row), diff

    async def delete_scenario(self, scenario_id: UUID) -> dict:
        """Returns snapshot for audit log. Raises 409 for seeded scenarios."""
        async with self.uow:
            row = await self.uow.scenarios.get_scenario(scenario_id)
            if row is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Сценарий не найден",
                )
            if row.is_seeded:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    "Системные сценарии (Базовый/Оптимистичный/Пессимистичный) "
                    "удалить нельзя. Можно очистить значения override'ов.",
                )
            snapshot = {
                "code": row.code, "name_ru": row.name_ru,
                "n_overrides": len(row.overrides),
            }
            await self.uow.scenarios.delete(row)
            await self.uow.scenarios.flush()
            return snapshot

    # ─── overrides ────────────────────────────────────────────────

    async def upsert_override(
        self,
        scenario_id: UUID,
        year: int,
        payload: ScenarioOverrideUpsert,
    ) -> tuple[ScenarioOverride, bool]:
        """Returns (override, is_create)."""
        async with self.uow:
            scenario = await self.uow.scenarios.get_scenario(scenario_id)
            if scenario is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Сценарий не найден",
                )
            ov = await self.uow.scenarios.get_override(scenario_id, year)
            is_create = ov is None
            if is_create:
                ov = MacroScenarioOverride(scenario_id=scenario_id, year=year)
                self.uow.scenarios.add(ov)
            ov.inflation_pct = payload.inflation_pct
            ov.cb_rate_pct = payload.cb_rate_pct
            ov.gdp_growth_pct = payload.gdp_growth_pct
            ov.usd_rate = payload.usd_rate
            ov.eur_rate = payload.eur_rate
            ov.uz_budget_trln = payload.uz_budget_trln
            ov.notes = payload.notes
            await self.uow.scenarios.flush()
            await self.uow.scenarios.refresh(ov)
            return _override_to_schema(ov), is_create

    async def delete_override(self, scenario_id: UUID, year: int) -> None:
        async with self.uow:
            ov = await self.uow.scenarios.get_override(scenario_id, year)
            if ov is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    f"Override на год {year} для этого сценария не существует",
                )
            await self.uow.scenarios.delete(ov)
            await self.uow.scenarios.flush()
