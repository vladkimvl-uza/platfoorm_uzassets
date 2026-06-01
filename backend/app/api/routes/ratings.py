"""Agency Ratings API — thin HTTP layer (refactored 2026-05-25).

Endpoints (URLs preserved):
  GET    /ratings                           list with filters
  GET    /companies/{code}/ratings          all ratings for one company
  POST   /ratings                           create new rating
  PATCH  /ratings/{id}                      update existing
  DELETE /ratings/{id}                      delete
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.dependencies.ratings import RatingsServiceDep
from app.models.agency_rating import AgencyRating
from app.models.user import User
from app.schemas.agency_rating import (
    AgencyRatingCreate,
    AgencyRatingDetail,
    AgencyRatingListResponse,
    AgencyRatingUpdate,
    CompanyRatingsResponse,
)

router = APIRouter(tags=["ratings"])
logger = logging.getLogger(__name__)


# Agency name (canonical) → library field_code
_AGENCY_TO_FIELD = {
    "fitch":              "rating_fitch",
    "s&p":                "rating_sp",
    "moody's":            "rating_moodys",
    "moodys":             "rating_moodys",
    "sustainable fitch":  "rating_esg",
}


async def _broadcast_rating_update(rec: AgencyRating, user) -> None:
    """Push field_update event to /ws/companies subscribers. Best-effort."""
    try:
        from app.services.sync_broadcaster import broadcaster
        key = (rec.agency or "").strip().lower()
        field_code = _AGENCY_TO_FIELD.get(key)
        if not field_code and rec.is_esg:
            field_code = "rating_esg"
        if not field_code:
            return
        value = rec.score if rec.is_esg else rec.rating
        await broadcaster.broadcast_field_update(
            company_id=str(rec.company_id),
            field_code=field_code,
            value=value,
            source_module="ratings",
            actor_id=str(getattr(user, "id", "")) or None,
        )
    except Exception:
        logger.warning("ratings library-sync broadcast failed", exc_info=True)


async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"Permission required: {code}")


async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else None


@router.get("/ratings", response_model=AgencyRatingListResponse)
async def list_ratings(
    service: RatingsServiceDep,
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    agency: Optional[str] = Query(None),
    is_esg: Optional[bool] = Query(None, description="True=ESG ratings only, False=credit only"),
    search: Optional[str] = Query(None),
    sort_by: str = Query("rating_date", regex="^(rating_date|agency|company_code|updated_at)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "ratings.view")
    return await service.list_ratings(
        scope_company_ids=await _scope(db, user),
        company_id=company_id, company_code=company_code,
        agency=agency, is_esg=is_esg, search=search,
        sort_by=sort_by, sort_dir=sort_dir,
        limit=limit, offset=offset,
    )


@router.get("/companies/{code}/ratings", response_model=CompanyRatingsResponse)
async def get_company_ratings(
    code: str,
    service: RatingsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "ratings.view")
    return await service.get_company_ratings(code, scope_company_ids=await _scope(db, user))


@router.post("/ratings", response_model=AgencyRatingDetail, status_code=http_status.HTTP_201_CREATED)
async def create_rating(
    payload: AgencyRatingCreate,
    service: RatingsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "ratings.edit")

    scope_ids = await _scope(db, user)
    if scope_ids is not None and payload.company_id not in scope_ids:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Cannot create rating for a company outside your allowed list",
        )

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="ratings", action="create",
        entity_id=None, entity_label=f"Рейтинг {payload.agency}",
        company_id=payload.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Новый рейтинг от {payload.agency}: {payload.rating}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status,
                     "message": "Изменение отправлено на модерацию"},
        )

    rec, detail = await service.create_rating(payload, scope_company_ids=scope_ids)
    await _broadcast_rating_update(rec, user)
    return detail


@router.patch("/ratings/{rating_id}", response_model=AgencyRatingDetail)
async def update_rating(
    rating_id: UUID,
    payload: AgencyRatingUpdate,
    service: RatingsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "ratings.edit")
    scope_ids = await _scope(db, user)

    rec_pre = await service.get_for_moderation(rating_id, scope_company_ids=scope_ids)

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="ratings", action="update",
        entity_id=str(rating_id),
        entity_label=f"Рейтинг {rec_pre.agency}",
        company_id=rec_pre.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json", exclude_unset=True),
        diff_summary=f"Обновление рейтинга {rec_pre.agency}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status,
                     "message": "Изменение отправлено на модерацию"},
        )

    rec, detail = await service.update_rating(rating_id, payload, scope_company_ids=scope_ids)
    await _broadcast_rating_update(rec, user)
    return detail


@router.delete("/ratings/{rating_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_rating(
    rating_id: UUID,
    service: RatingsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "ratings.edit")
    scope_ids = await _scope(db, user)

    rec_pre = await service.get_for_moderation(rating_id, scope_company_ids=scope_ids)

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="ratings", action="delete",
        entity_id=str(rating_id),
        entity_label=f"Рейтинг {rec_pre.agency}",
        company_id=rec_pre.company_id, sector_id=None, year=None,
        payload={"delete": True, "rating_id": str(rating_id)},
        diff_summary=f"Удаление рейтинга {rec_pre.agency}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status,
                     "message": "Удаление отправлено на модерацию"},
        )

    await service.delete_rating(rating_id, scope_company_ids=scope_ids)
