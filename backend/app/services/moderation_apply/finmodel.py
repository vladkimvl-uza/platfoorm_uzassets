"""FinModel v2 apply handler (deny-by-default Phase 4).

Применяет одобренную правку финмодели. Зеркалит persisting-роуты
`app/api/routes/finmodel.py` через `FinModelService`, который работает на СВОЕЙ
UoW/сессии (как companies/scenarios): каждый метод открывает/коммитит свою
транзакцию (`async with self.uow`). Поэтому мы НЕ оборачиваем сюда переданную
модерационную сессию `db` (её коммит/rollback ведёт `_dispatch_apply`), а строим
сервис на отдельной `AsyncSessionLocal`.

Атрибуция — ПРЕДЛОЖИВШИЙ (proposer), не модератор: user_id всех доменных
методов (updated_by ячеек, locked_by, created_by сценария, аудит) = автор.

ДИСКРИМИНАТОР: канонические action'ы (edit/create/delete/status_change)
сворачивают по несколько операций, поэтому в `proposed_value` лежит явный `op`:
  edit          → cell | cells_batch | macro | forecast
  create        → year_create | year_copy | scenario_create | import_commit
  delete        → year_delete | scenario_delete
  status_change → year_lock | year_unlock | scenario_activate

company_id — реальный UUID из пути (в gate_or_apply идёт как company_id), поэтому
живёт в `sub.target_company_id`; дублируется в payload для самодостаточности.
year НЕ хранится в сабмишене отдельным полем — несём его в `proposed_value`.

Идемпотентность: единственная НЕ-идемпотентная операция — создание сценария
(каждый вызов плодит новую строку). Для неё штампуем `sub.target_entity_id`
id-ом созданного сценария (коммитит `_dispatch_apply`), повтор apply дубль не
плодит. Остальные create-операции идемпотентны по своей природе: create_year
возвращает существующий lock, copy_year перетирает год, import_commit —
upsert по ключу ячейки.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.finmodel import FinModelScenario
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.finmodel import (
    CellBatchWrite,
    CellWrite,
    ForecastRequest,
    MacroCompanyWrite,
    ScenarioCreate,
    YearLockUpdate,
)
from app.services.finmodel.service import FinModelService
from app.services.moderation_service import register_apply_handler
from app.uow.impl import UnitOfWork


def _service() -> FinModelService:
    return FinModelService(uow=UnitOfWork(session_factory=AsyncSessionLocal))


def _company_id(sub: ModerationSubmission, pv: dict) -> UUID:
    if sub.target_company_id is not None:
        return sub.target_company_id
    raw = pv.get("company_id")
    if not raw:
        raise ValueError("finmodel apply requires company_id")
    return UUID(str(raw))


def _year(pv: dict) -> int:
    y = pv.get("year")
    if y is None:
        raise ValueError("finmodel apply requires year in proposed_value")
    return int(y)


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value)
    op = str(pv.get("op") or "").lower()

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user
    author_id = author.id

    company_id = _company_id(sub, pv)
    service = _service()

    # ── edit (cell / cells_batch / macro) ─────────────────────────────
    if action in ("edit", "update"):
        if op == "cell":
            body = CellWrite.model_validate(pv["body"])
            await service.patch_cell(company_id, _year(pv), body, user_id=author_id)
            return {"action": "edit", "op": op, "year": _year(pv)}
        if op == "cells_batch":
            body = CellBatchWrite.model_validate(pv["body"])
            await service.patch_cells_batch(company_id, _year(pv), body, user_id=author_id)
            return {"action": "edit", "op": op, "year": _year(pv),
                    "cells": len(body.cells)}
        if op == "macro":
            body = MacroCompanyWrite.model_validate(pv["body"])
            await service.put_macro(company_id, _year(pv), body, user_id=author_id)
            return {"action": "edit", "op": op, "year": _year(pv)}
        if op == "forecast":
            # Прогноз ПЕРСИСТИТ ячейки (is_calculated=True) — идемпотентен (upsert
            # по ключу ячейки на target_years), повтор apply просто перезапишет.
            body = ForecastRequest.model_validate(pv["body"])
            result = await service.regenerate_forecast(
                company_id, body, user_id=author_id
            )
            return {"action": "edit", "op": op, "base_year": body.base_year,
                    "target_years": body.target_years, **(result or {})}
        raise ValueError(f"unknown finmodel edit op: {op!r}")

    # ── create (year_create / year_copy / scenario_create / import) ───
    if action in ("create", "created"):
        if op == "year_create":
            await service.create_year(company_id, _year(pv))
            return {"action": "create", "op": op, "year": _year(pv)}
        if op == "year_copy":
            src_year = int(pv["src_year"])
            await service.copy_year(company_id, _year(pv), src_year, user_id=author_id)
            return {"action": "create", "op": op, "year": _year(pv),
                    "src_year": src_year}
        if op == "scenario_create":
            # Идемпотентность повтора: прошлый apply уже создал сценарий и
            # застолбил его id в target_entity_id — повтор НЕ создаёт дубль.
            if sub.target_entity_id:
                try:
                    sid = UUID(str(sub.target_entity_id))
                except (ValueError, TypeError):
                    sid = None
                if sid is not None:
                    exists = (await db.execute(
                        select(FinModelScenario.id).where(FinModelScenario.id == sid)
                    )).scalar_one_or_none()
                    if exists is not None:
                        return {"action": "create", "op": op,
                                "scenario_id": str(sid), "idempotent": True}
            body = ScenarioCreate.model_validate(pv["body"])
            scenario = await service.create_scenario(company_id, body, user_id=author_id)
            sub.target_entity_id = str(scenario.id)  # застолбить (коммитит _dispatch_apply)
            return {"action": "create", "op": op, "scenario_id": str(scenario.id)}
        if op == "import_commit":
            result = await service.import_excel_commit(
                company_id,
                preview=pv.get("preview") or {},
                selected_years=pv.get("selected_years"),
                skip_unmatched=bool(pv.get("skip_unmatched", True)),
                user_id=author_id,
            )
            return {"action": "create", "op": op, **result}
        raise ValueError(f"unknown finmodel create op: {op!r}")

    # ── delete (year_delete / scenario_delete) ────────────────────────
    if action in ("delete", "deleted", "archived"):
        if op == "year_delete":
            await service.delete_year(company_id, _year(pv), user_id=author_id)
            return {"action": "delete", "op": op, "year": _year(pv)}
        if op == "scenario_delete":
            scenario_id = UUID(str(pv["scenario_id"]))
            await service.delete_scenario(company_id, scenario_id)
            return {"action": "delete", "op": op, "scenario_id": str(scenario_id)}
        raise ValueError(f"unknown finmodel delete op: {op!r}")

    # ── status_change (year_lock / year_unlock / scenario_activate) ───
    if action in ("status_change", "status_changed"):
        if op == "year_lock":
            body = YearLockUpdate.model_validate(pv["body"])
            await service.lock_year(company_id, _year(pv), body, user_id=author_id)
            return {"action": "status_change", "op": op, "year": _year(pv)}
        if op == "year_unlock":
            await service.unlock_year(company_id, _year(pv))
            return {"action": "status_change", "op": op, "year": _year(pv)}
        if op == "scenario_activate":
            scenario_id = UUID(str(pv["scenario_id"]))
            await service.activate_scenario(company_id, scenario_id, user_id=author_id)
            return {"action": "status_change", "op": op,
                    "scenario_id": str(scenario_id)}
        raise ValueError(f"unknown finmodel status_change op: {op!r}")

    raise ValueError(f"unknown finmodel action: {action!r}")


register_apply_handler("finmodel", apply)
