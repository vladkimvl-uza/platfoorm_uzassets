"""Agency ratings API — external public ratings (credit + ESG).

Endpoints:
  GET    /ratings                           list with filters
  GET    /companies/{code}/ratings          all ratings for one company (split by category)
  POST   /ratings                           create new rating
  PATCH  /ratings/{id}                      update existing
  DELETE /ratings/{id}                      delete
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import _has_permission, get_current_user, has_effective_permission
from app.database import get_db
from app.models.agency_rating import AgencyRating, ESG_AGENCIES, is_esg_agency
from app.models.company import Company
from app.models.user import User
from app.schemas.agency_rating import (
    AgencyRatingBrief, AgencyRatingCreate, AgencyRatingDetail,
    AgencyRatingListResponse, AgencyRatingUpdate, CompanyRatingsResponse,
)


router = APIRouter(tags=["ratings"])


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


@router.get("/ratings", response_model=AgencyRatingListResponse)
async def list_ratings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    agency: Optional[str] = Query(None),
    is_esg: Optional[bool] = Query(None, description="True=ESG ratings only, False=credit only"),
    search: Optional[str] = Query(None),
    sort_by: str = Query("rating_date", regex="^(rating_date|agency|company_code|updated_at)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    if not await has_effective_permission(db, user, "ratings.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: ratings.view")

    # Per-company scope
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None and len(scope_ids) == 0:
        return AgencyRatingListResponse(items=[], total=0, by_agency={}, by_esg={"esg": 0, "credit": 0})

    q = (select(AgencyRating, Company.code.label("co_code"), Company.name_short.label("co_name"))
         .outerjoin(Company, AgencyRating.company_id == Company.id))

    if scope_ids is not None:
        q = q.where(AgencyRating.company_id.in_(scope_ids))

    if company_id:    q = q.where(AgencyRating.company_id == company_id)
    if company_code:  q = q.where(func.lower(Company.code) == company_code.lower())
    if agency:        q = q.where(func.lower(AgencyRating.agency) == agency.lower())
    if is_esg is not None: q = q.where(AgencyRating.is_esg.is_(is_esg))
    if search:
        s = f"%{search.strip().lower()}%"
        q = q.where(or_(
            func.lower(AgencyRating.rating).like(s),
            func.lower(AgencyRating.agency).like(s),
            func.lower(Company.name_ru).like(s),
            func.lower(Company.code).like(s),
        ))

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()

    sort_col = {
        "rating_date":  AgencyRating.rating_date,
        "agency":       AgencyRating.agency,
        "company_code": Company.code,
        "updated_at":   AgencyRating.updated_at,
    }.get(sort_by, AgencyRating.rating_date)
    q = q.order_by(asc(sort_col).nulls_last() if sort_dir == "asc" else desc(sort_col).nulls_last())
    q = q.limit(limit).offset(offset)

    rows = (await db.execute(q)).all()
    items = [_row_to_brief(r.AgencyRating, r.co_code, r.co_name) for r in rows]

    # Aggregates
    facet_q = (select(AgencyRating.agency, AgencyRating.is_esg, AgencyRating.company_id, Company.code)
               .outerjoin(Company, AgencyRating.company_id == Company.id))
    if scope_ids is not None: facet_q = facet_q.where(AgencyRating.company_id.in_(scope_ids))
    if company_id:    facet_q = facet_q.where(AgencyRating.company_id == company_id)
    if company_code:  facet_q = facet_q.where(func.lower(Company.code) == company_code.lower())
    facet_rows = (await db.execute(facet_q)).all()

    by_agency: dict[str, int] = {}
    by_company: dict[str, int] = {}
    credit_count = 0
    esg_count = 0
    for ag, esg, _cid, ccode in facet_rows:
        by_agency[ag] = by_agency.get(ag, 0) + 1
        if ccode:
            by_company[ccode] = by_company.get(ccode, 0) + 1
        if esg: esg_count += 1
        else:   credit_count += 1

    return AgencyRatingListResponse(
        items=items, total=total,
        by_agency=by_agency, by_company=by_company,
        credit_count=credit_count, esg_count=esg_count,
    )


@router.get("/companies/{code}/ratings", response_model=CompanyRatingsResponse)
async def get_company_ratings(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "ratings.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: ratings.view")

    co_q = await db.execute(
        select(Company).where(func.lower(Company.code) == code.lower())
    )
    company = co_q.scalar_one_or_none()
    if not company:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Company '{code}' not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None and company.id not in scope_ids:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this company")

    rat_q = await db.execute(
        select(AgencyRating)
        .where(AgencyRating.company_id == company.id)
        .order_by(AgencyRating.is_esg.asc(), AgencyRating.agency.asc())
    )
    all_ratings = list(rat_q.scalars().all())

    credit = []
    esg    = []
    for r in all_ratings:
        brief = _row_to_brief(r, company.code, company.name_short)
        (esg if r.is_esg else credit).append(brief)

    return CompanyRatingsResponse(
        company_id=company.id, company_code=company.code,
        company_name=company.name_short or company.name_ru or company.code,
        credit=credit, esg=esg,
    )


@router.post("/ratings", response_model=AgencyRatingDetail, status_code=http_status.HTTP_201_CREATED)
async def create_rating(
    payload: AgencyRatingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "ratings.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: ratings.edit")

    # Per-company scope: scoped users can only create ratings for allowed companies
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None and payload.company_id not in scope_ids:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Cannot create rating for a company outside your allowed list",
        )

    # Verify company exists
    co_q = await db.execute(select(Company).where(Company.id == payload.company_id))
    company = co_q.scalar_one_or_none()
    if not company:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Company not found")

    # Conflict: same (company, agency) already exists?
    dup_q = await db.execute(
        select(AgencyRating).where(
            AgencyRating.company_id == payload.company_id,
            func.lower(AgencyRating.agency) == payload.agency.lower(),
        )
    )
    if dup_q.scalar_one_or_none():
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Rating from {payload.agency} for this company already exists. "
            "Use PATCH to update.",
        )

    rec = AgencyRating(
        company_id=payload.company_id,
        agency=payload.agency.strip(),
        is_esg=is_esg_agency(payload.agency),
        rating=payload.rating, outlook=payload.outlook, score=payload.score,
        rating_date_text=payload.rating_date_text, rating_date=payload.rating_date,
        report_url=payload.report_url,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)

    base = _row_to_brief(rec, company.code, company.name_short)
    return AgencyRatingDetail(**base.model_dump(),
                              legacy_id=rec.legacy_id, legacy_board_id=rec.legacy_board_id,
                              extra=rec.extra)


@router.patch("/ratings/{rating_id}", response_model=AgencyRatingDetail)
async def update_rating(
    rating_id: UUID,
    payload: AgencyRatingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "ratings.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: ratings.edit")

    res = await db.execute(select(AgencyRating).where(AgencyRating.id == rating_id))
    rec = res.scalar_one_or_none()
    if not rec:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Rating not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None and rec.company_id not in scope_ids:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this rating")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(rec, field, value)

    await db.commit()
    await db.refresh(rec)

    co_q = await db.execute(
        select(Company.code, Company.name_short).where(Company.id == rec.company_id)
    )
    co = co_q.first()
    company_code = co.code if co else None
    company_name = co.name_short if co else None

    base = _row_to_brief(rec, company_code, company_name)
    return AgencyRatingDetail(**base.model_dump(),
                              legacy_id=rec.legacy_id, legacy_board_id=rec.legacy_board_id,
                              extra=rec.extra)


@router.delete("/ratings/{rating_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_rating(
    rating_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "ratings.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: ratings.edit")

    res = await db.execute(select(AgencyRating).where(AgencyRating.id == rating_id))
    rec = res.scalar_one_or_none()
    if not rec:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Rating not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None and rec.company_id not in scope_ids:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this rating")

    await db.delete(rec)
    await db.commit()
