"""ERP-конструктор (Фаза 0) — движок записей поверх метамодели.

Endpoints:
  GET    /erp/entities                     — список сущностей
  GET    /erp/entities/{code}              — сущность + поля (для рендерера)
  GET    /erp/companies                    — справочник компаний (для scope)
  GET    /erp/records/{entity_code}        — список записей (scoped)
  POST   /erp/records/{entity_code}        — создать (валидация + аудит)
  PATCH  /erp/records/{id}                 — обновить
  DELETE /erp/records/{id}                 — архивировать

Краевые случаи (Eng Manager):
  • company-scoped сущность без company_id → 400.
  • unique_scoped поле — проверка в рамках (entity, company).
  • неизвестное значение select / нечисло в number → 422 с понятным текстом.
  • запись чужой сущности в PATCH → 404.
  • аудит/owner-firehose — на каждое создание/правку (module="erp").
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.company import Company
from app.models.metamodel import FIELD_TYPES, MMEntity, MMField, MMRecord
from app.models.user import User

router = APIRouter(prefix="/erp", tags=["erp"])

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


def _require_builder(user: User) -> None:
    """Конструктор схемы — только владелец/админ."""
    if getattr(user, "is_owner", False):
        return
    roles = [getattr(r, "code", "") for r in (getattr(user, "roles", None) or [])]
    if "admin" in roles:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Конструктор доступен только владельцу/админу")


# ─── сериализация определений ──────────────────────────────────────

def _entity_out(e: MMEntity) -> dict:
    return {
        "code": e.code, "name": e.name, "name_plural": e.name_plural or e.name,
        "icon": e.icon, "module": e.module, "pack": e.pack,
        "is_company_scoped": e.is_company_scoped, "title_field": e.title_field,
    }


def _field_out(f: MMField) -> dict:
    return {
        "id": str(f.id),
        "code": f.code, "label": f.label, "type": f.type, "grp": f.grp,
        "required": f.required, "unique_scoped": f.unique_scoped,
        "options": f.options, "ref_entity_code": f.ref_entity_code,
        "unit": f.unit, "validation": f.validation, "help": f.help,
        "show_in_list": f.show_in_list, "sort": f.sort,
    }


async def _fields_for(db: AsyncSession, entity_code: str) -> list[MMField]:
    return list((await db.execute(
        select(MMField).where(MMField.entity_code == entity_code).order_by(MMField.sort, MMField.label),
    )).scalars().all())


# ─── валидатор записи против определения полей ─────────────────────

def _validate(fields: list[MMField], data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    errors: list[str] = []
    for f in fields:
        v = data.get(f.code)
        empty = v is None or v == "" or v == []
        if empty:
            if f.required:
                errors.append(f"«{f.label}» — обязательное поле")
            dv = (f.default_value or {}).get("v") if isinstance(f.default_value, dict) else None
            out[f.code] = dv
            continue
        t = f.type
        if t in ("number", "money"):
            try:
                v = float(v)
            except (TypeError, ValueError):
                errors.append(f"«{f.label}» — должно быть числом")
                continue
            val = f.validation or {}
            if "min" in val and v < val["min"]:
                errors.append(f"«{f.label}» — не меньше {val['min']}")
            if "max" in val and v > val["max"]:
                errors.append(f"«{f.label}» — не больше {val['max']}")
        elif t == "bool":
            v = bool(v)
        elif t == "select":
            allowed = [o.get("value") for o in (f.options or [])]
            if allowed and v not in allowed:
                errors.append(f"«{f.label}» — недопустимое значение")
        else:  # text/textarea/date/datetime/ref/user
            v = str(v)
        out[f.code] = v
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "; ".join(errors))
    return out


def _title(entity: MMEntity, data: dict) -> str:
    if entity.title_field and data.get(entity.title_field):
        return str(data[entity.title_field])
    # первый непустой текст
    for k, v in (data or {}).items():
        if isinstance(v, str) and v.strip():
            return v
    return entity.name


async def _audit(db, *, user: User, action: str, entity: MMEntity, rec_id, title: str):
    try:
        from app.services import audit_service
        verb = {"erp.create": "создал", "erp.update": "изменил", "erp.delete": "удалил"}.get(action, action)
        await audit_service.write_event(
            db, actor_id=user.id, actor_email=user.email,
            actor_role=(user.roles[0].code if getattr(user, "roles", None) else None),
            action=action, module="erp",
            entity_type=entity.code, entity_id=str(rec_id),
            entity_label=f"{entity.name}: {title}"[:140],
            notes=f"{verb} «{entity.name}»: {title}",
            meta={"link": f"/erp?entity={entity.code}"},
            is_critical=(action == "erp.delete"),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("erp audit failed", exc_info=True)


# ─── endpoints: определения ────────────────────────────────────────

@router.get("/entities")
async def list_entities(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(MMEntity).where(MMEntity.is_active.is_(True)).order_by(MMEntity.sort, MMEntity.name),
    )).scalars().all()
    can_build = bool(getattr(user, "is_owner", False)) or "admin" in [
        getattr(r, "code", "") for r in (getattr(user, "roles", None) or [])
    ]
    return {"items": [_entity_out(e) for e in rows], "can_build": can_build}


@router.get("/entities/{code}")
async def get_entity(code: str, db: AsyncSession = Depends(get_db), _u: User = Depends(get_current_user)):
    e = (await db.execute(select(MMEntity).where(MMEntity.code == code))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Сущность не найдена")
    fields = await _fields_for(db, code)
    return {"entity": _entity_out(e), "fields": [_field_out(f) for f in fields]}


@router.get("/companies")
async def erp_companies(db: AsyncSession = Depends(get_db), _u: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(Company.id, Company.code, Company.name_short, Company.name_ru).order_by(Company.name_ru),
    )).all()
    return {"items": [
        {"id": str(r._mapping["id"]), "code": r._mapping["code"],
         "name": r._mapping["name_short"] or r._mapping["name_ru"]}
        for r in rows
    ]}


# ─── КОНСТРУКТОР: сущности и поля (owner/admin) ────────────────────

class EntityIn(BaseModel):
    code: str
    name: str
    name_plural: Optional[str] = None
    icon: Optional[str] = None
    module: Optional[str] = None
    pack: Optional[str] = None
    is_company_scoped: bool = True
    title_field: Optional[str] = None


class EntityPatch(BaseModel):
    name: Optional[str] = None
    name_plural: Optional[str] = None
    icon: Optional[str] = None
    module: Optional[str] = None
    title_field: Optional[str] = None
    is_active: Optional[bool] = None


class FieldIn(BaseModel):
    code: str
    label: str
    type: str = "text"
    grp: Optional[str] = None
    sort: Optional[int] = None
    required: bool = False
    unique_scoped: bool = False
    options: Optional[list] = None
    ref_entity_code: Optional[str] = None
    unit: Optional[str] = None
    validation: Optional[dict] = None
    help: Optional[str] = None
    show_in_list: bool = True


@router.post("/entities", status_code=201)
async def create_entity(body: EntityIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _require_builder(user)
    if not _CODE_RE.match(body.code):
        raise HTTPException(422, "code: латиница/цифры/_ , начинается с буквы")
    if (await db.execute(select(func.count()).where(MMEntity.code == body.code))).scalar():
        raise HTTPException(409, "Сущность с таким code уже есть")
    sort = ((await db.execute(select(func.max(MMEntity.sort)))).scalar() or 0) + 1
    e = MMEntity(code=body.code, name=body.name, name_plural=body.name_plural or body.name,
                 icon=body.icon, module=body.module, pack=body.pack or "custom",
                 is_company_scoped=body.is_company_scoped, title_field=body.title_field, sort=sort)
    db.add(e)
    await db.commit()
    return _entity_out(e)


@router.patch("/entities/{code}")
async def patch_entity(code: str, body: EntityPatch, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _require_builder(user)
    e = await _load_entity(db, code)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    await db.commit()
    return _entity_out(e)


@router.delete("/entities/{code}", status_code=204)
async def deactivate_entity(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _require_builder(user)
    e = await _load_entity(db, code)
    e.is_active = False
    await db.commit()


@router.post("/entities/{code}/fields", status_code=201)
async def add_field(code: str, body: FieldIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _require_builder(user)
    await _load_entity(db, code)
    if not _CODE_RE.match(body.code):
        raise HTTPException(422, "code поля: латиница/цифры/_ , с буквы")
    if body.type not in FIELD_TYPES:
        raise HTTPException(422, f"type: один из {', '.join(FIELD_TYPES)}")
    dup = (await db.execute(select(func.count()).where(
        MMField.entity_code == code, MMField.code == body.code,
    ))).scalar()
    if dup:
        raise HTTPException(409, "Поле с таким code уже есть")
    sort = body.sort if body.sort is not None else (
        ((await db.execute(select(func.max(MMField.sort)).where(MMField.entity_code == code))).scalar() or 0) + 1
    )
    f = MMField(entity_code=code, code=body.code, label=body.label, type=body.type,
                grp=body.grp, sort=sort, required=body.required, unique_scoped=body.unique_scoped,
                options=body.options, ref_entity_code=body.ref_entity_code, unit=body.unit,
                validation=body.validation, help=body.help, show_in_list=body.show_in_list)
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return _field_out(f)


@router.patch("/fields/{field_id}")
async def patch_field(field_id: str, body: FieldIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _require_builder(user)
    try:
        fid = UUID(field_id)
    except Exception:
        raise HTTPException(400, "bad id")
    f = await db.get(MMField, fid)
    if not f:
        raise HTTPException(404, "Поле не найдено")
    if body.type not in FIELD_TYPES:
        raise HTTPException(422, "Недопустимый тип")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "code":
            continue  # code поля не меняем (иначе осиротеют данные)
        setattr(f, k, v)
    await db.commit()
    return _field_out(f)


@router.delete("/fields/{field_id}", status_code=204)
async def delete_field(field_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _require_builder(user)
    try:
        fid = UUID(field_id)
    except Exception:
        raise HTTPException(400, "bad id")
    f = await db.get(MMField, fid)
    if not f:
        raise HTTPException(404, "Поле не найдено")
    await db.delete(f)
    await db.commit()


# ─── endpoints: записи ─────────────────────────────────────────────

async def _load_entity(db, code: str) -> MMEntity:
    e = (await db.execute(select(MMEntity).where(MMEntity.code == code))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Сущность не найдена")
    return e


@router.get("/records/{entity_code}")
async def list_records(
    entity_code: str,
    company_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    await _load_entity(db, entity_code)
    conds = [MMRecord.entity_code == entity_code, MMRecord.is_archived.is_(False)]
    if company_id:
        try:
            conds.append(MMRecord.company_id == UUID(company_id))
        except Exception:
            raise HTTPException(400, "Некорректный company_id")
    rows = (await db.execute(
        select(MMRecord).where(and_(*conds)).order_by(MMRecord.created_at.desc()).limit(500),
    )).scalars().all()
    items = []
    for r in rows:
        if search:
            blob = " ".join(str(v) for v in (r.data or {}).values()).lower()
            if search.lower() not in blob:
                continue
        items.append({
            "id": str(r.id), "company_id": str(r.company_id) if r.company_id else None,
            "data": r.data, "state": r.state,
            "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat(),
        })
    return {"items": items, "total": len(items)}


async def _unique_guard(db, entity_code, company_id, fields, data, exclude_id=None):
    for f in fields:
        if not f.unique_scoped:
            continue
        v = data.get(f.code)
        if v in (None, ""):
            continue
        conds = [
            MMRecord.entity_code == entity_code,
            MMRecord.is_archived.is_(False),
            MMRecord.data[f.code].astext == str(v),
        ]
        if company_id:
            conds.append(MMRecord.company_id == company_id)
        if exclude_id:
            conds.append(MMRecord.id != exclude_id)
        exists = (await db.execute(select(func.count()).where(and_(*conds)))).scalar() or 0
        if exists:
            raise HTTPException(status.HTTP_409_CONFLICT, f"«{f.label}» — уже существует ({v})")


@router.post("/records/{entity_code}", status_code=201)
async def create_record(
    entity_code: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = await _load_entity(db, entity_code)
    company_id = None
    if e.is_company_scoped:
        cid = body.get("company_id")
        if not cid:
            raise HTTPException(400, "Нужно выбрать компанию")
        try:
            company_id = UUID(cid)
        except Exception:
            raise HTTPException(400, "Некорректный company_id")
    fields = await _fields_for(db, entity_code)
    data = _validate(fields, body.get("data") or {})
    await _unique_guard(db, entity_code, company_id, fields, data)

    rec = MMRecord(entity_code=entity_code, company_id=company_id, data=data,
                   created_by=user.id, updated_by=user.id)
    db.add(rec)
    await _audit(db, user=user, action="erp.create", entity=e, rec_id=rec.id, title=_title(e, data))
    await db.commit()
    await db.refresh(rec)
    return {"id": str(rec.id), "data": rec.data,
            "company_id": str(rec.company_id) if rec.company_id else None}


@router.patch("/records/{rec_id}")
async def update_record(
    rec_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        rid = UUID(rec_id)
    except Exception:
        raise HTTPException(400, "Некорректный id")
    rec = await db.get(MMRecord, rid)
    if not rec or rec.is_archived:
        raise HTTPException(404, "Запись не найдена")
    e = await _load_entity(db, rec.entity_code)
    fields = await _fields_for(db, rec.entity_code)
    merged = {**(rec.data or {}), **(body.get("data") or {})}
    data = _validate(fields, merged)
    await _unique_guard(db, rec.entity_code, rec.company_id, fields, data, exclude_id=rid)
    rec.data = data
    rec.updated_by = user.id
    await _audit(db, user=user, action="erp.update", entity=e, rec_id=rec.id, title=_title(e, data))
    await db.commit()
    return {"id": str(rec.id), "data": rec.data}


@router.delete("/records/{rec_id}", status_code=204)
async def delete_record(
    rec_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        rid = UUID(rec_id)
    except Exception:
        raise HTTPException(400, "Некорректный id")
    rec = await db.get(MMRecord, rid)
    if not rec or rec.is_archived:
        raise HTTPException(404, "Запись не найдена")
    e = await _load_entity(db, rec.entity_code)
    rec.is_archived = True
    rec.updated_by = user.id
    await _audit(db, user=user, action="erp.delete", entity=e, rec_id=rec.id, title=_title(e, rec.data or {}))
    await db.commit()


# ─── seed: пак «Горнодобыча» (идемпотентно) ────────────────────────

_SEED_FIELDS = [
    {"code": "inv_no", "label": "Инвентарный №", "type": "text", "required": True, "unique_scoped": True, "sort": 1},
    {"code": "model", "label": "Модель", "type": "text", "required": True, "sort": 2},
    {"code": "kind", "label": "Тип", "type": "select", "sort": 3,
     "options": [{"value": "excavator", "label": "Экскаватор", "color": "#7C6FF7"},
                 {"value": "dumptruck", "label": "Самосвал", "color": "#EF9F27"},
                 {"value": "drill", "label": "Буровая", "color": "#378ADD"},
                 {"value": "loader", "label": "Погрузчик", "color": "#1D9E75"}]},
    {"code": "commissioned", "label": "Введён в эксплуатацию", "type": "date", "sort": 4},
    {"code": "hours", "label": "Наработка", "type": "number", "unit": "ч", "sort": 5, "validation": {"min": 0}},
    {"code": "book_value", "label": "Балансовая стоимость", "type": "money", "unit": "USD", "sort": 6, "validation": {"min": 0}},
    {"code": "status", "label": "Статус", "type": "select", "required": True, "sort": 7,
     "options": [{"value": "work", "label": "В работе", "color": "#1D9E75"},
                 {"value": "repair", "label": "Ремонт", "color": "#EF9F27"},
                 {"value": "idle", "label": "Простой", "color": "#E24B4A"}]},
    {"code": "note", "label": "Примечание", "type": "textarea", "sort": 8, "show_in_list": False},
]


async def seed_demo_pack(db: AsyncSession) -> None:
    """Идемпотентно создаёт демо-сущность «Карьерная техника» (пак Горнодобыча)."""
    try:
        exists = (await db.execute(
            select(func.count()).where(MMEntity.code == "mining_equipment"),
        )).scalar() or 0
        if exists:
            return
        ent = MMEntity(
            code="mining_equipment", name="Карьерная техника",
            name_plural="Карьерная техника", icon="truck", module="EAM",
            pack="mining", is_company_scoped=True, title_field="inv_no", sort=1,
        )
        db.add(ent)
        for f in _SEED_FIELDS:
            db.add(MMField(
                entity_code="mining_equipment",
                code=f["code"], label=f["label"], type=f["type"],
                sort=f.get("sort", 0), required=f.get("required", False),
                unique_scoped=f.get("unique_scoped", False),
                options=f.get("options"), unit=f.get("unit"),
                validation=f.get("validation"), show_in_list=f.get("show_in_list", True),
            ))
        await db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("erp seed failed", exc_info=True)
        await db.rollback()
