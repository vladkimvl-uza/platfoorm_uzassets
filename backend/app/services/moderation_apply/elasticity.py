"""Elasticity apply handler (deny-by-default Phase 4).

Применяет одобренную правку эластичности / проектных эффектов. Зеркалит
PUT /elasticity/coefficients, DELETE /elasticity/coefficients/{id},
PUT /elasticity/project-effects, DELETE /elasticity/project-effects/{id}
через ElasticityService (тот же db-сеанс, что и live-роут).

Submission shape:
  target_module    = "elasticity"
  action           = "edit" (оба upsert) | "delete" (оба delete)
  target_entity_id = <coef_id|effect_id> для delete, None для upsert
  proposed_value   = model_dump(...) + дискриминатор "_kind":
                       "coefficient" | "project_effect"
                     (для delete также "id": <uuid>)

Дискриминатор нужен, потому что бакет-A даёт обоим upsert-роутам одно
действие "edit", а обоим delete — "delete" (см. core.moderation_routes),
и по одному лишь action нельзя понять, коэффициент это или проектный эффект.

Атрибуция: автор — ПРЕДЛОЖИВШИЙ (proposer), а не модератор. Сервис жёстко
зовёт `_admin_only(user)`, поэтому proposer грузим ВМЕСТЕ с ролями
(selectinload), иначе ленивое обращение к user.roles упало бы в async-сеансе.
Область автора уже проверена на гейте (route зовёт `_admin_only(user)` ДО
gate_or_apply), апстрим-проверка при применении — повторная страховка.

upsert идемпотентен (service.find_* → update|create по уникальному ключу),
delete — no-op при отсутствии строки, поэтому повторное применение из очереди
безопасно.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.elasticity import ElasticityUpsert, ProjectEffectUpsert
from app.services.elasticity.service import ElasticityService
from app.services.moderation_service import register_apply_handler


async def _load_proposer(db, sub: ModerationSubmission, fallback: User) -> User:
    if not sub.proposer_user_id:
        return fallback
    proposer = (await db.execute(
        select(User)
        .where(User.id == sub.proposer_user_id)
        .options(selectinload(User.roles))
    )).scalar_one_or_none()
    return proposer or fallback


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    pv = dict(sub.proposed_value)
    action = (sub.action or "").lower()
    kind = str(pv.get("_kind") or "").strip()

    author = await _load_proposer(db, sub, user)
    service = ElasticityService()

    if action in ("edit", "update", "upsert"):
        if kind == "coefficient":
            payload = ElasticityUpsert.model_validate(pv)
            obj = await service.upsert_coefficient(payload, db, author)
            return {"module": "elasticity", "action": "edit",
                    "kind": "coefficient", "id": str(obj.id)}
        if kind == "project_effect":
            payload = ProjectEffectUpsert.model_validate(pv)
            obj = await service.upsert_project_effect(payload, db, author)
            return {"module": "elasticity", "action": "edit",
                    "kind": "project_effect", "id": str(obj.id)}
        raise ValueError(f"elasticity edit: unknown _kind {kind!r}")

    if action in ("delete", "archived"):
        ent = pv.get("id") or sub.target_entity_id
        if not ent:
            raise ValueError("elasticity delete requires entity id")
        eid = UUID(str(ent))
        if kind == "coefficient":
            res = await service.delete_coefficient(eid, db, author)
        elif kind == "project_effect":
            res = await service.delete_project_effect(eid, db, author)
        else:
            raise ValueError(f"elasticity delete: unknown _kind {kind!r}")
        return {"module": "elasticity", "action": "delete",
                "kind": kind, "id": str(eid), **(res or {})}

    raise ValueError(f"unknown elasticity action: {action!r}")


register_apply_handler("elasticity", apply)
