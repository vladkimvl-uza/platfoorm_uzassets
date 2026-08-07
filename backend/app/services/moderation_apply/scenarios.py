"""Macro Scenarios apply handler (deny-by-default Phase 4).

Применяет одобренную правку макро-сценариев. Зеркалит write-роуты
app/api/routes/scenarios.py через ScenariosService, который работает на СВОЕЙ
UoW/сессии (как companies/notes/projects), поэтому create — с idempotency-штампом
target_entity_id: повтор применения не плодит дубль.

«Сценарии» — ГЛОБАЛЬНЫЙ справочник (admin-only, /admin/system-config), без
привязки к компании, поэтому target_company_id всегда None и маппинг в
`_effective_company_id` НЕ нужен.

Атрибуция аудита — ПРЕДЛОЖИВШИЙ (proposer), не модератор. (Аудит-цепочку пишет
сам роут пост-коммитом с actor IP/UA — при apply через очередь она не ведётся,
как и у directions/subsidies; доменная запись атрибутируется автору через сервис.)

ДИСКРИМИНАТОР (как в notes): пять write-роутов сворачиваются в два action —
`edit` (update_scenario ЛИБО upsert_override) и `delete` (delete_scenario ЛИБО
delete_override). Различаем по форме target_entity_id:
  • "<scenario_uuid>"        → операция над самим сценарием
  • "<scenario_uuid>:<year>" → операция над override этого сценария за год

Submission shape:
  target_module    = "scenarios"
  action           = create | edit | delete
  target_entity_id =
     create → None (для create — застолблённый id после применения)
     scenario edit/delete → "<scenario_id>"
     override edit/delete → "<scenario_id>:<year>"
  proposed_value   =
     create           → ScenarioCreate.model_dump(mode="json")
     scenario edit    → ScenarioUpdate.model_dump(mode="json", exclude_unset=True)
     scenario delete  → {"scenario_id"}
     override edit     → ScenarioOverrideUpsert.model_dump(mode="json")
     override delete   → {"scenario_id","year"}
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.moderation import ModerationSubmission
from app.models.scenarios import MacroScenario
from app.models.user import User
from app.schemas.scenarios import (
    ScenarioCreate,
    ScenarioOverrideUpsert,
    ScenarioUpdate,
)
from app.services.moderation_service import register_apply_handler
from app.services.scenarios.service import ScenariosService
from app.uow.impl import UnitOfWork


def _service() -> ScenariosService:
    return ScenariosService(uow=UnitOfWork(session_factory=AsyncSessionLocal))


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value or {})
    tid = str(sub.target_entity_id or "")
    is_override = ":" in tid

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    _author = proposer or user  # scenarios-сервис не берёт actor — атрибуция в роуте
    service = _service()

    # ─── overrides (target_entity_id = "<scenario_id>:<year>") ────────
    if is_override:
        sid_str, _, year_str = tid.partition(":")
        scenario_id = UUID(sid_str)
        year = int(year_str)

        if action in ("edit", "update"):
            # PUT-override = полная замена значений года (None = «очистить поле,
            # взять базу из year_registry»). Дампим/валидируем как есть — сервис
            # присваивает все поля, поэтому семантика замены сохраняется 1:1.
            payload = ScenarioOverrideUpsert.model_validate(pv)
            await service.upsert_override(scenario_id, year, payload)
            return {"action": "edit", "scenario_id": str(scenario_id), "year": year}

        if action in ("delete", "deleted"):
            await service.delete_override(scenario_id, year)
            return {"action": "delete", "scenario_id": str(scenario_id), "year": year}

        raise ValueError(f"unknown scenarios override action: {action!r}")

    # ─── scenario create ──────────────────────────────────────────────
    if action in ("create", "created"):
        if not pv:
            raise ValueError("proposed_value is empty")
        # Идемпотентность повтора: если прошлый apply уже создал сценарий и
        # застолбил его id в target_entity_id, повтор НЕ создаёт дубль.
        if sub.target_entity_id:
            try:
                cid = UUID(tid)
            except Exception:
                cid = None
            if cid is not None:
                exists = (await db.execute(
                    select(MacroScenario.id).where(MacroScenario.id == cid)
                )).scalar_one_or_none()
                if exists is not None:
                    return {"action": "create", "scenario_id": str(cid),
                            "idempotent": True}
        payload = ScenarioCreate.model_validate(pv)
        scenario, _snap = await service.create_scenario(payload)
        sub.target_entity_id = str(scenario.id)  # застолбить id (коммитит _dispatch_apply)
        return {"action": "create", "scenario_id": str(scenario.id),
                "code": scenario.code}

    # ─── scenario edit / delete (target_entity_id = "<scenario_id>") ──
    if not sub.target_entity_id:
        raise ValueError("scenarios apply requires target_entity_id (scenario id)")
    scenario_id = UUID(tid)

    if action in ("edit", "update"):
        # exclude_unset дампится в роуте → в pv только реально присланные поля;
        # update_scenario пишет лишь non-None поля, поэтому неприсланные не
        # затираются в None.
        payload = ScenarioUpdate.model_validate(pv)
        await service.update_scenario(scenario_id, payload)
        return {"action": "edit", "scenario_id": str(scenario_id)}

    if action in ("delete", "deleted"):
        await service.delete_scenario(scenario_id)
        return {"action": "delete", "scenario_id": str(scenario_id)}

    raise ValueError(f"unknown scenarios action: {action!r}")


register_apply_handler("scenarios", apply)
