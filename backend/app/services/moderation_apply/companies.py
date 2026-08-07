"""Companies apply handler (deny-by-default Phase 0).

Применяет одобренную правку компании. Зеркалит POST /companies,
PATCH /companies/{code}, DELETE /companies/{code}. CompaniesService работает на
СВОЕЙ UoW/сессии (как projects), поэтому create — с idempotency-штампом
target_entity_id: повтор применения не плодит дубль.

Атрибуция аудита — ПРЕДЛОЖИВШИЙ (proposer), не модератор.
delete через модерацию — только soft: cascade требует владельца, а владелец
модерацию обходит (gate_or_apply возвращает bypass), поэтому cascade-заявок нет.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.company import CompanyCreatePayload, CompanyUpdatePayload
from app.services.companies.service import CompaniesService
from app.services.moderation_service import register_apply_handler
from app.uow.impl import UnitOfWork


def _service() -> CompaniesService:
    return CompaniesService(uow=UnitOfWork(session_factory=AsyncSessionLocal))


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value)

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    actor_email = getattr(proposer, "email", None) or getattr(user, "email", "") or ""
    actor_id = str(sub.proposer_user_id) if sub.proposer_user_id else str(user.id)
    service = _service()

    if action in ("create", "created"):
        # Идемпотентность повтора: если прошлый apply уже создал компанию и
        # застолбил её id в target_entity_id, повтор НЕ создаёт дубль.
        if sub.target_entity_id:
            try:
                cid = UUID(sub.target_entity_id)
            except Exception:
                cid = None
            if cid is not None:
                from app.models.company import Company
                exists = (await db.execute(
                    select(Company.id).where(Company.id == cid)
                )).scalar_one_or_none()
                if exists is not None:
                    return {"action": "create", "company_id": str(cid), "idempotent": True}
        payload = CompanyCreatePayload.model_validate(pv)
        detail, _grp = await service.create_company(
            payload, actor_id=actor_id, actor_email=actor_email,
        )
        sub.target_entity_id = str(detail.id)  # застолбить id (коммитит _dispatch_apply)
        return {"action": "create", "company_id": str(detail.id), "code": detail.code}

    if action in ("update", "edit"):
        code = str(pv.get("code") or sub.target_entity_id or "").strip()
        if not code:
            raise ValueError("companies update requires code")
        payload = CompanyUpdatePayload.model_validate(pv)
        detail, _changes = await service.update_company(
            code, payload, scope_company_ids=None,
            actor_id=actor_id, actor_email=actor_email,
        )
        return {"action": "update", "code": detail.code}

    if action in ("delete", "deactivate", "archived"):
        code = str(pv.get("code") or sub.target_entity_id or "").strip()
        if not code:
            raise ValueError("companies delete requires code")
        await service.delete_company(
            code, cascade=False, actor_is_owner=False, scope_company_ids=None,
            actor_id=actor_id, actor_email=actor_email,
        )
        return {"action": "delete", "code": code}

    raise ValueError(f"unknown companies action: {action!r}")


register_apply_handler("companies", apply)
