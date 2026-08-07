"""Consultants apply handler (deny-by-default Phase 4).

Применяет одобренную правку СПРАВОЧНИКА консультантов. Зеркалит
POST /consultants, PATCH /consultants/{id}, DELETE /consultants/{id}.
ConsultantsService работает на СВОЕЙ UoW/сессии (session_factory=AsyncSessionLocal,
как companies/projects), поэтому create — с idempotency-штампом target_entity_id:
повтор применения из очереди не плодит дубль.

Справочник консультантов ГЛОБАЛЬНЫЙ (фирмы Big-4 и пр.), НЕ привязан к компании,
поэтому company_id заявки всегда None, и в `_effective_company_id`
(moderation_service) модуль добавлять НЕ нужно — scope модератора здесь не
применим (сущность живёт вне компаний).

Атрибуция: правку предложил ПРЕДЛОЖИВШИЙ (proposer). Методы сервиса
(create/update/delete_consultant) НЕ принимают actor — в слое консультантов нет
audit-хука, поэтому атрибуцию через сервис протянуть некуда (см. concerns).

Submission shape:
  target_module    = "consultants"
  target_entity_id = <consultant UUID> (edit/delete) | None→id (create)
  action           = create | edit | delete
  proposed_value   = ConsultantIn (create) | ConsultantPatch exclude_unset (edit)
                     | {"hard": bool} (delete)
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.consultant import Consultant
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.consultants.service import ConsultantsService
from app.services.moderation_service import register_apply_handler
from app.uow.impl import UnitOfWork


def _service() -> ConsultantsService:
    return ConsultantsService(uow=UnitOfWork(session_factory=AsyncSessionLocal))


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value or {})

    # Схемы валидации (ConsultantIn/ConsultantPatch) объявлены в самом роутере;
    # импорт ленивый — не тянем API-слой на этапе загрузки apply-хендлеров
    # (исключаем любой цикл импорта route↔moderation).
    from app.api.routes.consultants import ConsultantIn, ConsultantPatch

    service = _service()

    if action in ("create", "created"):
        # Идемпотентность повтора: прошлый apply уже создал фирму и застолбил её
        # id в target_entity_id — повтор не плодит дубль.
        if sub.target_entity_id:
            try:
                cid = UUID(sub.target_entity_id)
            except Exception:
                cid = None
            if cid is not None:
                exists = (await db.execute(
                    select(Consultant.id).where(Consultant.id == cid)
                )).scalar_one_or_none()
                if exists is not None:
                    return {"action": "create", "consultant_id": str(cid), "idempotent": True}
        detail = await service.create_consultant(payload=ConsultantIn.model_validate(pv))
        sub.target_entity_id = str(detail["id"])  # застолбить id (коммитит _dispatch_apply)
        return {"action": "create", "consultant_id": str(detail["id"]), "code": detail.get("code")}

    if action in ("edit", "update"):
        if not sub.target_entity_id:
            raise ValueError("consultants edit requires target_entity_id (consultant id)")
        cid = UUID(sub.target_entity_id)
        # ConsultantPatch пере-валидируется из proposed_value. Роут кладёт его с
        # exclude_unset=True, поэтому re-validate помечает set ТОЛЬКО реально
        # присланные поля → сервис (model_dump(exclude_unset=True)) не занулит
        # неуказанные (partial-PATCH сохраняется).
        detail = await service.update_consultant(cid, payload=ConsultantPatch.model_validate(pv))
        return {"action": "edit", "consultant_id": str(cid), "code": detail.get("code")}

    if action in ("delete", "deactivate", "archived"):
        if not sub.target_entity_id:
            raise ValueError("consultants delete requires target_entity_id (consultant id)")
        cid = UUID(sub.target_entity_id)
        # Идемпотентность hard-delete: строки уже нет — считаем применённым.
        exists = (await db.execute(
            select(Consultant.id).where(Consultant.id == cid)
        )).scalar_one_or_none()
        if exists is None:
            return {"action": "delete", "consultant_id": str(cid), "idempotent": True}
        await service.delete_consultant(cid, hard=bool(pv.get("hard", False)))
        return {"action": "delete", "consultant_id": str(cid)}

    raise ValueError(f"unknown consultants action: {action!r}")


register_apply_handler("consultants", apply)
