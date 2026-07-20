"""Data access for Agency Ratings."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency_rating import AgencyRating
from app.models.company import Company


class RatingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── single lookups ───────────────────────────────────────────

    async def get(self, rating_id: UUID) -> Optional[AgencyRating]:
        res = await self.session.execute(
            select(AgencyRating).where(AgencyRating.id == rating_id)
        )
        return res.scalar_one_or_none()

    async def get_by_company_agency(self, company_id: UUID, agency: str):
        res = await self.session.execute(
            select(AgencyRating).where(
                AgencyRating.company_id == company_id,
                func.lower(AgencyRating.agency) == agency.lower(),
            )
        )
        return res.scalar_one_or_none()

    async def get_company(self, company_id: UUID) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).where(Company.id == company_id)
        )
        return res.scalar_one_or_none()

    async def get_company_by_code(self, code: str) -> Optional[Company]:
        res = await self.session.execute(
            select(Company).where(func.lower(Company.code) == code.lower())
        )
        return res.scalar_one_or_none()

    async def get_company_short(self, company_id: UUID):
        return (await self.session.execute(
            select(Company.code, Company.name_short)
            .where(Company.id == company_id)
        )).first()

    # ─── list / filtering ─────────────────────────────────────────

    async def list_ratings(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
        agency: Optional[str] = None,
        is_esg: Optional[bool] = None,
        search: Optional[str] = None,
        sort_by: str = "rating_date",
        sort_dir: str = "desc",
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list, int]:
        q = (select(AgencyRating, Company.code.label("co_code"),
                    Company.name_short.label("co_name"))
             .outerjoin(Company, AgencyRating.company_id == Company.id))
        # Портфельный список (без явного фильтра по компании) не показывает
        # рейтинги деактивированных компаний; рейтинги-сироты (company_id NULL)
        # сохраняем. При явном фильтре по company_id/code — показываем как есть.
        if not company_id and not company_code:
            q = q.where(or_(Company.is_active.is_(True), AgencyRating.company_id.is_(None)))
        if scope_company_ids is not None:
            q = q.where(AgencyRating.company_id.in_(scope_company_ids))
        if company_id:
            q = q.where(AgencyRating.company_id == company_id)
        if company_code:
            q = q.where(func.lower(Company.code) == company_code.lower())
        if agency:
            q = q.where(func.lower(AgencyRating.agency) == agency.lower())
        if is_esg is not None:
            q = q.where(AgencyRating.is_esg.is_(is_esg))
        if search:
            s = f"%{search.strip().lower()}%"
            q = q.where(or_(
                func.lower(AgencyRating.rating).like(s),
                func.lower(AgencyRating.agency).like(s),
                func.lower(Company.name_ru).like(s),
                func.lower(Company.code).like(s),
            ))

        total = (await self.session.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        sort_col = {
            "rating_date":  AgencyRating.rating_date,
            "agency":       AgencyRating.agency,
            "company_code": Company.code,
            "updated_at":   AgencyRating.updated_at,
        }.get(sort_by, AgencyRating.rating_date)
        q = q.order_by(
            asc(sort_col).nulls_last() if sort_dir == "asc"
            else desc(sort_col).nulls_last()
        )
        q = q.limit(limit).offset(offset)
        rows = (await self.session.execute(q)).all()
        return rows, total

    async def facet_rows(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
    ):
        q = (select(AgencyRating.agency, AgencyRating.is_esg,
                    AgencyRating.company_id, Company.code)
             .outerjoin(Company, AgencyRating.company_id == Company.id))
        if not company_id and not company_code:
            q = q.where(or_(Company.is_active.is_(True), AgencyRating.company_id.is_(None)))
        if scope_company_ids is not None:
            q = q.where(AgencyRating.company_id.in_(scope_company_ids))
        if company_id:
            q = q.where(AgencyRating.company_id == company_id)
        if company_code:
            q = q.where(func.lower(Company.code) == company_code.lower())
        return (await self.session.execute(q)).all()

    async def list_company_ratings(self, company_id: UUID):
        res = await self.session.execute(
            select(AgencyRating)
            .where(AgencyRating.company_id == company_id)
            .order_by(AgencyRating.is_esg.asc(), AgencyRating.agency.asc())
        )
        return list(res.scalars().all())

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
