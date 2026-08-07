"""Subsidies apply handler (deny-by-default Phase 4).

Применяет одобренную правку реестра субсидий. Зеркалит POST /subsidies,
PUT /subsidies/{id}, DELETE /subsidies/{id} через SubsidiesService (работает на
той же сессии запроса модерации, НЕ на отдельной UoW — как ratings/kpi).

Атрибуция создания — ПРЕДЛОЖИВШИЙ (proposer): SubsidiesService.create пишет
created_by / created_by_name из переданного user, поэтому загружаем автора по
sub.proposer_user_id, а не берём модератора. Scope модератора уже проверен на
resolve — заявка несёт реальный UUID компании в target_company_id, — поэтому в
сервис передаём scope_ids=None (иначе повторно и лишне сузили бы область).

Submission shape:
  target_module    = "subsidies"
  action           = "create" | "edit" | "delete"
  target_entity_id = <subsidy id> (edit/delete; для create застолбляется после
                     применения — идемпотентность повтора)
  proposed_value   = SubsidyUpsert (create) | SubsidyPatch (edit) | {} (delete)
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.subsidies import Subsidy
from app.models.user import User
from app.schemas.subsidies import SubsidyPatch, SubsidyUpsert
from app.services.moderation_service import register_apply_handler
from app.services.subsidies.service import SubsidiesService


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    action = (sub.action or "").lower()
    service = SubsidiesService(db)

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user

    if action in ("create", "created"):
        if not sub.proposed_value:
            raise ValueError("proposed_value is empty")
        # Идемпотентность повтора: если прошлый apply уже создал запись и
        # застолбил её id в target_entity_id, повтор НЕ плодит дубль.
        if sub.target_entity_id:
            try:
                sid = UUID(sub.target_entity_id)
            except Exception:
                sid = None
            if sid is not None:
                exists = (await db.execute(
                    select(Subsidy.id).where(Subsidy.id == sid),
                )).scalar_one_or_none()
                if exists is not None:
                    return {"action": "create", "subsidy_id": str(sid), "idempotent": True}
        payload = SubsidyUpsert.model_validate(dict(sub.proposed_value))
        row = await service.create(payload, author, scope_ids=None)
        sub.target_entity_id = str(row.id)  # застолбить id (коммитит _dispatch_apply)
        return {"action": "create", "subsidy_id": str(row.id)}

    if action in ("edit", "update"):
        if not sub.target_entity_id:
            raise ValueError("subsidies edit requires target_entity_id")
        sid = UUID(sub.target_entity_id)
        patch = SubsidyPatch.model_validate(dict(sub.proposed_value or {}))
        row = await service.update(sid, patch, scope_ids=None)
        return {"action": "edit", "subsidy_id": str(row.id)}

    if action in ("delete", "deleted"):
        if not sub.target_entity_id:
            raise ValueError("subsidies delete requires target_entity_id")
        sid = UUID(sub.target_entity_id)
        await service.delete(sid, scope_ids=None)
        return {"action": "delete", "subsidy_id": str(sid)}

    raise ValueError(f"unknown subsidies action: {action!r}")


register_apply_handler("subsidies", apply)
