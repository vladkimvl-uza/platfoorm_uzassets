"""Data access for Credit Scenarios + per-loan overrides + custom indicators."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.credit import CreditPortfolioLoan
from app.models.credit_scenario import (
    CreditCustomIndicator,
    CreditPortfolioLoanScenario,
    CreditPortfolioScenario,
)


class CreditScenarioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── scenarios ────────────────────────────────────────────────

    async def list_scenarios(self) -> list[CreditPortfolioScenario]:
        res = await self.session.execute(
            select(CreditPortfolioScenario)
            .order_by(CreditPortfolioScenario.created_at.asc())
        )
        return list(res.scalars().all())

    async def get_scenario(self, scenario_id: UUID) -> Optional[CreditPortfolioScenario]:
        res = await self.session.execute(
            select(CreditPortfolioScenario)
            .where(CreditPortfolioScenario.id == scenario_id)
        )
        return res.scalar_one_or_none()

    async def scenario_exists_by_key(self, key: str) -> bool:
        res = await self.session.execute(
            select(CreditPortfolioScenario.id)
            .where(CreditPortfolioScenario.macro_scenario_key == key)
        )
        return res.first() is not None

    # ─── loan overrides ───────────────────────────────────────────

    async def list_overrides(self, scenario_id: UUID):
        res = await self.session.execute(
            select(CreditPortfolioLoanScenario)
            .where(CreditPortfolioLoanScenario.scenario_id == scenario_id)
        )
        return list(res.scalars().all())

    async def get_override(
        self, scenario_id: UUID, loan_id: UUID,
    ) -> Optional[CreditPortfolioLoanScenario]:
        res = await self.session.execute(
            select(CreditPortfolioLoanScenario).where(and_(
                CreditPortfolioLoanScenario.scenario_id == scenario_id,
                CreditPortfolioLoanScenario.loan_id == loan_id,
            ))
        )
        return res.scalar_one_or_none()

    # ─── custom indicators ────────────────────────────────────────

    async def list_custom_indicators(self):
        res = await self.session.execute(
            select(CreditCustomIndicator)
            .order_by(CreditCustomIndicator.created_at.asc())
        )
        return list(res.scalars().all())

    async def get_custom_indicator(self, ind_id: UUID) -> Optional[CreditCustomIndicator]:
        res = await self.session.execute(
            select(CreditCustomIndicator)
            .where(CreditCustomIndicator.id == ind_id)
        )
        return res.scalar_one_or_none()

    async def indicator_exists_by_key(self, key: str) -> bool:
        res = await self.session.execute(
            select(CreditCustomIndicator.id)
            .where(CreditCustomIndicator.key == key)
        )
        return res.first() is not None

    # ─── loans (for formula test + drilldown) ─────────────────────

    async def get_loan(self, loan_id: UUID) -> Optional[CreditPortfolioLoan]:
        res = await self.session.execute(
            select(CreditPortfolioLoan).where(CreditPortfolioLoan.id == loan_id)
        )
        return res.scalar_one_or_none()

    async def get_first_active_loan(self) -> Optional[CreditPortfolioLoan]:
        res = await self.session.execute(
            select(CreditPortfolioLoan).where(
                CreditPortfolioLoan.deleted_at.is_(None),
                CreditPortfolioLoan.debt_usd.isnot(None),
            ).limit(1)
        )
        return res.scalar_one_or_none()

    async def list_active_loans(self) -> list[CreditPortfolioLoan]:
        res = await self.session.execute(
            select(CreditPortfolioLoan)
            .where(CreditPortfolioLoan.deleted_at.is_(None))
        )
        return list(res.scalars().all())

    async def list_loans_with_company_filtered(self, *, filters: list):
        res = await self.session.execute(
            select(CreditPortfolioLoan, Company.name_ru)
            .join(Company, Company.id == CreditPortfolioLoan.company_id, isouter=True)
            .where(and_(*filters))
        )
        return list(res.all())

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
