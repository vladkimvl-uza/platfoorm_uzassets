"""Unit-cost apply handler (deny-by-default Phase 0).

Применяет одобренную правку удельной себестоимости компании. Зеркалит
PUT /unit-cost/companies/{code} (UnitCostService.save_company — снапшот в
system_config, period-keyed JSONB).

Submission shape:
  target_module    = "unit_cost"
  target_entity_id = <company code>
  proposed_value   = {"code","year","quarter","products","imports","comments"}

Атрибуция: автор правки — ПРЕДЛОЖИВШИЙ (proposer), а не модератор, нажавший
«принять» — новые комментарии и запись аудита должны вести к автору. Scope
модератора уже проверен на resolve (in_resolve_scope резолвит компанию по коду
для unit_cost), поэтому в save_company передаём cid_in_scope=True.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.moderation_service import register_apply_handler
from app.services.unit_cost.service import UnitCostService


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    pv = dict(sub.proposed_value)
    code = str(pv.get("code") or sub.target_entity_id or "").strip()
    if not code:
        raise ValueError("unit_cost apply requires company code")

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author_email = getattr(proposer, "email", None) or getattr(user, "email", "") or ""
    author_id = str(sub.proposer_user_id) if sub.proposer_user_id else None

    await UnitCostService().save_company(
        db, code,
        pv.get("products") or [], pv.get("imports") or [], pv.get("comments") or [],
        year=int(pv.get("year") or 2025), quarter=str(pv.get("quarter") or "annual"),
        cid_in_scope=True,
        user_email=author_email, user_id=author_id,
    )
    return {"module": "unit_cost", "code": code,
            "year": pv.get("year"), "quarter": pv.get("quarter")}


register_apply_handler("unit_cost", apply)
