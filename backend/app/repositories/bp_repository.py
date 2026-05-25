"""Data access for Business Plan domain."""
from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bp_kpi import BpComment, BpRecord
from app.models.company import Company


class BpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── companies that have BP data ──────────────────────────────

    async def list_company_year_pairs(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
    ):
        q = select(BpRecord.company_id, BpRecord.year).distinct()
        if scope_company_ids is not None:
            q = q.where(BpRecord.company_id.in_(scope_company_ids))
        return (await self.session.execute(q)).all()

    async def list_companies_with_sector(self, company_ids: Sequence[UUID]):
        if not company_ids:
            return []
        rows = await self.session.execute(
            select(Company)
            .options(selectinload(Company.sector))
            .where(Company.id.in_(company_ids))
        )
        return list(rows.scalars().all())

    async def distinct_companies_with_bp(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
    ) -> list[UUID]:
        q = select(BpRecord.company_id).distinct()
        if scope_company_ids is not None:
            q = q.where(BpRecord.company_id.in_(scope_company_ids))
        return [r[0] for r in (await self.session.execute(q)).all()]

    # ─── raw records (editor) ─────────────────────────────────────

    async def list_records_for_year(
        self,
        company_id: UUID,
        year: int,
    ) -> list[BpRecord]:
        rows = await self.session.execute(
            select(BpRecord)
            .where(BpRecord.company_id == company_id)
            .where(BpRecord.year == year)
        )
        return list(rows.scalars().all())

    # ─── upserts ──────────────────────────────────────────────────

    async def upsert_record(
        self,
        *,
        company_id: UUID,
        year: int,
        period: str,
        metric: str,
        plan,
        expect,
        fact,
    ) -> None:
        stmt = pg_insert(BpRecord).values(
            company_id=company_id, year=year, period=period, metric=metric,
            plan=plan, expect=expect, fact=fact,
        ).on_conflict_do_update(
            index_elements=["company_id", "year", "period", "metric"],
            set_={
                "plan": plan, "expect": expect, "fact": fact,
                "updated_at": func.now(),
            },
        )
        await self.session.execute(stmt)

    async def delete_year(self, company_id: UUID, year: int) -> None:
        await self.session.execute(
            delete(BpRecord)
            .where(BpRecord.company_id == company_id)
            .where(BpRecord.year == year)
        )
        await self.session.execute(
            delete(BpComment)
            .where(BpComment.company_id == company_id)
            .where(BpComment.year == year)
        )

    # ─── comments ─────────────────────────────────────────────────

    async def get_comment(
        self,
        company_id: UUID,
        year: int,
        period: str,
    ) -> Optional[BpComment]:
        res = await self.session.execute(
            select(BpComment)
            .where(BpComment.company_id == company_id)
            .where(BpComment.year == year)
            .where(BpComment.period == period)
        )
        return res.scalar_one_or_none()

    async def upsert_comment(
        self,
        *,
        company_id: UUID,
        year: int,
        period: str,
        body: str,
        author_id: UUID,
    ) -> BpComment:
        stmt = pg_insert(BpComment).values(
            company_id=company_id, year=year, period=period,
            body=body, author_id=author_id,
        ).on_conflict_do_update(
            index_elements=["company_id", "year", "period"],
            set_={"body": body, "author_id": author_id, "updated_at": func.now()},
        ).returning(BpComment)
        return (await self.session.execute(stmt)).scalar_one()

    async def flush(self) -> None:
        await self.session.flush()
