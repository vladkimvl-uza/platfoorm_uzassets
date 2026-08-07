"""PMO apply handler (deny-by-default Phase 4).

Применяет одобренную правку модуля PMO. У PMO НЕТ сервис-слоя — write-роуты
`app/api/routes/pmo.py` мутируют модели инлайном, поэтому apply зеркалит ту же
инлайновую логику напрямую по моделям на ТОЙ ЖЕ сессии запроса модерации
(как kpi/ratings; коммитит `_dispatch_apply`, здесь только flush ради id).

Один модуль "pmo" покрывает ~9 типов сущностей (dependency / raid / sprint /
raci / stakeholder / lesson / change / charter / status_report) × create/edit/
delete. `sub.action` (create|edit|delete) не различает raid от sprint, поэтому
тип сущности ЗАКОДИРОВАН в `proposed_value["_entity"]`, и хендлер ветвится по
нему.

Атрибуция создания — ПРЕДЛОЖИВШИЙ (proposer): `created_by` пишется из автора
(load User by proposer_user_id), а не из модератора. Scope модератора уже
проверен на resolve (заявка несёт реальный UUID компании в target_company_id —
роуты зовут gate_or_apply с company_id=<UUID>), поэтому здесь область не сужаем.

Submission shape:
  target_module    = "pmo"
  action           = "create" | "edit" | "delete"
  target_company_id= <UUID компании> (или None — dependency у задачи без компании)
  target_entity_id =
     create → None (застолбляется id созданной сущности после применения)
     edit/delete → "<entity id>"
  proposed_value   = {"_entity": "<type>", ...}
     create → полный дамп *Create-схемы (+ для dependency: predecessor/successor)
     edit   → частичный дамп *Update-схемы (exclude_unset — не затирать неприсланное)
     delete → {"_entity": "<type>"}
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.company import Company
from app.models.pmo import (
    PmoChange,
    PmoCharter,
    PmoLesson,
    PmoRaci,
    PmoSprint,
    PmoStakeholder,
    RaidItem,
    StatusReport,
)
from app.models.task import Task, TaskDependency
from app.models.user import User
from app.schemas.pmo import (
    ChangeCreate,
    ChangeUpdate,
    CharterCreate,
    CharterUpdate,
    LessonCreate,
    LessonUpdate,
    RaciCreate,
    RaciUpdate,
    RaidItemCreate,
    RaidItemUpdate,
    SprintCreate,
    SprintUpdate,
    StakeholderCreate,
    StakeholderUpdate,
)
from app.services.moderation_service import register_apply_handler
from app.services.pmo.health import generate_status_report


# ── decision-штампы (зеркало инлайн-хелперов роутера) ──────────────────

def _change_decision(item: PmoChange) -> None:
    """Решённый статус → штамп decided_at; обратно в proposed → снять."""
    if item.status in ("approved", "rejected", "implemented"):
        if item.decided_at is None:
            item.decided_at = datetime.now(timezone.utc)
    else:
        item.decided_at = None


def _charter_approval(item: PmoCharter, actor: User) -> None:
    """status=approved → штамп approver+дата; обратно в draft → снять."""
    if item.status == "approved":
        if item.approved_at is None:
            item.approved_at = datetime.now(timezone.utc)
            item.approved_by = actor.full_name or actor.email
    else:
        item.approved_at = None
        item.approved_by = None


async def _would_create_cycle(db, predecessor_id: UUID, successor_id: UUID) -> bool:
    """Замкнёт ли ребро pred→succ цикл (зеркало роутерного BFS)."""
    rows = (await db.execute(select(TaskDependency))).scalars().all()
    succ: dict[UUID, list[UUID]] = defaultdict(list)
    for d in rows:
        succ[d.predecessor_id].append(d.successor_id)
    seen: set[UUID] = set()
    q = deque([successor_id])
    while q:
        n = q.popleft()
        if n == predecessor_id:
            return True
        for s in succ.get(n, []):
            if s not in seen:
                seen.add(s)
                q.append(s)
    return False


def _norm(action: str) -> str:
    a = (action or "").lower()
    if a in ("create", "created"):
        return "create"
    if a in ("edit", "update", "updated"):
        return "edit"
    if a in ("delete", "deleted", "archived"):
        return "delete"
    return a


async def _already(db, model, sub: ModerationSubmission) -> bool:
    """Идемпотентность повтора create: id уже застолблён и строка существует."""
    if not sub.target_entity_id:
        return False
    try:
        eid = UUID(str(sub.target_entity_id))
    except Exception:
        return False
    return (await db.execute(
        select(model.id).where(model.id == eid)
    )).scalar_one_or_none() is not None


async def _load(db, model, sub: ModerationSubmission):
    if not sub.target_entity_id:
        raise ValueError(f"pmo edit/delete requires target_entity_id ({model.__name__})")
    eid = UUID(str(sub.target_entity_id))
    return (await db.execute(select(model).where(model.id == eid))).scalar_one_or_none()


# ════════════════════════════════════════════════════════════════════════
#   Per-entity apply
# ════════════════════════════════════════════════════════════════════════

async def _apply_dependency(db, sub, author, act, pv) -> dict:
    if act == "create":
        if await _already(db, TaskDependency, sub):
            return {"entity": "dependency", "action": "create",
                    "dependency_id": str(sub.target_entity_id), "idempotent": True}
        pred_id = UUID(str(pv["predecessor_id"]))
        succ_id = UUID(str(pv["successor_id"]))
        if pred_id == succ_id:
            raise ValueError("dependency self-reference")
        existing = (await db.execute(
            select(TaskDependency).where(
                TaskDependency.predecessor_id == pred_id,
                TaskDependency.successor_id == succ_id,
            )
        )).scalar_one_or_none()
        if existing is not None:
            sub.target_entity_id = str(existing.id)
            return {"entity": "dependency", "action": "create",
                    "dependency_id": str(existing.id), "idempotent": True}
        if await _would_create_cycle(db, pred_id, succ_id):
            raise ValueError("dependency would create a cycle")
        dep = TaskDependency(
            predecessor_id=pred_id, successor_id=succ_id,
            dep_type=pv.get("dep_type", "FS"), lag_days=int(pv.get("lag_days", 0) or 0),
            created_by=author.id,
        )
        db.add(dep)
        await db.flush()
        sub.target_entity_id = str(dep.id)
        return {"entity": "dependency", "action": "create", "dependency_id": str(dep.id)}

    if act == "delete":
        dep = await _load(db, TaskDependency, sub)
        if dep is not None:
            await db.delete(dep)
        return {"entity": "dependency", "action": "delete",
                "dependency_id": str(sub.target_entity_id)}

    raise ValueError(f"unknown dependency action: {act!r}")


async def _apply_raid(db, sub, author, act, pv) -> dict:
    if act == "create":
        if await _already(db, RaidItem, sub):
            return {"entity": "raid", "action": "create",
                    "raid_id": str(sub.target_entity_id), "idempotent": True}
        payload = RaidItemCreate.model_validate(pv)
        data = payload.model_dump()
        item = RaidItem(
            company_id=sub.target_company_id,
            score=int(payload.probability) * int(payload.impact),
            created_by=author.id,
            closed_at=datetime.now(timezone.utc) if payload.status == "closed" else None,
            **data,
        )
        db.add(item)
        await db.flush()
        sub.target_entity_id = str(item.id)
        return {"entity": "raid", "action": "create", "raid_id": str(item.id)}

    if act == "edit":
        item = await _load(db, RaidItem, sub)
        if item is None:
            raise ValueError("raid item not found")
        patch = RaidItemUpdate.model_validate(pv)
        for k, v in patch.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        item.score = int(item.probability) * int(item.impact)
        if item.status == "closed" and item.closed_at is None:
            item.closed_at = datetime.now(timezone.utc)
        if item.status != "closed":
            item.closed_at = None
        return {"entity": "raid", "action": "edit", "raid_id": str(item.id)}

    if act == "delete":
        item = await _load(db, RaidItem, sub)
        if item is not None:
            await db.delete(item)
        return {"entity": "raid", "action": "delete", "raid_id": str(sub.target_entity_id)}

    raise ValueError(f"unknown raid action: {act!r}")


async def _apply_change(db, sub, author, act, pv) -> dict:
    if act == "create":
        if await _already(db, PmoChange, sub):
            return {"entity": "change", "action": "create",
                    "change_id": str(sub.target_entity_id), "idempotent": True}
        payload = ChangeCreate.model_validate(pv)
        item = PmoChange(company_id=sub.target_company_id, created_by=author.id,
                         **payload.model_dump())
        _change_decision(item)
        db.add(item)
        await db.flush()
        sub.target_entity_id = str(item.id)
        return {"entity": "change", "action": "create", "change_id": str(item.id)}

    if act == "edit":
        item = await _load(db, PmoChange, sub)
        if item is None:
            raise ValueError("change not found")
        patch = ChangeUpdate.model_validate(pv)
        for k, v in patch.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        _change_decision(item)
        return {"entity": "change", "action": "edit", "change_id": str(item.id)}

    if act == "delete":
        item = await _load(db, PmoChange, sub)
        if item is not None:
            await db.delete(item)
        return {"entity": "change", "action": "delete", "change_id": str(sub.target_entity_id)}

    raise ValueError(f"unknown change action: {act!r}")


async def _apply_charter(db, sub, author, act, pv) -> dict:
    if act == "create":
        if await _already(db, PmoCharter, sub):
            return {"entity": "charter", "action": "create",
                    "charter_id": str(sub.target_entity_id), "idempotent": True}
        payload = CharterCreate.model_validate(pv)
        # один устав на проект — если уже есть, возвращаем существующий (как роут)
        if payload.project_id is not None:
            existing = (await db.execute(
                select(PmoCharter).where(
                    PmoCharter.company_id == sub.target_company_id,
                    PmoCharter.project_id == payload.project_id,
                )
            )).scalar_one_or_none()
            if existing is not None:
                sub.target_entity_id = str(existing.id)
                return {"entity": "charter", "action": "create",
                        "charter_id": str(existing.id), "idempotent": True}
        item = PmoCharter(company_id=sub.target_company_id, created_by=author.id,
                          **payload.model_dump())
        db.add(item)
        await db.flush()
        sub.target_entity_id = str(item.id)
        return {"entity": "charter", "action": "create", "charter_id": str(item.id)}

    if act == "edit":
        item = await _load(db, PmoCharter, sub)
        if item is None:
            raise ValueError("charter not found")
        patch = CharterUpdate.model_validate(pv)
        for k, v in patch.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        _charter_approval(item, author)
        return {"entity": "charter", "action": "edit", "charter_id": str(item.id)}

    if act == "delete":
        item = await _load(db, PmoCharter, sub)
        if item is not None:
            await db.delete(item)
        return {"entity": "charter", "action": "delete", "charter_id": str(sub.target_entity_id)}

    raise ValueError(f"unknown charter action: {act!r}")


async def _apply_status_report(db, sub, author, act, pv) -> dict:
    """Статус-отчёт = генерируемый снимок (только create). Пересобираем через
    штатный генератор, атрибутируя автору-предложившему."""
    if act != "create":
        raise ValueError(f"status_report supports only create, got {act!r}")
    if await _already(db, StatusReport, sub):
        return {"entity": "status_report", "action": "create",
                "report_id": str(sub.target_entity_id), "idempotent": True}
    company = (await db.execute(
        select(Company).where(Company.id == sub.target_company_id)
    )).scalar_one_or_none()
    if company is None:
        raise ValueError("status_report requires a valid company")
    project_id = pv.get("project_id")
    if project_id is not None:
        project_id = UUID(str(project_id))
    rep = await generate_status_report(
        db, company.code, project_id, bool(pv.get("use_ai", False)),
        author.id, date.today(),
    )
    if rep is None:
        raise ValueError("status_report generation returned nothing")
    sub.target_entity_id = str(rep.id)
    return {"entity": "status_report", "action": "create", "report_id": str(rep.id)}


# Простые сущности: create = Model(company_id, created_by, **dump), edit/delete —
# setattr/удаление без доп. логики.
_SIMPLE: dict[str, tuple] = {
    "sprint": (PmoSprint, SprintCreate, SprintUpdate),
    "raci": (PmoRaci, RaciCreate, RaciUpdate),
    "stakeholder": (PmoStakeholder, StakeholderCreate, StakeholderUpdate),
    "lesson": (PmoLesson, LessonCreate, LessonUpdate),
}


async def _apply_simple(db, sub, author, act, pv, entity) -> dict:
    model, create_schema, update_schema = _SIMPLE[entity]
    if act == "create":
        if await _already(db, model, sub):
            return {"entity": entity, "action": "create",
                    "id": str(sub.target_entity_id), "idempotent": True}
        payload = create_schema.model_validate(pv)
        item = model(company_id=sub.target_company_id, created_by=author.id,
                     **payload.model_dump())
        db.add(item)
        await db.flush()
        sub.target_entity_id = str(item.id)
        return {"entity": entity, "action": "create", "id": str(item.id)}

    if act == "edit":
        item = await _load(db, model, sub)
        if item is None:
            raise ValueError(f"{entity} not found")
        patch = update_schema.model_validate(pv)
        for k, v in patch.model_dump(exclude_unset=True).items():
            setattr(item, k, v)
        return {"entity": entity, "action": "edit", "id": str(item.id)}

    if act == "delete":
        item = await _load(db, model, sub)
        if item is not None:
            await db.delete(item)
        return {"entity": entity, "action": "delete", "id": str(sub.target_entity_id)}

    raise ValueError(f"unknown {entity} action: {act!r}")


# ════════════════════════════════════════════════════════════════════════

async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    pv = dict(sub.proposed_value or {})
    entity = str(pv.get("_entity") or "").lower()
    act = _norm(sub.action or "")
    if not entity:
        raise ValueError("pmo apply requires proposed_value['_entity']")

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user

    if entity == "dependency":
        return await _apply_dependency(db, sub, author, act, pv)
    if entity == "raid":
        return await _apply_raid(db, sub, author, act, pv)
    if entity == "change":
        return await _apply_change(db, sub, author, act, pv)
    if entity == "charter":
        return await _apply_charter(db, sub, author, act, pv)
    if entity == "status_report":
        return await _apply_status_report(db, sub, author, act, pv)
    if entity in _SIMPLE:
        return await _apply_simple(db, sub, author, act, pv, entity)

    raise ValueError(f"unknown pmo entity: {entity!r}")


register_apply_handler("pmo", apply)
