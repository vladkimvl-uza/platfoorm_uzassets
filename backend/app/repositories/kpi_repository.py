"""KPI repository — все SQL-queries для KPI-модуля в одном месте.

Pattern: каждый метод — одна понятная операция над БД. Никаких
HTTP-вещей (HTTPException, Depends), никакой бизнес-логики (вычисления,
веса, статусы) — это всё в `services/kpi/`.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bp_kpi import KpiComment, KpiIndicator, KpiManager
from app.models.company import Company


class KpiRepository:
    """Data-access layer для KPI-модуля.

    Конвенции:
    - Не делает commit/rollback — это owns UnitOfWork.
    - Возвращает ORM-объекты (KpiManager, KpiComment, Company).
    - Не raise HTTPException — service-слой решает что делать с None.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── Companies + years inventory ──────────────────────────────

    async def distinct_company_years(self) -> list[tuple[UUID, int]]:
        """Возвращает unique (company_id, year) — каркас для available-companies."""
        rows = (await self.session.execute(
            select(KpiManager.company_id, KpiManager.year).distinct()
        )).all()
        return [(cid, yr) for cid, yr in rows]

    async def list_companies_with_sector(self, ids: Sequence[UUID]) -> list[Company]:
        """Pre-load sector relation чтобы services могли спокойно читать .sector."""
        if not ids:
            return []
        res = await self.session.execute(
            select(Company)
            .options(selectinload(Company.sector))
            .where(Company.id.in_(list(ids)))
            .where(Company.is_active.is_(True))
        )
        return list(res.scalars().all())

    async def list_all_companies_with_sector(self) -> list[Company]:
        """Все компании реестра (для пикера owner/admin — чтобы можно было
        завести KPI любой существующей компании, даже без данных)."""
        res = await self.session.execute(
            select(Company)
            .options(selectinload(Company.sector))
            .where(Company.is_active.is_(True))
        )
        return list(res.scalars().all())

    # ─── Managers + indicators tree (per company-year) ────────────

    async def get_managers_with_indicators(
        self, company_id: UUID, year: int,
    ) -> list[KpiManager]:
        """Дерево руководителей+индикаторов одной компании за год."""
        res = await self.session.execute(
            select(KpiManager)
            .where(KpiManager.company_id == company_id, KpiManager.year == year)
            .options(selectinload(KpiManager.indicators))
            .order_by(KpiManager.sort_order)
        )
        return list(res.scalars().all())

    async def get_summary_managers(
        self, year: int, scope_company_ids: Optional[set[UUID]] = None,
    ) -> list[KpiManager]:
        """Все managers за год (с companies+sector pre-loaded) для портфельной сводки."""
        q = (
            select(KpiManager)
            .where(KpiManager.year == year)
            .options(
                selectinload(KpiManager.indicators),
                selectinload(KpiManager.company).selectinload(Company.sector),
            )
            .order_by(KpiManager.company_id, KpiManager.sort_order)
        )
        if scope_company_ids is not None:
            q = q.where(KpiManager.company_id.in_(scope_company_ids))
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def count_managers(self, company_id: UUID, year: int) -> int:
        res = await self.session.execute(
            select(func.count())
            .select_from(KpiManager)
            .where(KpiManager.company_id == company_id, KpiManager.year == year)
        )
        return int(res.scalar_one())

    # ─── Mutations ────────────────────────────────────────────────

    async def delete_year(self, company_id: UUID, year: int) -> None:
        await self.session.execute(
            delete(KpiManager)
            .where(KpiManager.company_id == company_id, KpiManager.year == year)
        )

    async def delete_comments_for_year(self, company_id: UUID, year: int) -> None:
        await self.session.execute(
            delete(KpiComment)
            .where(KpiComment.company_id == company_id, KpiComment.year == year)
        )

    async def add_manager(self, manager: KpiManager) -> KpiManager:
        self.session.add(manager)
        await self.session.flush()  # populates id
        return manager

    async def add_indicator(self, indicator: KpiIndicator) -> None:
        self.session.add(indicator)

    # ─── Company lookup для template loading ──────────────────────

    async def get_company_by_code(self, code: str) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).where(func.lower(Company.code) == code.lower())
        )
        return res.scalar_one_or_none()

    # ─── Comments ─────────────────────────────────────────────────

    async def get_comment(
        self, company_id: UUID, year: int, period: str,
    ) -> Optional[KpiComment]:
        res = await self.session.execute(
            select(KpiComment)
            .where(KpiComment.company_id == company_id)
            .where(KpiComment.year == year)
            .where(KpiComment.period == period)
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
    ) -> KpiComment:
        stmt = pg_insert(KpiComment).values(
            company_id=company_id,
            year=year,
            period=period,
            body=body,
            author_id=author_id,
        ).on_conflict_do_update(
            index_elements=["company_id", "year", "period"],
            set_={"body": body, "author_id": author_id, "updated_at": func.now()},
        ).returning(KpiComment)
        res = await self.session.execute(stmt)
        return res.scalar_one()
