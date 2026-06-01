"""KPI apply handler (Pack 148-followup B1).

Applies an approved moderation submission to the KPI store. Supports:
  - action="replace_year" / "edit": full (company_id, year) tree replacement
    matching the shape of PUT /kpi/{company_id}/{year}.

Submission shape expected:
  sub.target_module     = "kpi"
  sub.target_entity_id  = <company_id UUID string>
  sub.proposed_value    = {
      "company_id": "<uuid>",
      "year":       2026,
      "managers":   [ {... mirroring KpiManagerUpsert ...}, ... ],
  }

If the shape is wrong, raise ValueError — _dispatch_apply will mark the
submission as `apply_status='failed'` with the error in `apply_error`.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete

from app.models.bp_kpi import KpiIndicator, KpiManager
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.bp_kpi import KpiCompanyYearUpsert
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")

    # Validate via the same Pydantic schema the live route uses.
    try:
        payload = KpiCompanyYearUpsert.model_validate(sub.proposed_value)
    except Exception as e:
        raise ValueError(f"proposed_value does not match KpiCompanyYearUpsert: {e}") from e

    # Cross-check with target_entity_id if set.
    if sub.target_entity_id:
        try:
            entity_uuid = UUID(sub.target_entity_id)
        except Exception:
            entity_uuid = None
        if entity_uuid and entity_uuid != payload.company_id:
            raise ValueError(
                f"target_entity_id {sub.target_entity_id} != payload.company_id {payload.company_id}",
            )

    # Wipe + reinsert (mirror of replace_company_year).
    await db.execute(
        delete(KpiManager)
        .where(KpiManager.company_id == payload.company_id)
        .where(KpiManager.year == payload.year)
    )

    inserted_mgr = 0
    inserted_ind = 0
    for mi, m in enumerate(payload.managers):
        mgr = KpiManager(
            company_id=payload.company_id,
            year=payload.year,
            sort_order=m.sort_order if m.sort_order is not None else mi,
            title=m.title,
            short_title=m.short_title,
            role=m.role,
        )
        db.add(mgr)
        await db.flush()
        for ii, ind in enumerate(m.indicators):
            db.add(KpiIndicator(
                manager_id=mgr.id,
                sort_order=ind.sort_order if ind.sort_order is not None else ii,
                name=ind.name,
                unit=ind.unit,
                weight=ind.weight,
                plan_year=ind.plan_year,
                fact_year=ind.fact_year,
                q1_weight=ind.q1_weight, q2_weight=ind.q2_weight,
                q3_weight=ind.q3_weight, q4_weight=ind.q4_weight,
                q1_plan=ind.q1_plan, q1_fact=ind.q1_fact,
                q2_plan=ind.q2_plan, q2_fact=ind.q2_fact,
                q3_plan=ind.q3_plan, q3_fact=ind.q3_fact,
                q4_plan=ind.q4_plan, q4_fact=ind.q4_fact,
                notes=ind.notes,
            ))
            inserted_ind += 1
        inserted_mgr += 1

    await db.commit()
    return {
        "company_id": str(payload.company_id),
        "year": payload.year,
        "managers_written": inserted_mgr,
        "indicators_written": inserted_ind,
    }


register_apply_handler("kpi", apply)
