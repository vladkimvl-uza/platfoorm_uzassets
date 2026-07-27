"""Activity notifications — every meaningful change across the platform.

Drives an in-app notification feed from the audit middleware (the single
chokepoint that sees every mutating request), so no per-endpoint wiring:

  • OWNERs get notified of EVERY change (unrestricted).
  • Scoped users (e.g. organization users) get notified only of changes in the
    companies they can access — resolved from the request path / entity.

Status changes, comments, file uploads and any data edited through the module
editors (KPI/financials/ESG/governance/ratings/BP/credit/investment/…) all flow
through here. Delivery is IN-APP ONLY (the bell) — Telegram/e-mail per change
would be spam — and throttled per (recipient, module, actor) so the KPI editor's
1.5s auto-save can't flood the feed. The actor is never notified of their own
action.

Company-scope note: when the affected company can't be resolved from the path
(e.g. POST /comments has the task id only in the body), we fall back to notifying
OWNERs only; participants/mentioned users are still covered by their own
dedicated notifications.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.models.notification import Notification
from app.services.notifications_service import notify

log = logging.getLogger(__name__)


# Ключи тела, из которых берём человекочитаемое НАЗВАНИЕ записи (для «что изменено»).
_DESCRIPTOR_KEYS = (
    "metric_name", "product_name", "committee_name", "name", "title", "label",
    "name_ru", "name_short", "short_title", "full_name",
    "agency", "rating", "product",
)
# Ключи тела, указывающие на компанию (для scope получателей + контекста).
_COMPANY_REF_KEYS = ("company_id", "company_code", "company", "code")


def extract_descriptor(data: object, depth: int = 2) -> Optional[str]:
    """Человекочитаемое название записи из JSON (тело запроса ИЛИ ответа).

    Ищет whitelist-ключи на верхнем уровне, затем на один-два уровня вглубь
    (upsert-payload'ы часто оборачивают запись: {"record": {...}}, список строк
    и т.п.). Только строки; секретов не берём (whitelist). None — не нашли."""
    if depth < 0:
        return None
    if isinstance(data, list):
        for item in data[:5]:
            found = extract_descriptor(item, depth - 1)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None
    for dk in _DESCRIPTOR_KEYS:
        v = data.get(dk)
        if isinstance(v, str) and v.strip():
            return v.strip()[:120]
    for v in list(data.values())[:25]:
        if isinstance(v, dict | list):
            found = extract_descriptor(v, depth - 1)
            if found:
                return found
    return None


async def capture_activity(request: Request) -> None:
    """FastAPI-зависимость (router-level): снимает из JSON-тела ДО обработчика —
    имена полей (что за область изменена), название записи и ссылку на компанию —
    чтобы уведомление об изменении показало «что именно изменено» по ВСЕМ модулям
    без ручной проводки в каждом роуте. Тело кэшируется Starlette → Pydantic всё
    равно распарсит его из кэша. Только мутации с JSON-телом; multipart/файлы и
    пустые тела не трогаем. Значений-секретов не берём (только whitelist-ключи)."""
    m = (request.method or "").upper()
    if m not in ("POST", "PUT", "PATCH"):
        return
    if "application/json" not in (request.headers.get("content-type", "") or "").lower():
        return
    try:
        body = await request.json()
    except Exception:
        return
    d = body if isinstance(body, dict) else (
        body[0] if isinstance(body, list) and body and isinstance(body[0], dict) else None)
    if not d:
        return
    st = request.state
    try:
        st.activity_body_keys = [str(k) for k in d.keys()][:40]
        # Название записи — с рекурсией: upsert-тела часто оборачивают запись
        # ({"records": [...]}, {"record": {...}}), верхнего уровня недостаточно.
        desc = extract_descriptor(body)
        if desc:
            st.activity_descriptor = desc
        for ck in _COMPANY_REF_KEYS:
            v = d.get(ck)
            if isinstance(v, str) and v.strip():
                st.activity_company_ref = v.strip()[:64]
                break
    except Exception:
        pass

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_THROTTLE_MINUTES = 10

# Path-prefix → (human label, module slug). Order: longest/specific first.
# slug = чистый идентификатор модуля для source_module → секции сайдбара.
_PATH_LABELS: list[tuple[str, str, str]] = [
    ("/business-plan", "Бизнес-план", "business_plan"),
    ("/credit-portfolio", "Кредитный портфель", "finance"),
    ("/invest-projects", "Инвест-проекты", "investment"),
    ("/tasks", "Задачи", "tasks"),
    ("/projects", "Проекты", "tasks"),
    ("/comments", "Комментарии", "tasks"),
    ("/attachments", "Файлы", "tasks"),
    ("/kpi", "KPI", "kpi"),
    ("/financials", "Финансы", "finance"),
    ("/bp", "Бизнес-план", "business_plan"),
    ("/esg", "ESG", "esg"),
    ("/governance", "Корпоративное управление", "governance"),
    ("/ratings", "Рейтинги", "ratings"),
    ("/credit", "Кредитный портфель", "finance"),
    ("/investment", "Инвест-проекты", "investment"),
    ("/finmodel", "Финмодель", "finance"),
    ("/treasury", "Казначейство", "finance"),
    ("/procurement", "Закупки", "procurement"),
    ("/companies", "Компании", "companies"),
    ("/notes", "Заметки", "tasks"),
    ("/elasticity", "Эластичность", "finance"),
]


def _classify(path: str) -> Optional[tuple[str, str]]:
    """→ (label, slug) либо None."""
    p = path.split("?", 1)[0]
    for pre, label, slug in _PATH_LABELS:
        if p == pre or p.startswith(pre + "/"):
            return label, slug
    return None


def _verb(method: str, path: str) -> str:
    if path.startswith("/comments") and method == "POST":
        return "новый комментарий"
    if path.startswith("/attachments") and method == "POST":
        return "загружен файл"
    return {
        "POST": "добавление", "PUT": "изменение",
        "PATCH": "изменение", "DELETE": "удаление",
    }.get(method, "изменение")


def _is_uuid(s: str) -> bool:
    return bool(_UUID_RE.match(s or ""))


async def _company_id_from_token(db: AsyncSession, token: str) -> Optional[UUID]:
    if _is_uuid(token):
        return (await db.execute(
            text("SELECT id FROM companies WHERE id = :i"), {"i": token}
        )).scalar()
    return (await db.execute(
        text("SELECT id FROM companies WHERE code = :c"), {"c": token}
    )).scalar()


async def _resolve_company_id(db: AsyncSession, path: str) -> Optional[UUID]:
    """Best-effort: affected company id from the request path. None if unknown."""
    parts = [p for p in path.split("?", 1)[0].split("/") if p and p not in ("api", "v1")]
    if not parts:
        return None
    head = parts[0].lower()
    # .../companies/{code|uuid}/...
    if "companies" in parts:
        i = parts.index("companies")
        if i + 1 < len(parts):
            return await _company_id_from_token(db, parts[i + 1])
    # /kpi/{company_uuid}/{year}
    if head == "kpi" and len(parts) >= 2 and _is_uuid(parts[1]):
        return await _company_id_from_token(db, parts[1])
    # /tasks/{uuid} | /projects/{uuid} → resolve via the entity's company_id
    if head in ("tasks", "projects") and len(parts) >= 2 and _is_uuid(parts[1]):
        tbl = "tasks" if head == "tasks" else "projects"
        return (await db.execute(
            text(f"SELECT company_id FROM {tbl} WHERE id = :i"), {"i": parts[1]}
        )).scalar()
    return None


def _resolve_link(path: str) -> Optional[str]:
    """Ссылка на затронутую сущность (для клика по уведомлению → открыть карточку)."""
    parts = [p for p in path.split("?", 1)[0].split("/") if p and p not in ("api", "v1")]
    if not parts:
        return None
    head = parts[0].lower()
    if head in ("tasks", "projects") and len(parts) >= 2 and _is_uuid(parts[1]):
        return f"/{head}/{parts[1]}"
    return None


async def _resolve_entity_title(db: AsyncSession, path: str) -> Optional[str]:
    """Название затронутой сущности (задача/проект/заметка), если id есть в пути.
    Для POST-создания id в пути нет → None (название не подтянуть)."""
    parts = [p for p in path.split("?", 1)[0].split("/") if p and p not in ("api", "v1")]
    if not parts:
        return None
    head = parts[0].lower()
    tbl = {"tasks": "tasks", "projects": "projects", "notes": "notes"}.get(head)
    if tbl and len(parts) >= 2 and _is_uuid(parts[1]):
        col = "title" if tbl != "notes" else "COALESCE(title, left(body, 80))"
        try:
            return (await db.execute(
                text(f"SELECT {col} FROM {tbl} WHERE id = :i"), {"i": parts[1]}
            )).scalar()
        except Exception:
            return None
    return None


async def _company_name(db: AsyncSession, company_id: Optional[UUID]) -> Optional[str]:
    """Имя компании для контекста уведомления («ESG · Узбекнефтегаз»)."""
    if company_id is None:
        return None
    try:
        return (await db.execute(
            text("SELECT COALESCE(name_short, name_ru, code) FROM companies WHERE id = :i"),
            {"i": str(company_id)},
        )).scalar()
    except Exception:
        return None


_OWNERS_SQL = "SELECT id FROM users WHERE is_owner = true AND is_active = true"

# Active users who can access a given company: owners, companies.view_all holders,
# members of a group bound to the company, and users whose allowed_sectors covers
# the company's sector.
_COMPANY_RECIPIENTS_SQL = """
SELECT DISTINCT u.id
FROM users u
WHERE u.is_active = true AND (
    u.is_owner = true
    OR EXISTS (
        SELECT 1 FROM user_group_role ugr
        JOIN groups g ON g.id = ugr.group_id
        WHERE ugr.user_id = u.id AND g.company_id = :cid
    )
    OR (
        u.allowed_sectors IS NOT NULL
        AND u.allowed_sectors @> jsonb_build_array(
            (SELECT s.code FROM sectors s
             JOIN companies c ON c.sector_id = s.id WHERE c.id = :cid)
        )
    )
    OR EXISTS (
        SELECT 1 FROM user_role ur
        JOIN role_permission rp ON rp.role_id = ur.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE ur.user_id = u.id AND p.code = 'companies.view_all'
    )
)
"""


async def _recipients(db: AsyncSession, company_id: Optional[UUID]) -> list[UUID]:
    if company_id is None:
        rows = (await db.execute(text(_OWNERS_SQL))).scalars().all()
    else:
        rows = (await db.execute(
            text(_COMPANY_RECIPIENTS_SQL), {"cid": str(company_id)}
        )).scalars().all()
    return list(rows)


# Рус. лейблы полей — для детали «Изменено: статус, срок». Покрывают все модули
# (задачи/проекты + финансы/ESG/рейтинги/корп.упр./KPI/БП/закупки/себестоимость),
# т.к. changed_fields теперь приходят из ключей тела запроса по всем разделам.
_FIELD_LABELS: dict[str, str] = {
    # задачи / проекты / общее
    "title": "название", "name": "название", "description": "описание",
    "status": "статус", "due_date": "срок", "start_date": "дата начала",
    "assignee_id": "исполнитель", "assignee_email": "исполнитель", "assignees": "исполнители",
    "consultant_ids": "консультанты", "consultants": "консультанты",
    "priority": "приоритет", "direction_id": "направление",
    "tags": "теги", "progress": "прогресс", "progress_pct": "прогресс",
    "result": "результат", "is_result": "результат",
    "notes": "примечание", "comment": "комментарий", "comments": "комментарии",
    "color": "цвет", "sector": "сектор", "is_active": "активность",
    # финансы / бизнес-план / HLF
    "revenue": "выручка", "ebitda": "EBITDA", "net_profit": "чистая прибыль",
    "gross_profit": "валовая прибыль", "assets": "активы", "liabilities": "обязательства",
    "equity": "капитал", "cash": "денежные средства", "opex": "операц. расходы",
    "capex": "капзатраты", "debt": "долг", "plan": "план", "fact": "факт",
    "metric_key": "показатель", "metrics": "показатели", "records": "записи",
    "lines": "статьи", "values": "значения", "amount": "сумма", "currency": "валюта",
    # KPI
    "indicators": "показатели", "weight": "вес", "direction": "направление",
    "managers": "ответственные", "target": "цель", "value": "значение",
    # ESG
    "issues": "риски/вопросы", "swot": "SWOT", "pillar": "компонент",
    "score": "оценка", "e": "экология", "s": "социальное", "g": "управление",
    # рейтинги
    "rating": "рейтинг", "agency": "агентство", "outlook": "прогноз",
    "scale": "шкала", "report_url": "ссылка на отчёт", "is_esg": "ESG-флаг", "date": "дата",
    # корп. управление
    "board_members": "совет директоров", "committees": "комитеты",
    "meetings": "заседания", "decisions": "решения", "chairman": "председатель",
    "members": "состав", "is_independent": "независимость", "email": "e-mail", "phone": "телефон",
    # закупки
    "contracts": "договоры", "savings": "экономия", "suppliers": "поставщики", "lots": "лоты",
    # себестоимость
    "products": "продукты", "imports": "импорт", "energy": "энергоресурсы",
    "norm": "норма расхода", "output": "выпуск", "components": "статьи затрат",
    # назначения / консультанты
    "assignments": "назначения", "consultant": "консультант", "tasks": "задачи",
}
# Внутренние/служебные поля — не показываем в «Изменено» (не несут смысла читателю).
# year/period/quarter/code — это КОНТЕКСТ записи (какой год/период), а не «что
# изменено», поэтому тоже скрываем из списка полей.
_FIELD_HIDDEN = {
    "num", "id", "project_id", "board_id", "parent_id", "company_id", "company_code",
    "code", "year", "period", "quarter", "portfolio_year",
    "sort_order", "position", "order", "updated_at", "created_at",
}


# Человекочитаемые статусы задач/проектов (для детали «Статус: Новая → Завершено»).
_STATUS_RU: dict[str, str] = {
    "init": "Инициация", "new": "Новая", "active": "В работе", "review": "На проверке",
    "done": "Завершено", "quarterly": "Квартальная", "monthly": "Ежемесячная",
    "ongoing": "Постоянная", "deferred": "Перенесена", "blocked": "Заблокирована",
}


def status_label(code: Optional[str]) -> str:
    s = str(code or "").strip()
    return _STATUS_RU.get(s, s or "—")


def _humanize_fields(keys: Optional[list[str]]) -> list[str]:
    """Ключи → рус. лейблы. Незамапленные ключи ОТБРАСЫВАЕМ (не показываем сырые
    англ. имена вроде metric_code): тело upsert-а несёт всю запись, поэтому список
    ключей — это «какая область затронута», и чистый рус. список читается лучше
    сырого. Замапленные поля (задачи/финансы/ESG/…) покрывают все ходовые случаи."""
    if not keys:
        return []
    out: list[str] = []
    for k in keys:
        if k in _FIELD_HIDDEN:
            continue
        lbl = _FIELD_LABELS.get(k)
        if not lbl:                    # неизвестное поле — не шумим сырым ключом
            continue
        if lbl not in out:
            out.append(lbl)
    return out


async def notify_owners_of_change(
    db: AsyncSession,
    *,
    http_path: str,
    http_method: str,
    status: int,
    actor_id: Optional[str],
    actor_email: Optional[str],
    changed_fields: Optional[list[str]] = None,
    summary: Optional[str] = None,
    entity_override: Optional[str] = None,
    descriptor: Optional[str] = None,
    company_ref: Optional[str] = None,
) -> None:
    """Best-effort: notify everyone with access to the affected company (OWNERs
    always; scoped users only for their companies) of a change. Only fires for
    successful mutating requests on a recognised data module. Throttled per
    (recipient, module, actor)."""
    method = (http_method or "").upper()
    if method not in _MUTATING or status >= 400:
        return
    classified = _classify(http_path or "")
    if classified is None:
        return
    label, slug = classified

    actor_uuid: Optional[UUID] = None
    if actor_id:
        try:
            actor_uuid = UUID(str(actor_id))
        except (ValueError, TypeError):
            actor_uuid = None

    company_id = await _resolve_company_id(db, http_path or "")
    # Компания часто приходит в ТЕЛЕ (напр. PUT /esg/metric с company_id в payload),
    # а не в пути → добираем из captured company_ref, чтобы верно заскоупить
    # получателей и показать компанию в контексте.
    if company_id is None and company_ref:
        company_id = await _company_id_from_token(db, company_ref)
    recipient_ids = await _recipients(db, company_id)

    verb = _verb(method, (http_path or "").split("?", 1)[0])
    # Название записи: явный override роута → описатель из тела/ответа (имя
    # показателя/записи) → подтянутое из пути (задача/проект) → имя компании.
    co_name = await _company_name(db, company_id)
    entity_title = (entity_override or descriptor
                    or await _resolve_entity_title(db, http_path or "")
                    or co_name)
    fields = _humanize_fields(changed_fields)
    link = _resolve_link(http_path or "")
    title = f"{label}: {verb}"
    body = actor_email or "пользователь"
    since = datetime.now(UTC) - timedelta(minutes=_THROTTLE_MINUTES)

    for rid in recipient_ids:
        if actor_uuid is not None and rid == actor_uuid:
            continue  # never notify the actor of their own action
        try:
            dup = (await db.execute(
                select(Notification.id).where(
                    Notification.recipient_user_id == rid,
                    Notification.type == "owner.activity",
                    Notification.source_module == slug,
                    Notification.source_user_id == actor_uuid,
                    Notification.created_at > since,
                ).limit(1)
            )).first()
            if dup is not None:
                continue
            await notify(
                db,
                recipient_id=rid,
                type="owner.activity",
                title=title,
                body=body,
                source_module=slug,
                source_entity_id=(http_path or "")[:256],
                source_user_id=actor_uuid,
                company_id=company_id,
                payload={"action": "activity", "verb": verb, "label": label,
                         "entity_title": entity_title, "fields": fields,
                         # Компания — ВСЕГДА отдельным полем (контекст «у кого»),
                         # а не только как fallback названия записи.
                         "company": co_name,
                         # detail_text: человеческая деталь от роута
                         # («Выручка 2025: 1 200 млрд», «Статус: Новая → Завершено»).
                         "detail_text": summary},
                link_url=link,
                in_app_only=True,
                commit=True,
            )
        except Exception as e:  # noqa: BLE001 — never break the request path
            log.warning("activity notify failed for user=%s: %s", rid, e)
