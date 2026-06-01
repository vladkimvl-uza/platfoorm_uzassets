"""Business-plan apply handler (Pack 148-followup B1).

Applies an approved BP bulk-upsert submission. Mirrors POST /bp/bulk-upsert.

Submission shape:
  target_module    = "business_plan"
  target_entity_id = <company_id UUID string>
  proposed_value   = { "records": [BpRecordUpsert, ...] }
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.bp_kpi import BpRecord
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.bp_kpi import BpBulkUpsert
from app.services.moderation_service import register_apply_handler

# Mirror the validation lists from routes/business_plan.py
BP_PERIODS = {"year", "q1", "q2", "q3", "q4"}
BP_METRIC_KEYS = {"revenue", "ebitda", "net_income", "capex", "opex", "fcf",
                  "debt", "equity", "assets", "cash", "headcount"}


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")

    try:
        payload = BpBulkUpsert.model_validate(sub.proposed_value)
    except Exception as e:
        raise ValueError(f"proposed_value does not match BpBulkUpsert: {e}") from e

    n = 0
    for rec in payload.records:
        if rec.period not in BP_PERIODS or rec.metric not in BP_METRIC_KEYS:
            continue
        stmt = pg_insert(BpRecord).values(
            company_id=rec.company_id, year=rec.year,
            period=rec.period, metric=rec.metric,
            plan=rec.plan, expect=rec.expect, fact=rec.fact,
        ).on_conflict_do_update(
            index_elements=["company_id", "year", "period", "metric"],
            set_={
                "plan": rec.plan, "expect": rec.expect, "fact": rec.fact,
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
        n += 1
    await db.commit()
    return {"upserted": n}


register_apply_handler("business_plan", apply)
