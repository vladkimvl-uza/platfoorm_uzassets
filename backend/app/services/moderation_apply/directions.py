"""Directions apply handler (deny-by-default Phase 4).

Применяет одобренную правку глобального справочника «Направления». Зеркалит
POST /directions (create), PATCH /directions/{id} (edit), DELETE /directions/{id}
(delete + опциональный reassign). DirectionsService пишет в ТУ ЖЕ сессию, что и
получает (как unit_cost), и коммитит сам.

Атрибуция аудита — ПРЕДЛОЖИВШИЙ (proposer), а не модератор, нажавший «принять».
Сервис ещё раз прогоняет `_require_admin(proposer)` — если у автора отозвали
право между предложением и одобрением, apply падает (fail-closed).

«Направления» — ГЛОБАЛЬНЫЙ справочник без привязки к компании, поэтому
target_company_id всегда None и маппинг в `_effective_company_id` НЕ нужен.

Submission shape:
  target_module    = "directions"
  target_entity_id = <direction id>  (create: штампуется id созданного)
  proposed_value:
    create → поля DirectionIn
    edit   → поля DirectionPatch (exclude_unset — частичный патч сохраняется)
    delete → {"reassign_to": <code|null>}
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.company import Direction
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.directions.service import (
    DirectionIn,
    DirectionPatch,
    DirectionsService,
)
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value or {})

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user
    service = DirectionsService()

    if action in ("create", "created"):
        # Идемпотентность повтора: если прошлый apply уже создал направление и
        # застолбил его id в target_entity_id, повтор НЕ создаёт дубль.
        if sub.target_entity_id:
            try:
                did = uuid.UUID(str(sub.target_entity_id))
            except Exception:
                did = None
            if did is not None:
                exists = (await db.execute(
                    select(Direction.id).where(Direction.id == did)
                )).scalar_one_or_none()
                if exists is not None:
                    return {"action": "create", "direction_id": str(did),
                            "idempotent": True}
        payload = DirectionIn.model_validate(pv)
        res = await service.create_direction(payload, db, author)
        # застолбить id (коммитит _dispatch_apply) — как в companies.create
        sub.target_entity_id = str(res.get("id"))
        return {"action": "create", "direction_id": res.get("id"),
                "code": res.get("code")}

    if not sub.target_entity_id:
        raise ValueError("directions apply requires target_entity_id (direction id)")
    direction_id = uuid.UUID(str(sub.target_entity_id))

    if action in ("edit", "update"):
        payload = DirectionPatch.model_validate(pv)
        res = await service.update_direction(direction_id, payload, db, author)
        return {"action": "edit", "direction_id": str(direction_id),
                "code": res.get("code")}

    if action in ("delete", "archived"):
        reassign_to = pv.get("reassign_to")
        await service.delete_direction(direction_id, reassign_to, db, author)
        return {"action": "delete", "direction_id": str(direction_id)}

    raise ValueError(f"unknown directions action: {action!r}")


register_apply_handler("directions", apply)
