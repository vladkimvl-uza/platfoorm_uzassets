"""Subsidies registry service — list / summary / CRUD.

Тонкий слой поверх AsyncSession (queries здесь, не в роутере). Scope-фильтрация
по allowed_company_ids передаётся из маршрута.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company, Sector
from app.models.subsidies import Subsidy
from app.models.user import User
from app.schemas.subsidies import (
    SubsidyCompanyAgg,
    SubsidyPatch,
    SubsidyRow,
    SubsidySectorAgg,
    SubsidySummary,
    SubsidyUpsert,
)


def _company_name(c: Optional[Company]) -> Optional[str]:
    if c is None:
        return None
    return c.name_short or c.name_ru


class SubsidiesService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── queries ──────────────────────────────────────────────────

    async def _fetch(
        self,
        *,
        year: Optional[int],
        sector_code: Optional[str],
        company_id: Optional[UUID],
        scope_ids: Optional[Sequence[UUID]],
    ) -> list[tuple[Subsidy, Company, Optional[Sector]]]:
        q = (
            select(Subsidy, Company, Sector)
            .join(Company, Subsidy.company_id == Company.id)
            .outerjoin(Sector, Company.sector_id == Sector.id)
        )
        if year is not None:
            q = q.where(Subsidy.year == year)
        if company_id is not None:
            q = q.where(Subsidy.company_id == company_id)
        if sector_code:
            q = q.where(func.lower(Sector.code) == sector_code.lower())
        if scope_ids is not None:
            q = q.where(Subsidy.company_id.in_(list(scope_ids)))
        q = q.order_by(Subsidy.year.desc().nullslast(), Subsidy.allocation_date.desc().nullslast())
        res = await self.db.execute(q)
        return list(res.all())

    @staticmethod
    def _row(s: Subsidy, c: Company, sec: Optional[Sector]) -> SubsidyRow:
        return SubsidyRow(
            id=s.id,
            company_id=s.company_id,
            company_name=_company_name(c),
            company_code=c.code if c else None,
            sector_code=sec.code if sec else None,
            sector_name=(sec.name_ru if sec else None),
            sector_color=(sec.color_hex if sec else None),
            year=s.year,
            amount=s.amount,
            program=s.program,
            source=s.source,
            kind=s.kind,
            status=s.status,
            allocation_date=s.allocation_date,
            note=s.note,
            created_by_name=s.created_by_name,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )

    async def list_rows(
        self,
        *,
        year: Optional[int] = None,
        sector_code: Optional[str] = None,
        company_id: Optional[UUID] = None,
        scope_ids: Optional[Sequence[UUID]] = None,
    ) -> list[SubsidyRow]:
        rows = await self._fetch(
            year=year, sector_code=sector_code, company_id=company_id, scope_ids=scope_ids,
        )
        return [self._row(s, c, sec) for (s, c, sec) in rows]

    async def summary(
        self,
        *,
        year: Optional[int] = None,
        sector_code: Optional[str] = None,
        scope_ids: Optional[Sequence[UUID]] = None,
    ) -> SubsidySummary:
        rows = await self._fetch(
            year=year, sector_code=sector_code, company_id=None, scope_ids=scope_ids,
        )
        # Демо/непрофильные компании (include_in_rollups=false) не должны искажать портфельные суммы (в реестре list_rows они остаются видимыми).
        rows = [(s, c, sec) for (s, c, sec) in rows if c is None or c.include_in_rollups]
        total = Decimal(0)
        by_co: dict[UUID, SubsidyCompanyAgg] = {}
        by_sec: dict[str, SubsidySectorAgg] = {}
        for (s, c, sec) in rows:
            amt = s.amount or Decimal(0)
            total += amt
            # by company
            agg = by_co.get(s.company_id)
            if agg is None:
                agg = SubsidyCompanyAgg(
                    company_id=s.company_id,
                    company_name=_company_name(c),
                    company_code=c.code if c else None,
                    sector_code=sec.code if sec else None,
                    sector_name=(sec.name_ru if sec else None),
                    sector_color=(sec.color_hex if sec else None),
                    total=Decimal(0),
                    count=0,
                )
                by_co[s.company_id] = agg
            agg.total = (agg.total or Decimal(0)) + amt
            agg.count += 1
            # by sector
            sk = (sec.code if sec else "—") or "—"
            sagg = by_sec.get(sk)
            if sagg is None:
                sagg = SubsidySectorAgg(
                    sector_code=(sec.code if sec else None),
                    sector_name=(sec.name_ru if sec else None),
                    sector_color=(sec.color_hex if sec else None),
                    total=Decimal(0),
                    count=0,
                )
                by_sec[sk] = sagg
            sagg.total = (sagg.total or Decimal(0)) + amt
            sagg.count += 1

        return SubsidySummary(
            year=year,
            sector_code=sector_code,
            total=total,
            count=len(rows),
            by_company=sorted(by_co.values(), key=lambda a: a.total or Decimal(0), reverse=True),
            by_sector=sorted(by_sec.values(), key=lambda a: a.total or Decimal(0), reverse=True),
        )

    # ─── mutations ────────────────────────────────────────────────

    async def _get_with_join(self, subsidy_id: UUID) -> tuple[Subsidy, Company, Optional[Sector]]:
        res = await self.db.execute(
            select(Subsidy, Company, Sector)
            .join(Company, Subsidy.company_id == Company.id)
            .outerjoin(Sector, Company.sector_id == Sector.id)
            .where(Subsidy.id == subsidy_id)
        )
        row = res.first()
        if row is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Subsidy not found")
        return row  # type: ignore[return-value]

    @staticmethod
    def _check_scope(company_id: UUID, scope_ids: Optional[Sequence[UUID]]) -> None:
        if scope_ids is not None and company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this company")

    async def create(
        self,
        payload: SubsidyUpsert,
        user: User,
        *,
        scope_ids: Optional[Sequence[UUID]] = None,
    ) -> SubsidyRow:
        self._check_scope(payload.company_id, scope_ids)
        # company must exist
        comp = await self.db.get(Company, payload.company_id)
        if comp is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
        row = Subsidy(
            company_id=payload.company_id,
            year=payload.year,
            amount=(Decimal(str(payload.amount)) if payload.amount is not None else None),
            program=payload.program,
            source=payload.source,
            kind=payload.kind,
            status=payload.status,
            allocation_date=payload.allocation_date,
            note=payload.note,
            created_by=user.id,
            created_by_name=(
                getattr(user, "full_name", None)
                or getattr(user, "username", None)
                or getattr(user, "email", None)
            ),
        )
        self.db.add(row)
        await self.db.commit()
        s, c, sec = await self._get_with_join(row.id)
        return self._row(s, c, sec)

    async def update(
        self,
        subsidy_id: UUID,
        patch: SubsidyPatch,
        *,
        scope_ids: Optional[Sequence[UUID]] = None,
    ) -> SubsidyRow:
        s, c, sec = await self._get_with_join(subsidy_id)
        self._check_scope(s.company_id, scope_ids)
        data = patch.model_dump(exclude_unset=True)
        for key, val in data.items():
            if key == "amount":
                s.amount = Decimal(str(val)) if val is not None else None
            else:
                setattr(s, key, val)
        await self.db.commit()
        s2, c2, sec2 = await self._get_with_join(subsidy_id)
        return self._row(s2, c2, sec2)

    async def delete(
        self,
        subsidy_id: UUID,
        *,
        scope_ids: Optional[Sequence[UUID]] = None,
    ) -> None:
        s, _c, _sec = await self._get_with_join(subsidy_id)
        self._check_scope(s.company_id, scope_ids)
        await self.db.execute(sa_delete(Subsidy).where(Subsidy.id == subsidy_id))
        await self.db.commit()
