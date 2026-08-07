"""Report-wizard apply handler (deny-by-default Phase 4).

Применяет одобренную правку «Мастера отчёта». Зеркалит
PUT /report-wizard/{code}/{year} (ReportWizardService.upsert — full-replace
конфига по (company_id, year), запись в report_wizard_config).

Submission shape:
  target_module    = "report_wizard"
  target_entity_id = "<company code>:<year>"
  target_company_id = <company UUID>   (резолвится в роуте, едет в submission)
  year             = <int>
  proposed_value   = {"code","year","config"}

Атрибуция: автор правки — ПРЕДЛОЖИВШИЙ (proposer), а не модератор, нажавший
«принять» — updated_by / updated_by_name должны вести к автору. Компания
резолвится по коду заново (as в живом роуте), scope модератора уже проверен на
resolve. `config` — это ВЕСЬ объект (upsert делает full-replace колонки), поэтому
partial-NULL проблемы batch-1 здесь нет.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.company import Company
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.moderation_service import register_apply_handler
from app.services.report_wizard.service import ReportWizardService


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    pv = dict(sub.proposed_value)

    code = str(pv.get("code") or "").strip()
    if not code and sub.target_entity_id:
        code = str(sub.target_entity_id).split(":", 1)[0].strip()
    if not code:
        raise ValueError("report_wizard apply requires company code")

    year = pv.get("year")
    if year is None and sub.target_entity_id and ":" in str(sub.target_entity_id):
        year = str(sub.target_entity_id).split(":", 1)[1].strip()
    if year is None:
        raise ValueError("report_wizard apply requires year")
    year = int(year)

    config = pv.get("config") or {}

    # Атрибуция аудита/updated_by — автор правки (proposer), не модератор.
    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user

    cid = sub.target_company_id
    if cid is None:
        res = await db.execute(select(Company.id).where(Company.code == code))
        cid = res.scalar_one_or_none()
    if cid is None:
        raise ValueError(f"report_wizard apply: company '{code}' not found")
    if not isinstance(cid, UUID):
        cid = UUID(str(cid))

    await ReportWizardService(db).upsert(cid, year, config, author)
    return {"module": "report_wizard", "code": code, "year": year}


register_apply_handler("report_wizard", apply)
