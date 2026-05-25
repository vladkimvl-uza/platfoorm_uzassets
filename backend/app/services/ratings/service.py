"""Use cases for Agency Ratings."""
from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from fastapi import HTTPException, status as http_status

from app.models.agency_rating import AgencyRating, is_esg_agency
from app.schemas.agency_rating import (
    AgencyRatingBrief, AgencyRatingCreate, AgencyRatingDetail,
    AgencyRatingListResponse, AgencyRatingUpdate, CompanyRatingsResponse,
)
from app.uow.ports import UnitOfWorkABC


def _row_to_brief(r: AgencyRating, company_code: Optional[str],
                  company_name: Optional[str]) -> AgencyRatingBrief:
    return AgencyRatingBrief(
        id=r.id, company_id=r.company_id,
        company_code=company_code, company_name=company_name,
        agency=r.agency, is_esg=r.is_esg,
        rating=r.rating, outlook=r.outlook, score=r.score,
        rating_date_text=r.rating_date_text, rating_date=r.rating_date,
        report_url=r.report_url,
        created_at=r.created_at, updated_at=r.updated_at,
    )


def _to_detail(rec: AgencyRating, brief: AgencyRatingBrief) -> AgencyRatingDetail:
    return AgencyRatingDetail(
        **brief.model_dump(),
        legacy_id=rec.legacy_id,
        legacy_board_id=rec.legacy_board_id,
        extra=rec.extra,
    )


class RatingsService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── list / per-company queries ───────────────────────────────

    async def list_ratings(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
        company_id: Optional[UUID],
        company_code: Optional[str],
        agency: Optional[str],
        is_esg: Optional[bool],
        search: Optional[str],
        sort_by: str,
        sort_dir: str,
        limit: int,
        offset: int,
    ) -> AgencyRatingListResponse:
        if scope_company_ids is not None and len(scope_company_ids) == 0:
            return AgencyRatingListResponse(
                items=[], total=0, by_agency={},
                credit_count=0, esg_count=0,
            )

        async with self.uow:
            rows, total = await self.uow.ratings.list_ratings(
                scope_company_ids=scope_company_ids,
                company_id=company_id, company_code=company_code,
                agency=agency, is_esg=is_esg, search=search,
                sort_by=sort_by, sort_dir=sort_dir,
                limit=limit, offset=offset,
            )
            items = [_row_to_brief(r.AgencyRating, r.co_code, r.co_name) for r in rows]

            facet_rows = await self.uow.ratings.facet_rows(
                scope_company_ids=scope_company_ids,
                company_id=company_id, company_code=company_code,
            )

        by_agency: dict[str, int] = {}
        by_company: dict[str, int] = {}
        credit_count = esg_count = 0
        for ag, esg, _cid, ccode in facet_rows:
            by_agency[ag] = by_agency.get(ag, 0) + 1
            if ccode:
                by_company[ccode] = by_company.get(ccode, 0) + 1
            if esg:
                esg_count += 1
            else:
                credit_count += 1

        return AgencyRatingListResponse(
            items=items, total=total,
            by_agency=by_agency, by_company=by_company,
            credit_count=credit_count, esg_count=esg_count,
        )

    async def get_company_ratings(
        self,
        code: str,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> CompanyRatingsResponse:
        async with self.uow:
            company = await self.uow.ratings.get_company_by_code(code)
            if not company:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Company '{code}' not found")
            if scope_company_ids is not None and company.id not in scope_company_ids:
                raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this company")
            all_ratings = await self.uow.ratings.list_company_ratings(company.id)

        credit, esg = [], []
        for r in all_ratings:
            brief = _row_to_brief(r, company.code, company.name_short)
            (esg if r.is_esg else credit).append(brief)

        return CompanyRatingsResponse(
            company_id=company.id, company_code=company.code,
            company_name=company.name_short or company.name_ru or company.code,
            credit=credit, esg=esg,
        )

    # ─── create / update / delete ─────────────────────────────────

    async def create_rating(
        self,
        payload: AgencyRatingCreate,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> tuple[AgencyRating, AgencyRatingDetail]:
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot create rating for a company outside your allowed list",
            )

        async with self.uow:
            company = await self.uow.ratings.get_company(payload.company_id)
            if not company:
                raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Company not found")

            dup = await self.uow.ratings.get_by_company_agency(payload.company_id, payload.agency)
            if dup:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Rating from {payload.agency} for this company already exists. Use PATCH to update.",
                )

            rec = AgencyRating(
                company_id=payload.company_id,
                agency=payload.agency.strip(),
                is_esg=is_esg_agency(payload.agency),
                rating=payload.rating, outlook=payload.outlook, score=payload.score,
                rating_date_text=payload.rating_date_text,
                rating_date=payload.rating_date,
                report_url=payload.report_url,
            )
            self.uow.ratings.add(rec)
            await self.uow.ratings.flush()
            await self.uow.ratings.refresh(rec)
            brief = _row_to_brief(rec, company.code, company.name_short)
            return rec, _to_detail(rec, brief)

    async def get_for_moderation(
        self,
        rating_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> AgencyRating:
        async with self.uow:
            rec = await self.uow.ratings.get(rating_id)
        if not rec:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Rating not found")
        if scope_company_ids is not None and rec.company_id not in scope_company_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this rating")
        return rec

    async def update_rating(
        self,
        rating_id: UUID,
        payload: AgencyRatingUpdate,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> tuple[AgencyRating, AgencyRatingDetail]:
        async with self.uow:
            rec = await self.uow.ratings.get(rating_id)
            if not rec:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Rating not found")
            if scope_company_ids is not None and rec.company_id not in scope_company_ids:
                raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this rating")

            for field, value in payload.model_dump(exclude_unset=True).items():
                setattr(rec, field, value)
            await self.uow.ratings.flush()
            await self.uow.ratings.refresh(rec)
            co_short = await self.uow.ratings.get_company_short(rec.company_id)
            cc = co_short.code if co_short else None
            cn = co_short.name_short if co_short else None
            brief = _row_to_brief(rec, cc, cn)
            return rec, _to_detail(rec, brief)

    async def delete_rating(
        self,
        rating_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> None:
        async with self.uow:
            rec = await self.uow.ratings.get(rating_id)
            if not rec:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Rating not found")
            if scope_company_ids is not None and rec.company_id not in scope_company_ids:
                raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this rating")
            await self.uow.ratings.delete(rec)
            await self.uow.ratings.flush()
