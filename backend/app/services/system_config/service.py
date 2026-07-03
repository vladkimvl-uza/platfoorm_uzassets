"""Use cases for System Config / YearRegistry."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.year_registry import YearRegistry
from app.schemas.system_config import (
    YearlyRate,
    YearlyRateCreate,
    YearlyRateUpdate,
)
from app.uow.ports import UnitOfWorkABC


def _to_schema(yr: YearRegistry) -> YearlyRate:
    return YearlyRate(
        year=yr.year, label=yr.label, is_closed=yr.is_closed,
        usd_rate=yr.usd_rate, eur_rate=yr.eur_rate,
        uz_budget_trln=yr.uz_budget_trln,
        inflation_pct=yr.inflation_pct,
        cb_rate_pct=yr.cb_rate_pct,
        gdp_growth_pct=yr.gdp_growth_pct,
        gdp_bln=yr.gdp_bln,
    )


def _diff(before: YearRegistry, after_payload: YearlyRateUpdate) -> dict:
    diff: dict = {}
    fields = ["label", "is_closed", "usd_rate", "eur_rate", "uz_budget_trln",
              "inflation_pct", "cb_rate_pct", "gdp_growth_pct", "gdp_bln"]
    for f in fields:
        new = getattr(after_payload, f)
        if new is None:
            continue
        old = getattr(before, f)
        if old != new:
            diff[f] = {
                "from": str(old) if old is not None else None,
                "to": str(new),
            }
    return diff


# Tables to scan for cascading-year dependencies on DELETE
DEPENDENT_TABLES = [
    ("financial_reports",  "Финансовые отчёты"),
    ("bp_lines",           "Бизнес-планы"),
    ("kpi_facts",          "KPI факты"),
    ("ratings_history",    "Рейтинги"),
    ("governance_metrics", "Корп. управление"),
    ("esg_metrics",        "ESG метрики"),
]


class SystemConfigService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def list_yearly_rates(self) -> list[YearlyRate]:
        async with self.uow:
            rows = await self.uow.system_config.list_years()
        return [_to_schema(r) for r in rows]

    async def create_yearly_rate(self, payload: YearlyRateCreate) -> tuple[YearlyRate, dict]:
        async with self.uow:
            existing = await self.uow.system_config.get_year(payload.year)
            if existing is not None:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Год {payload.year} уже существует в реестре",
                )
            row = YearRegistry(
                year=payload.year,
                label=payload.label or str(payload.year),
                is_closed=payload.is_closed,
                usd_rate=payload.usd_rate,
                eur_rate=payload.eur_rate,
                uz_budget_trln=payload.uz_budget_trln,
                inflation_pct=payload.inflation_pct,
                cb_rate_pct=payload.cb_rate_pct,
                gdp_growth_pct=payload.gdp_growth_pct,
                gdp_bln=payload.gdp_bln,
            )
            self.uow.system_config.add(row)
            await self.uow.system_config.flush()
            await self.uow.system_config.refresh(row)
            return _to_schema(row), payload.model_dump(mode="json")

    async def update_yearly_rate(
        self,
        year: int,
        payload: YearlyRateUpdate,
        *,
        allow_closed: bool,
    ) -> tuple[YearlyRate, dict]:
        async with self.uow:
            row = await self.uow.system_config.get_year(year)
            if row is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    f"Год {year} не найден в реестре",
                )

            # Allow toggling `is_closed` itself even when row is closed
            only_is_closed_change = (
                payload.is_closed is not None
                and all(
                    getattr(payload, f) is None
                    for f in (
                        "label", "usd_rate", "eur_rate", "uz_budget_trln",
                        "inflation_pct", "cb_rate_pct", "gdp_growth_pct", "gdp_bln",
                    )
                )
            )
            if row.is_closed and not allow_closed and not only_is_closed_change:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Год {year} закрыт для редактирования. "
                    f"Передайте ?allow_closed=true для подтверждения разблокировки.",
                )

            diff = _diff(row, payload)
            if not diff:
                return _to_schema(row), {}

            if payload.label is not None:
                row.label = payload.label
            if payload.is_closed is not None:
                row.is_closed = payload.is_closed
            if payload.usd_rate is not None:
                row.usd_rate = payload.usd_rate
            if payload.eur_rate is not None:
                row.eur_rate = payload.eur_rate
            if payload.uz_budget_trln is not None:
                row.uz_budget_trln = payload.uz_budget_trln
            if payload.inflation_pct is not None:
                row.inflation_pct = payload.inflation_pct
            if payload.cb_rate_pct is not None:
                row.cb_rate_pct = payload.cb_rate_pct
            if payload.gdp_growth_pct is not None:
                row.gdp_growth_pct = payload.gdp_growth_pct
            if payload.gdp_bln is not None:
                row.gdp_bln = payload.gdp_bln

            await self.uow.system_config.flush()
            await self.uow.system_config.refresh(row)
            return _to_schema(row), diff

    async def delete_yearly_rate(
        self,
        year: int,
        *,
        force: bool,
    ) -> Optional[dict]:
        """Returns audit snapshot on success; raises on cascade conflict."""
        async with self.uow:
            row = await self.uow.system_config.get_year(year)
            if row is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    f"Год {year} не найден в реестре",
                )

            if not force:
                blockers: dict[str, int] = {}
                for table_name, label in DEPENDENT_TABLES:
                    cnt = await self.uow.system_config.count_in_table_by_year(
                        table_name, year,
                    )
                    if cnt > 0:
                        blockers[label] = cnt
                if blockers:
                    raise HTTPException(
                        http_status.HTTP_409_CONFLICT,
                        detail=blockers,
                    )

            snapshot = {
                "year": row.year,
                "usd_rate": str(row.usd_rate) if row.usd_rate is not None else None,
                "eur_rate": str(row.eur_rate) if row.eur_rate is not None else None,
                "uz_budget_trln": str(row.uz_budget_trln) if row.uz_budget_trln is not None else None,
            }
            await self.uow.system_config.delete(row)
            await self.uow.system_config.flush()
            return snapshot
