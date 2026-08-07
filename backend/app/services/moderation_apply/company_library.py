"""Company-library apply handler (deny-by-default Phase 4).

Применяет одобренную правку одного поля карточки компании из «Библиотеки
компаний» (MDM). Зеркалит PATCH /library/companies/{id}/fields/{code}
(CompanyLibraryService.apply_library_field — прямая запись library/companies-поля
БЕЗ повторного гейта модерации). Рейтинговые и финансовые поля этого же роута
модерируются СВОИМИ модулями (ratings/financials) и в company_library-заявку не
попадают.

Атрибуция аудита/бродкаста — ПРЕДЛОЖИВШИЙ (proposer), не модератор, нажавший
«принять».

Сервис работает на СВОЕЙ UoW/сессии (AsyncSessionLocal, как companies), поэтому
доменная запись не зависит от сессии модерации. Запись поля идемпотентна по
своей природе (custom_data[code]=value / setattr) — отдельный штамп повтора не
нужен.

Submission shape:
  target_module     = "company_library"
  target_entity_id  = <company id (UUID)>
  target_company_id = <company id (UUID)>  — scope-гейт резолвит компанию прямо
  proposed_value    = {"company_id","field_code","value","source_module"}
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.company_library.service import CompanyLibraryService
from app.services.moderation_service import register_apply_handler
from app.uow.impl import UnitOfWork


def _service() -> CompanyLibraryService:
    return CompanyLibraryService(uow=UnitOfWork(session_factory=AsyncSessionLocal))


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    pv = dict(sub.proposed_value)

    raw_cid = pv.get("company_id") or sub.target_company_id or sub.target_entity_id
    if not raw_cid:
        raise ValueError("company_library apply requires company_id")
    company_id = UUID(str(raw_cid))
    field_code = str(pv.get("field_code") or "").strip()
    if not field_code:
        raise ValueError("company_library apply requires field_code")
    new_value = pv.get("value")

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author_email = getattr(proposer, "email", None) or getattr(user, "email", "") or ""
    author_id = str(sub.proposer_user_id) if sub.proposer_user_id else str(user.id)

    routed_to = await _service().apply_library_field(
        company_id, field_code, new_value,
        actor_id=author_id, actor_email=author_email,
    )
    return {"module": "company_library", "company_id": str(company_id),
            "field_code": field_code, "routed_to": routed_to}


register_apply_handler("company_library", apply)
