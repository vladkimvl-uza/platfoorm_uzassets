"""Overview-matrix apply handler (deny-by-default Phase 4).

Применяет одобренную правку конфига квартальной матрицы «Сводного обзора».
Зеркалит PUT /overview-matrix/{company_id}/{year}
(OverviewMatrixService.upsert — один row на (company, year), config хранится
целиком в JSONB).

Submission shape:
  target_module     = "overview_matrix"
  target_entity_id  = "<company_uuid>:<year>"
  target_company_id = <company UUID>            (реальный id → scope штатно)
  proposed_value    = {"company_id","year","config": {...MatrixConfig...}}

Атрибуция: автор правки — ПРЕДЛОЖИВШИЙ (proposer), а не модератор, нажавший
«принять» — updated_by / updated_by_name ведут к автору.

Идемпотентность: action="replace" — это upsert полного config в единственный
row (company, year). Повторное применение перезаписывает тот же row тем же
значением, поэтому отдельный separate-session штамп (как create в companies.py)
не нужен — операция идемпотентна по своей природе.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.overview_matrix import MatrixConfig
from app.services.moderation_service import register_apply_handler
from app.services.overview_matrix.service import OverviewMatrixService


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value)

    # company_id: из payload либо из target_company_id (реальный UUID).
    raw_cid = pv.get("company_id") or sub.target_company_id
    if not raw_cid:
        raise ValueError("overview_matrix apply requires company_id")
    company_id = raw_cid if isinstance(raw_cid, UUID) else UUID(str(raw_cid))

    year = pv.get("year")
    if year is None:
        raise ValueError("overview_matrix apply requires year")
    year = int(year)

    # Атрибуция — предложивший (proposer), не модератор.
    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user

    if action in ("replace", "upsert", "edit", "update"):
        config = MatrixConfig.model_validate(pv.get("config") or {})
        await OverviewMatrixService(db).upsert(company_id, year, config, author)
        return {"module": "overview_matrix", "action": "replace",
                "company_id": str(company_id), "year": year}

    raise ValueError(f"unknown overview_matrix action: {action!r}")


register_apply_handler("overview_matrix", apply)
