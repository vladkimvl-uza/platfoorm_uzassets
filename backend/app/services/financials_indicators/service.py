"""Company indicators editor — ИНН + годовые скалярные KPI.

Хранит метрики уровня компании (стандарт-агностично, один набор на компанию):
  - Company.inn                  — ИНН (одно значение)
  - Company.extra["indicators"]  — JSONB {field: {yearStr: float}} для
                                   sponsorship / taxes / headcount

Двунаправленно: GET читает, PUT upsert'ит (как единичную inline-правку
field+year, так и bulk-push всего набора по API). Мерж в extra не затирает
прочие ключи (ifrs_editor_schema_*, hlf и т.п.).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from fastapi import HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import has_effective_permission
from app.models.user import User
from app.repositories.financials_repository import FinancialsRepository

# Годовые скалярные индикаторы, которые умеет редактор (whitelist).
INDICATOR_FIELDS = ("sponsorship", "taxes", "headcount")


class IndicatorsUpsertPayload(BaseModel):
    """Тело PUT /companies/{code}/indicators.

    Поддерживает единичную inline-правку (один field/year) и bulk-push.
    - `set_inn=True` → применить `inn` (в т.ч. пустую строку/None как очистку).
    - `indicators` — мерж по field/year; значение None в ячейке = удалить год.
    """

    inn: Optional[str] = None
    set_inn: bool = False
    indicators: dict[str, dict[str, Optional[float]]] = Field(default_factory=dict)


def _clean_indicators(raw: Optional[dict]) -> dict[str, dict[str, float]]:
    """Привести extra['indicators'] к {field:{yearStr:float}} только по whitelist."""
    out: dict[str, dict[str, float]] = {}
    if not isinstance(raw, dict):
        return out
    for field in INDICATOR_FIELDS:
        ym = raw.get(field)
        if not isinstance(ym, dict):
            continue
        clean: dict[str, float] = {}
        for ys, v in ym.items():
            try:
                year = int(ys)
            except (TypeError, ValueError):
                continue
            if v is None:
                continue
            try:
                clean[str(year)] = float(v)
            except (TypeError, ValueError):
                continue
        if clean:
            out[field] = clean
    return out


def _indicators_diff_summary(payload: "IndicatorsUpsertPayload") -> str:
    """Короткое RU-описание правки для очереди модерации."""
    parts: list[str] = []
    if payload.set_inn:
        parts.append("ИНН")
    cells = sum(len(m or {}) for m in payload.indicators.values())
    if cells:
        parts.append(f"{cells} яч. показателей")
    return "Показатели компании: " + (", ".join(parts) if parts else "без изменений")


async def _apply_indicators_core(
    db: AsyncSession,
    *,
    company,
    payload: "IndicatorsUpsertPayload",
    user: User,
) -> dict:
    """Единая запись индикаторов (ИНН + годовые KPI) — общий код для ЖИВОГО
    пути и для APPLY одобренной заявки, чтобы не было расхождения.

    Выполняет мутацию и коммит, атрибутируя правку переданному `user`
    (на apply — автору заявки). Мерж не затирает прочие ключи `extra`
    (ifrs_editor_schema_*, hlf …) и правит только затронутые field/year —
    поэтому checksum/editor-token не нужен: параллельные правки ДРУГИХ ячеек
    сохраняются, а одна и та же ячейка — last-writer-wins (как и на прямом
    пути, у которого токена нет).
    """
    co = company

    # 1. ИНН (только при явном set_inn — иначе indicator-only правки его не трогают)
    if payload.set_inn:
        v = (payload.inn or "").strip()
        co.inn = v or None

    # 2. Мерж годовых индикаторов в extra['indicators'] (по whitelist).
    extra = dict(co.extra or {})
    ind = _clean_indicators(extra.get("indicators"))
    for field, year_map in payload.indicators.items():
        if field not in INDICATOR_FIELDS:
            continue
        cur = dict(ind.get(field) or {})
        for ys, val in year_map.items():
            try:
                year = int(ys)
            except (TypeError, ValueError):
                continue
            if val is None:
                cur.pop(str(year), None)
            else:
                try:
                    cur[str(year)] = float(val)
                except (TypeError, ValueError):
                    continue
        if cur:
            ind[field] = cur
        else:
            ind.pop(field, None)
    if ind:
        extra["indicators"] = ind
    else:
        extra.pop("indicators", None)
    extra["indicators_updated_at"] = datetime.now(UTC).isoformat()
    extra["indicators_updated_by"] = user.email
    co.extra = extra  # переприсваиваем — иначе JSONB-изменение не зафиксируется

    await db.commit()
    return {
        "code": co.code,
        "inn": co.inn,
        "indicators": _clean_indicators(co.extra.get("indicators")),
        "saved": True,
    }


async def apply_submission(db: AsyncSession, *, sub, user: User) -> dict:
    """Применить одобренную заявку на изменение показателей.

    Диспатчится из `app/services/moderation_apply/financials.py` (ветка
    action='indicators_save'). Резолвит компанию по коду в proposed_value,
    подгружает АВТОРА заявки для атрибуции (fallback — одобривший модератор),
    валидирует схему и зовёт общий write-core. Editor-token тут нет —
    re-валидация не нужна.
    """
    pv = dict(sub.proposed_value or {})
    if not pv:
        raise ValueError("proposed_value is empty")
    code = pv.get("code") or sub.target_entity_id
    if not code:
        raise ValueError("indicators_save requires company code in proposed_value")

    repo = FinancialsRepository(db)
    co = await repo.find_company_by_code(str(code))
    if co is None:
        raise ValueError(f"Company '{code}' no longer exists")

    try:
        payload = IndicatorsUpsertPayload.model_validate(
            {k: v for k, v in pv.items() if k != "code"}
        )
    except Exception as e:  # noqa: BLE001
        raise ValueError(
            f"proposed_value does not match IndicatorsUpsertPayload: {e}"
        ) from e

    proposer = (
        await db.get(User, sub.proposer_user_id) if sub.proposer_user_id else None
    )
    result = await _apply_indicators_core(
        db, company=co, payload=payload, user=proposer or user
    )
    return {
        "action": "indicators_save",
        "code": co.code,
        "inn": result.get("inn"),
        "saved": True,
    }


@dataclass
class FinancialsIndicatorsService:
    async def _load(self, code: str, db: AsyncSession, user: User, *, write: bool):
        perm = "financials.edit" if write else "financials.view"
        repo = FinancialsRepository(db)
        co = await repo.find_company_by_code(code)
        if not co:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                f"Company '{code}' not found",
            )
        if not await has_effective_permission(db, user, perm, company_id=co.id):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                f"Permission required: {perm}",
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and co.id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access")
        return co

    async def get_indicators(
        self, code: str, db: AsyncSession, user: User,
    ) -> dict:
        co = await self._load(code, db, user, write=False)
        extra = co.extra or {}
        return {
            "code": co.code,
            "inn": co.inn,
            "indicators": _clean_indicators(extra.get("indicators")),
            # employees_count — уровень-компании фолбэк «Сотрудники» (как на карточке,
            # когда годовой indicators.headcount не заполнен). Раньше не отдавался →
            # внешняя система не могла подтянуть численность.
            "employees_count": getattr(co, "employees_count", None),
            "updated_at": extra.get("indicators_updated_at"),
            "updated_by": extra.get("indicators_updated_by"),
        }

    async def indicators_summary(
        self, db: AsyncSession, user: User, *, field: str, year: int,
    ) -> dict:
        """Сумма годового индикатора (sponsorship/taxes/headcount) по портфелю —
        для KPI-карточки в Финансах. Scoped: company-scoped юзер видит только
        свои компании."""
        if field not in INDICATOR_FIELDS:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "unknown indicator field")
        if not await has_effective_permission(db, user, "financials.view"):
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: financials.view")
        repo = FinancialsRepository(db)
        companies = await repo.list_all_companies()
        scope_ids = await allowed_company_ids(db, user)
        ys = str(year)
        total = 0.0
        present = 0
        for co in companies:
            if scope_ids is not None and co.id not in scope_ids:
                continue
            # Флаг исключает компанию только из ПОРТФЕЛЬНОЙ суммы и счётчика покрытия.
            # При явной области выборка уже сужена вызывающим — иначе пользователь,
            # чья область состоит из такой компании, увидит нулевой KPI.
            if scope_ids is None and not co.include_in_rollups:
                continue
            ind = _clean_indicators((co.extra or {}).get("indicators"))
            v = (ind.get(field) or {}).get(ys)
            if v is not None:
                total += float(v)
                present += 1
        return {"field": field, "year": year, "total": total, "present": present}

    async def upsert_indicators(
        self,
        code: str,
        payload: IndicatorsUpsertPayload,
        db: AsyncSession,
        user: User,
    ) -> tuple[Optional[dict], Optional[dict]]:
        """Returns (result, None) на happy-path либо (None, queued_dict), если
        модерация задержала правку (роут превращает queued в HTTP 202).

        Контракт-двойник save_report: гейт стоит ПОСЛЕ проверок прав + per-company
        scope (внутри `_load`) и ДО любой мутации БД. У редактора нет editor-token.
        """
        co = await self._load(code, db, user, write=True)

        # Deny-by-default модерация. По умолчанию в проде выключена (allow-list) —
        # поведение не меняется, пока админ не включит модуль 'financials'.
        from app.services.moderation_service import gate_or_apply
        queued, sub = await gate_or_apply(
            db, user=user,
            module="financials", action="indicators_save",
            entity_id=co.code,
            entity_label=f"Показатели компании {co.code}",
            company_id=co.id, sector_id=None, year=None,
            payload={
                "code": co.code,
                "set_inn": bool(payload.set_inn),
                "inn": payload.inn,
                "indicators": payload.indicators,
            },
            editor_token=None,
            diff_summary=_indicators_diff_summary(payload),
        )
        if queued:
            return None, {
                "queued": True, "submission_id": str(sub.id),
                "status": sub.status,
                "message": "Изменение отправлено на модерацию",
            }

        result = await _apply_indicators_core(
            db, company=co, payload=payload, user=user
        )
        return result, None
