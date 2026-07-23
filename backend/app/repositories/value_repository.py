"""Data access for the Value Opportunities registry."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company
from app.models.value import ValueOpportunity


class ValueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        status: Optional[str] = None,
        source: Optional[str] = None,
        company_id: Optional[UUID] = None,
        scope_company_ids: Optional[Sequence[UUID]] = None,
    ) -> list[tuple[ValueOpportunity, Optional[Company]]]:
        q = (
            select(ValueOpportunity, Company)
            .outerjoin(Company, ValueOpportunity.company_id == Company.id)
            .options(selectinload(Company.sector))
            .order_by(ValueOpportunity.created_at.desc())
        )
        if status:
            q = q.where(ValueOpportunity.status == status)
        if source:
            q = q.where(ValueOpportunity.source == source)
        if company_id:
            q = q.where(ValueOpportunity.company_id == company_id)
        if scope_company_ids is not None:
            # scope: свои компании ИЛИ портфельные (company_id IS NULL)
            q = q.where(
                (ValueOpportunity.company_id.in_(scope_company_ids))
                | (ValueOpportunity.company_id.is_(None))
            )
        rows = (await self.session.execute(q)).all()
        return [(opp, co) for opp, co in rows]

    async def get(self, opp_id: UUID) -> Optional[ValueOpportunity]:
        res = await self.session.execute(
            select(ValueOpportunity).where(ValueOpportunity.id == opp_id)
        )
        return res.scalar_one_or_none()

    async def company_for(self, company_id: UUID) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).options(selectinload(Company.sector)).where(Company.id == company_id)
        )
        return res.scalar_one_or_none()

    def add(self, opp: ValueOpportunity) -> None:
        self.session.add(opp)

    async def flush(self) -> None:
        await self.session.flush()

    async def delete(self, opp_id: UUID) -> None:
        await self.session.execute(
            delete(ValueOpportunity).where(ValueOpportunity.id == opp_id)
        )

    async def find_fingerprints(self, fingerprints: Sequence[str]) -> set[str]:
        """Существующие отпечатки (для дедупа авто-генерации)."""
        if not fingerprints:
            return set()
        res = await self.session.execute(
            select(ValueOpportunity.fingerprint).where(
                ValueOpportunity.fingerprint.in_(list(fingerprints))
            )
        )
        return {fp for (fp,) in res.all() if fp}
