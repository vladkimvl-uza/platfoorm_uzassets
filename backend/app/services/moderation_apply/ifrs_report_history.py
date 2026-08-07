"""IFRS report history apply handler (deny-by-default Phase 4).

Применяет одобренную правку даты публикации МСФО-отчётности. Зеркалит
PUT /ifrs-report-history/{company_id}/{year}
(IfrsReportHistoryService.upsert — задать/очистить published_on по
company_id+year).

Submission shape:
  target_module     = "ifrs_report_history"
  target_company_id = <company UUID>          (реальный UUID — из пути роута)
  target_entity_id  = "<company_id>:<year>"
  year              = <int>
  proposed_value    = {"company_id","year","published_on"?}

Идемпотентность: upsert по своей природе идемпотентен (ключ company_id+year;
повтор просто перезаписывает тем же значением), поэтому штамп target_entity_id
для create-дедупа не нужен.

Атрибуция: автор правки — ПРЕДЛОЖИВШИЙ (proposer), а не модератор, нажавший
«принять». Сервис пишет updated_by/updated_by_name из переданного `user`, поэтому
передаём загруженного проповера (фолбэк — модератор, если не найден).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.ifrs_report_history import IfrsHistoryUpsert
from app.services.ifrs_report_history.service import IfrsReportHistoryService
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    pv = dict(sub.proposed_value)

    # Компания: из target_company_id (реальный UUID пути), фолбэк — payload.
    company_id: UUID | None = sub.target_company_id
    if company_id is None and pv.get("company_id"):
        company_id = UUID(str(pv["company_id"]))
    if company_id is None:
        raise ValueError("ifrs_report_history apply requires company_id")

    # ModerationSubmission НЕ хранит year (year идёт только в match_rule). Берём
    # из payload; фолбэк — суффикс target_entity_id "<company_id>:<year>".
    year = pv.get("year")
    if year is None and sub.target_entity_id and ":" in sub.target_entity_id:
        year = sub.target_entity_id.rsplit(":", 1)[-1]
    if year is None:
        raise ValueError("ifrs_report_history apply requires year")
    year = int(year)

    # published_on: коэрсим ISO-строку → date через схему (exclude_unset при
    # гейте: отсутствие == null == очистить дату, как в живом роуте).
    published_on = IfrsHistoryUpsert.model_validate(pv).published_on

    # Атрибуция — предложивший. Сервис берёт updated_by из user.id.
    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user

    await IfrsReportHistoryService(db).upsert(company_id, year, published_on, author)
    return {"module": "ifrs_report_history", "company_id": str(company_id),
            "year": year, "published_on": published_on.isoformat() if published_on else None}


register_apply_handler("ifrs_report_history", apply)
