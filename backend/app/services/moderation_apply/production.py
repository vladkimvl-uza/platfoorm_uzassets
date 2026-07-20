"""Production apply handler — applies an approved company upsert.

Submission shape:
  target_module    = "production"
  target_entity_id = <company code>
  proposed_value   = { "year": int, "period": str, "lines": [ProductionLineIn, ...] }
"""
from __future__ import annotations

from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.repositories.production_repository import ProductionRepository
from app.schemas.production import ProductionUpsert
from app.services.moderation_service import register_apply_handler

_FIELDS = ("name", "unit", "total", "parent", "baseN", "baseM",
           "planN", "planM", "expN", "expM", "factN", "factM")


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    code = (sub.target_entity_id or "").lower()
    if not code:
        raise ValueError("target_entity_id (company code) missing")
    try:
        payload = ProductionUpsert.model_validate(sub.proposed_value)
    except Exception as e:
        raise ValueError(f"proposed_value does not match ProductionUpsert: {e}") from e

    year, period = payload.year, (payload.period or "h1")
    lines = [{k: getattr(l, k) for k in _FIELDS} for l in payload.lines]

    repo = ProductionRepository(db)
    snap = await repo.load_snapshot()
    snap = [
        e for e in snap
        if not (isinstance(e, dict) and (e.get("k") or "").lower() == code
                and e.get("year") == year and (e.get("period") or "h1") == period)
    ]
    snap.append({"k": code, "year": year, "period": period, "lines": lines})
    await repo.save_snapshot(snap)
    await db.commit()
    return {"code": code, "year": year, "period": period, "lines": len(lines)}


register_apply_handler("production", apply)
