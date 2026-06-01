"""Ratings apply handler (Pack 148-followup B1).

Dispatches by sub.action — 'create' / 'update' / 'delete' — to the matching
operation. Mirrors POST/PATCH/DELETE /ratings.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from app.models.agency_rating import AgencyRating
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.agency_rating import AgencyRatingCreate, AgencyRatingUpdate
from app.services.moderation_service import register_apply_handler


def _is_esg_agency(name: str) -> bool:
    """Mirror of routes/ratings.is_esg_agency — kept local to avoid circular imports."""
    n = (name or "").lower()
    return any(t in n for t in ("msci", "sustainalytics", "iss", "esg"))


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()

    if action == "create":
        payload = AgencyRatingCreate.model_validate(sub.proposed_value)
        # Conflict guard — same (company, agency) may have been created since.
        dup = (await db.execute(
            select(AgencyRating).where(
                AgencyRating.company_id == payload.company_id,
                func.lower(AgencyRating.agency) == payload.agency.lower(),
            )
        )).scalar_one_or_none()
        if dup is not None:
            raise ValueError(
                f"Rating {payload.agency} for this company already exists "
                f"(id={dup.id}). Use update instead.",
            )
        rec = AgencyRating(
            company_id=payload.company_id,
            agency=payload.agency.strip(),
            is_esg=_is_esg_agency(payload.agency),
            rating=payload.rating, outlook=payload.outlook, score=payload.score,
            rating_date_text=payload.rating_date_text, rating_date=payload.rating_date,
            report_url=payload.report_url,
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        return {"action": "create", "rating_id": str(rec.id)}

    if not sub.target_entity_id:
        raise ValueError("missing target_entity_id for ratings update/delete")
    try:
        rid = UUID(sub.target_entity_id)
    except Exception as e:
        raise ValueError(f"invalid target_entity_id: {sub.target_entity_id}") from e

    rec = (await db.execute(
        select(AgencyRating).where(AgencyRating.id == rid)
    )).scalar_one_or_none()
    if rec is None:
        raise ValueError(f"Rating {rid} no longer exists")

    if action == "update":
        payload = AgencyRatingUpdate.model_validate(sub.proposed_value)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(rec, field, value)
        await db.commit()
        return {"action": "update", "rating_id": str(rec.id)}

    if action == "delete":
        await db.delete(rec)
        await db.commit()
        return {"action": "delete", "rating_id": str(rid)}

    raise ValueError(f"unknown ratings action: {action!r}")


register_apply_handler("ratings", apply)
