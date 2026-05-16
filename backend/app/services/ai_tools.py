"""
AI Tools — Pack 7.7.

15 tools total, schema-aware: handlers return ALL model columns via
SQLAlchemy introspection, so when new fields are added to models, they
automatically surface to Claude without code changes.

  Pack 7.5 (existing, schema-aware now):
    1. get_company_full
    2. list_overdue_tasks
    3. compare_companies
    4. search_tasks
  Pack 7.6 (existing):
    5. get_financials
    6. get_governance
    7. get_credit_portfolio
    8. get_kpi_summary
    9. search_audit_log
   10. get_ratings_history
  Pack 7.7 (new):
   11. get_task_details         — full task dump (comments + attachments + history + consultants)
   12. get_project_details      — project + tasks + comments
   13. search_comments          — across task/project/general comments
   14. list_consultants         — 17 consultants, optionally Big4 only, with assignment counts
   15. list_carried_over        — tasks/projects moved between years (linked_year != portfolio_year)
"""
from __future__ import annotations
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, desc, and_, or_, inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession


# ─────────────────── Constants & helpers ───────────────────

_DONE_STATUSES = {"done", "completed", "finished"}
_ACTIVE_STATUSES = {"active", "in_progress", "inprogress", "review"}

# Heavy/sensitive columns that we drop from generic introspection dumps
# (kept for explicit handlers that need them).
_HEAVY_COLUMNS = {"description", "extra"}


def _to_jsonable(v: Any) -> Any:
    """Convert SQLAlchemy values to JSON-serializable forms."""
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, Decimal):
        try:
            return float(v)
        except (TypeError, ValueError):
            return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [_to_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _to_jsonable(val) for k, val in v.items()}
    return str(v)


def _model_to_dict(obj: Any, *, include_heavy: bool = False, max_text: int = 300) -> dict:
    """
    Dump every column of an SQLAlchemy model instance to a JSON-friendly dict.
    Drops heavy columns (description, extra) by default — pass include_heavy
    when caller needs them. Truncates long text values.
    """
    if obj is None:
        return {}
    try:
        cols = sa_inspect(obj.__class__).columns.keys()
    except Exception:
        return {}
    out: dict = {}
    for col in cols:
        if not include_heavy and col in _HEAVY_COLUMNS:
            continue
        val = getattr(obj, col, None)
        jv = _to_jsonable(val)
        if isinstance(jv, str) and len(jv) > max_text:
            jv = jv[:max_text] + "…"
        out[col] = jv
    return out


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_overdue(deadline: Any, status: Optional[str]) -> bool:
    if status and status.lower() in _DONE_STATUSES:
        return False
    if not deadline:
        return False
    try:
        d = deadline.date() if isinstance(deadline, datetime) else deadline
        if not isinstance(d, date):
            return False
        return d < datetime.now(timezone.utc).date()
    except Exception:
        return False


def _is_carried_over(item: Any) -> bool:
    """A task/project is 'carried over' if linked_year is set and differs from portfolio_year."""
    py = getattr(item, "portfolio_year", None)
    ly = getattr(item, "linked_year", None)
    if ly is None:
        return False
    return py != ly


def _company_name(co: Any) -> str:
    for attr in ("name_ru", "name_short", "name_en", "name_uz", "code"):
        v = getattr(co, attr, None)
        if v:
            return str(v)
    return "?"


async def _find_company_by_name(db: AsyncSession, name: str) -> Optional[Any]:
    from app.models.company import Company  # type: ignore[import]
    if not name:
        return None
    q = name.strip().lower()
    res = await db.execute(select(Company))
    cos = list(res.scalars().all())
    for co in cos:
        for attr in ("name_ru", "name_short", "name_en", "name_uz", "code"):
            v = getattr(co, attr, None)
            if v and v.strip().lower() == q:
                return co
    for co in cos:
        for attr in ("name_ru", "name_short", "name_en", "name_uz", "code"):
            v = getattr(co, attr, None)
            if v and q in v.strip().lower():
                return co
    tokens = [t for t in q.split() if len(t) >= 4]
    for co in cos:
        for attr in ("name_ru", "name_short", "name_en", "name_uz"):
            v = getattr(co, attr, None)
            if v:
                vl = v.strip().lower()
                if any(t in vl for t in tokens):
                    return co
    return None


async def _build_lookup_maps(db: AsyncSession, *,
                              need_companies: bool = False,
                              need_directions: bool = False,
                              need_sectors: bool = False) -> dict[str, dict]:
    """Build id→name maps for joining."""
    out: dict[str, dict] = {}
    if need_companies:
        from app.models.company import Company  # type: ignore[import]
        r = await db.execute(select(Company))
        out["companies"] = {co.id: _company_name(co) for co in r.scalars().all()}
    if need_directions:
        from app.models.company import Direction  # type: ignore[import]
        r = await db.execute(select(Direction))
        out["directions"] = {d.id: getattr(d, "name_ru", None) or getattr(d, "code", "?")
                             for d in r.scalars().all()}
    if need_sectors:
        from app.models.company import Sector  # type: ignore[import]
        r = await db.execute(select(Sector))
        out["sectors"] = {s.id: getattr(s, "name_ru", None) or getattr(s, "code", "?")
                          for s in r.scalars().all()}
    return out


async def _consultants_for_tasks(db: AsyncSession, task_ids: list) -> dict[Any, list[dict]]:
    """Return {task_id: [{consultant_id, name, abbr, is_big4, source}]}"""
    if not task_ids:
        return {}
    try:
        from app.models.consultant import ConsultantAssignment, Consultant  # type: ignore[import]
    except ImportError:
        return {}
    a_res = await db.execute(
        select(ConsultantAssignment).where(ConsultantAssignment.task_id.in_(task_ids))
    )
    asses = list(a_res.scalars().all())
    if not asses:
        return {}
    cons_ids = list({a.consultant_id for a in asses})
    c_res = await db.execute(select(Consultant).where(Consultant.id.in_(cons_ids)))
    cons_map = {c.id: c for c in c_res.scalars().all()}
    out: dict[Any, list[dict]] = {}
    for a in asses:
        c = cons_map.get(a.consultant_id)
        if not c:
            continue
        out.setdefault(a.task_id, []).append({
            "id": str(c.id),
            "name": c.name_ru,
            "abbr": getattr(c, "abbr", None),
            "is_big4": bool(getattr(c, "is_big4", False)),
            "source": getattr(a, "source", None),
        })
    return out


def _enrich_task(t: Any, *, co_map: dict, dir_map: dict,
                 consultants_for: Optional[dict] = None,
                 include_heavy: bool = False) -> dict:
    """Build a rich task dict: all columns + resolved names + carried_over + consultants."""
    d = _model_to_dict(t, include_heavy=include_heavy)
    d["company"] = co_map.get(getattr(t, "company_id", None)) if co_map else None
    d["direction"] = dir_map.get(getattr(t, "direction_id", None)) if dir_map else None
    d["is_overdue"] = _is_overdue(getattr(t, "due_date", None), getattr(t, "status", None))
    d["is_carried_over"] = _is_carried_over(t)
    if consultants_for is not None:
        d["consultants"] = consultants_for.get(getattr(t, "id", None), [])
    return d


def _enrich_project(p: Any, *, co_map: dict, dir_map: dict,
                    include_heavy: bool = False) -> dict:
    d = _model_to_dict(p, include_heavy=include_heavy)
    d["company"] = co_map.get(getattr(p, "company_id", None)) if co_map else None
    d["direction"] = dir_map.get(getattr(p, "direction_id", None)) if dir_map else None
    d["is_overdue"] = _is_overdue(getattr(p, "due_date", None), getattr(p, "status", None))
    d["is_carried_over"] = _is_carried_over(p)
    return d


# ─────────────────── Tool definitions ───────────────────

TOOLS: list[dict] = [
    {
        "name": "get_company_full",
        "description": (
            "Полная информация о компании: все поля (sector, code, ИНН, legal_form, "
            "names на 3 языках), статистика проектов и задач (по 2025 и 2026), "
            "просрочки, перенесённые задачи, последние рейтинги, ESG-метрики, "
            "консультанты компании. Имя на любом языке, частично."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Название (полное или частичное)"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_overdue_tasks",
        "description": (
            "Просроченные задачи (дедлайн прошёл, статус не 'выполнено'). "
            "Возвращает все поля задач: статус, приоритет, исполнителя, теги (бейджи), "
            "консультантов, признак переноса. Можно фильтровать по году/компании."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "company_name": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "compare_companies",
        "description": "Сравнить компании по метрике.",
        "input_schema": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"}},
                "metric": {
                    "type": "string",
                    "enum": [
                        "task_completion_2026", "task_completion_2025",
                        "overdue_count_2026", "overdue_count_2025",
                        "carried_over_count_2026", "carried_over_count_2025",
                        "project_count", "credit_rating_count", "esg_metric_count",
                        "total_debt_usd",
                    ],
                },
            },
            "required": ["names", "metric"],
        },
    },
    {
        "name": "search_tasks",
        "description": (
            "Поиск задач по тексту в названии. Возвращает полные данные: все поля, "
            "теги, консультанты, исполнитель, признак просрочки и переноса."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "year": {"type": "integer"},
                "status": {"type": "string"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": ["query"],
        },
    },
    # Pack 7.6
    {
        "name": "get_financials",
        "description": "Финансовая отчётность: P&L, EBITDA, чистая прибыль, IFRS/NSBU.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "year": {"type": "integer"},
                "standard": {"type": "string"},
            },
            "required": ["company_name", "year"],
        },
    },
    {
        "name": "get_governance",
        "description": "Корп. управление: совет, независимые, женщины, комитеты.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "year": {"type": "integer"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "get_credit_portfolio",
        "description": "Кредитный портфель: займы по компании, банк, ставка, debt USD.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "currency": {"type": "string"},
                "limit": {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "get_kpi_summary",
        "description": (
            "Сводная статистика по портфелю UzAssets за год: компании/проекты/задачи, "
            "% выполнения, просрочки, ПЕРЕНЕСЁННЫЕ из прошлого года, ESG-метрики, "
            "топ-5 отстающих."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"year": {"type": "integer"}},
            "required": ["year"],
        },
    },
    {
        "name": "search_audit_log",
        "description": "Журнал действий платформы.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "entity_type": {"type": "string"},
                "days_back": {"type": "integer", "default": 7},
                "actor_email": {"type": "string"},
                "limit": {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "get_ratings_history",
        "description": "История рейтингов компании от агентств.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "agency": {"type": "string"},
                "is_esg": {"type": "boolean"},
            },
            "required": ["company_name"],
        },
    },

    # ─────────────── Pack 7.7 new tools ───────────────

    {
        "name": "get_task_details",
        "description": (
            "Полная карточка задачи: все поля, описание, история изменений, "
            "комментарии, файлы, консультанты, исполнитель. Используй когда "
            "пользователь спросил про конкретную задачу по номеру или ключевому "
            "слову. Возвращает максимум деталей."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "num": {
                    "type": "string",
                    "description": "Номер задачи (например 'T-2026-001') ИЛИ часть названия",
                },
                "include_history": {"type": "boolean", "default": True},
            },
            "required": ["num"],
        },
    },
    {
        "name": "get_project_details",
        "description": (
            "Полная карточка проекта: все поля, описание, project_type, ground_type, "
            "теги, признак переноса, список задач проекта (с их статусами). "
            "Используй для запросов про конкретный проект."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "num": {"type": "string", "description": "Номер или часть названия"},
                "include_tasks": {"type": "boolean", "default": True},
            },
            "required": ["num"],
        },
    },
    {
        "name": "search_comments",
        "description": (
            "Поиск по комментариям к задачам и проектам по подстроке. "
            "Используй когда нужно найти обсуждение конкретной темы — 'что обсуждали "
            "по тарифам', 'комментарии про IPO'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "days_back": {"type": "integer", "default": 90,
                               "description": "За сколько дней искать (по умолчанию 90)"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_consultants",
        "description": (
            "Список консультантов системы: name_ru, name_en, abbr, флаг Big4, "
            "цвет, количество назначенных задач. Используй для 'кто из консультантов "
            "работает', 'какие Big4 в проектах', 'консультанты компании X'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "big4_only": {"type": "boolean", "description": "Только Big4 (KPMG/E&Y/PwC/Deloitte)"},
                "active_only": {"type": "boolean", "default": True},
                "company_name": {
                    "type": "string",
                    "description": "Фильтр: консультанты работающие на компании",
                },
            },
        },
    },
    {
        "name": "list_carried_over",
        "description": (
            "Перенесённые задачи и проекты: те, у которых linked_year отличается "
            "от portfolio_year (т.е. они изначально были в другом году портфеля). "
            "Используй для 'какие задачи перенесли с 2025 на 2026', "
            "'сколько хвостов с прошлого года'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "Текущий год портфеля"},
                "company_name": {"type": "string"},
                "kind": {"type": "string", "enum": ["tasks", "projects", "both"], "default": "both"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["year"],
        },
    },

    # ─────────────── Pack 7.8 verification tools ───────────────

    {
        "name": "verify_count",
        "description": (
            "ПРОВЕРОЧНЫЙ tool: получить точное количество строк по таблице с фильтрами. "
            "Используй когда сомневаешься в цифре или нужна верификация. "
            "Возвращает COUNT + явный SQL который выполнен. "
            "Если в одном из других tools цифра кажется странной — "
            "вызови verify_count чтобы перепроверить."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "enum": ["tasks", "projects", "companies", "consultant_assignments",
                             "agency_ratings", "esg_metrics", "cp_loans",
                             "financial_reports", "audit_log"],
                    "description": "Таблица для подсчёта"
                },
                "portfolio_year": {"type": "integer", "description": "Фильтр по году портфеля (только tasks/projects)"},
                "linked_year": {"type": "integer", "description": "Фильтр по исходному году (только tasks/projects)"},
                "company_name": {"type": "string", "description": "Фильтр по компании"},
                "status": {"type": "string", "description": "Фильтр по статусу"},
                "is_carried_over": {
                    "type": "boolean",
                    "description": "Только перенесённые (linked_year != portfolio_year AND linked_year IS NOT NULL)"
                },
                "is_overdue": {"type": "boolean", "description": "Только просроченные"},
                "currency": {"type": "string", "description": "Для cp_loans: USD/UZS/EUR/CNY"},
            },
            "required": ["table"],
        },
    },
    {
        "name": "compare_years",
        "description": (
            "Сравнить ОДНУ метрику по нескольким годам в ОДНОМ вызове. "
            "Используй для запросов 'сравни 2025 vs 2026'. "
            "Один вызов вместо нескольких — гарантирует одинаковую методологию подсчёта."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "years": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Список лет: [2025, 2026]"
                },
                "metric": {
                    "type": "string",
                    "enum": [
                        "tasks_in_year",
                        "tasks_done_in_year",
                        "tasks_overdue_in_year",
                        "tasks_carried_over_into_year",
                        "completion_pct",
                        "projects_in_year",
                    ],
                },
                "company_name": {"type": "string", "description": "Опц. фильтр по компании"},
            },
            "required": ["years", "metric"],
        },
    },
]


# ─────────────────── Handlers (Pack 7.5/7.6 now schema-aware) ───────────────────

async def _tool_get_company_full(args: dict, db: AsyncSession) -> dict:
    name = args.get("name", "")
    co = await _find_company_by_name(db, name)
    if not co:
        return {"error": f"Компания '{name}' не найдена"}
    co_id = co.id

    co_dict = _model_to_dict(co, include_heavy=False)

    # Sector name resolved
    try:
        from app.models.company import Sector  # type: ignore[import]
        if getattr(co, "sector_id", None):
            sr = await db.execute(select(Sector).where(Sector.id == co.sector_id))
            sec = sr.scalar_one_or_none()
            if sec:
                co_dict["sector_name"] = getattr(sec, "name_ru", None) or getattr(sec, "code", None)
    except ImportError:
        pass

    # Projects + tasks
    from app.models.project import Project  # type: ignore[import]
    from app.models.task import Task  # type: ignore[import]
    proj_res = await db.execute(select(Project).where(Project.company_id == co_id))
    projects = list(proj_res.scalars().all())
    task_res = await db.execute(select(Task).where(Task.company_id == co_id))
    tasks = list(task_res.scalars().all())

    def _stats(items: list, year: Optional[int] = None) -> dict:
        out = {"total": 0, "done": 0, "active": 0, "overdue": 0, "carried_over": 0}
        for it in items:
            if year is not None and getattr(it, "portfolio_year", None) != year:
                continue
            out["total"] += 1
            st = (getattr(it, "status", "") or "").lower()
            if st in _DONE_STATUSES: out["done"] += 1
            elif st in _ACTIVE_STATUSES: out["active"] += 1
            if _is_overdue(getattr(it, "due_date", None), st): out["overdue"] += 1
            if _is_carried_over(it): out["carried_over"] += 1
        return out

    # Ratings
    ratings_data = []
    try:
        from app.models.agency_rating import AgencyRating  # type: ignore[import]
        r_res = await db.execute(
            select(AgencyRating).where(AgencyRating.company_id == co_id)
            .order_by(AgencyRating.rating_date.desc().nullslast()).limit(20)
        )
        for r in r_res.scalars().all():
            ratings_data.append(_model_to_dict(r))
    except ImportError:
        pass

    # ESG
    esg_data = []
    try:
        from app.models.esg import EsgMetric  # type: ignore[import]
        e_res = await db.execute(
            select(EsgMetric).where(EsgMetric.company_id == co_id)
            .order_by(EsgMetric.year.desc()).limit(50)
        )
        for m in e_res.scalars().all():
            esg_data.append(_model_to_dict(m))
    except ImportError:
        pass

    # Consultants working on this company (via task assignments)
    consultants_data: list[dict] = []
    try:
        from app.models.consultant import Consultant, ConsultantAssignment  # type: ignore[import]
        task_ids = [t.id for t in tasks]
        if task_ids:
            ca_res = await db.execute(
                select(ConsultantAssignment.consultant_id, func.count(ConsultantAssignment.id).label("cnt"))
                .where(ConsultantAssignment.task_id.in_(task_ids))
                .group_by(ConsultantAssignment.consultant_id)
            )
            counts = {row.consultant_id: row.cnt for row in ca_res}
            if counts:
                c_res = await db.execute(select(Consultant).where(Consultant.id.in_(list(counts.keys()))))
                for c in c_res.scalars().all():
                    consultants_data.append({
                        "name": c.name_ru,
                        "abbr": getattr(c, "abbr", None),
                        "is_big4": bool(getattr(c, "is_big4", False)),
                        "task_count": int(counts.get(c.id, 0)),
                    })
                consultants_data.sort(key=lambda x: -x["task_count"])
    except ImportError:
        pass

    return {
        "company": co_dict,
        "projects_stats": _stats(projects),
        "projects_2025_stats": _stats(projects, 2025),
        "projects_2026_stats": _stats(projects, 2026),
        "tasks_2025_stats": _stats(tasks, 2025),
        "tasks_2026_stats": _stats(tasks, 2026),
        "ratings": ratings_data[:15],
        "esg_metrics": esg_data[:30],
        "esg_metrics_count": len(esg_data),
        "consultants": consultants_data[:15],
    }


async def _tool_list_overdue_tasks(args: dict, db: AsyncSession) -> dict:
    year = args.get("year")
    company_name = args.get("company_name")
    limit = min(int(args.get("limit", 50)), 200)

    company_id = None
    if company_name:
        co = await _find_company_by_name(db, company_name)
        if not co:
            return {"error": f"Компания '{company_name}' не найдена", "tasks": []}
        company_id = co.id

    from app.models.task import Task  # type: ignore[import]

    stmt = select(Task)
    if year: stmt = stmt.where(Task.portfolio_year == year)
    if company_id: stmt = stmt.where(Task.company_id == company_id)
    stmt = stmt.order_by(Task.due_date.asc().nullslast()).limit(500)

    res = await db.execute(stmt)
    all_tasks = list(res.scalars().all())
    overdue = [t for t in all_tasks
               if _is_overdue(getattr(t, "due_date", None), getattr(t, "status", None))][:limit]

    maps = await _build_lookup_maps(db, need_companies=True, need_directions=True)
    co_map = maps.get("companies", {})
    dir_map = maps.get("directions", {})

    cons_for = await _consultants_for_tasks(db, [t.id for t in overdue])

    return {
        "filter": {"year": year, "company_name": company_name, "limit": limit},
        "total_overdue": len(overdue),
        "tasks": [_enrich_task(t, co_map=co_map, dir_map=dir_map, consultants_for=cons_for)
                  for t in overdue],
    }


async def _tool_compare_companies(args: dict, db: AsyncSession) -> dict:
    names = args.get("names", []) or []
    metric = args.get("metric", "")
    if not names or not metric:
        return {"error": "Параметры 'names' и 'metric' обязательны"}

    from app.models.task import Task  # type: ignore[import]
    from app.models.project import Project  # type: ignore[import]

    results = []
    for nm in names:
        co = await _find_company_by_name(db, nm)
        if not co:
            results.append({"name_query": nm, "found": False, "value": None})
            continue
        val: Any = None

        if metric in ("task_completion_2025", "task_completion_2026"):
            yr = 2025 if "2025" in metric else 2026
            t_res = await db.execute(select(Task).where(Task.company_id == co.id, Task.portfolio_year == yr))
            ts = list(t_res.scalars().all())
            done = sum(1 for t in ts if (getattr(t, "status", "") or "").lower() in _DONE_STATUSES)
            val = {"total": len(ts), "done": done, "pct": round(done/len(ts)*100) if ts else 0}
        elif metric in ("overdue_count_2025", "overdue_count_2026"):
            yr = 2025 if "2025" in metric else 2026
            t_res = await db.execute(select(Task).where(Task.company_id == co.id, Task.portfolio_year == yr))
            ts = list(t_res.scalars().all())
            val = sum(1 for t in ts if _is_overdue(getattr(t, "due_date", None), getattr(t, "status", None)))
        elif metric in ("carried_over_count_2025", "carried_over_count_2026"):
            yr = 2025 if "2025" in metric else 2026
            t_res = await db.execute(select(Task).where(Task.company_id == co.id, Task.portfolio_year == yr))
            ts = list(t_res.scalars().all())
            val = sum(1 for t in ts if _is_carried_over(t))
        elif metric == "project_count":
            r = await db.execute(select(func.count()).select_from(Project).where(Project.company_id == co.id))
            val = int(r.scalar_one() or 0)
        elif metric == "credit_rating_count":
            try:
                from app.models.agency_rating import AgencyRating  # type: ignore[import]
                r = await db.execute(
                    select(func.count()).select_from(AgencyRating)
                    .where(AgencyRating.company_id == co.id, AgencyRating.is_esg == False)  # noqa: E712
                )
                val = int(r.scalar_one() or 0)
            except ImportError: val = 0
        elif metric == "esg_metric_count":
            try:
                from app.models.esg import EsgMetric  # type: ignore[import]
                r = await db.execute(select(func.count()).select_from(EsgMetric).where(EsgMetric.company_id == co.id))
                val = int(r.scalar_one() or 0)
            except ImportError: val = 0
        elif metric == "total_debt_usd":
            try:
                from app.models.credit import CpLoan  # type: ignore[import]
                r = await db.execute(select(func.sum(CpLoan.debt_usd)).where(CpLoan.company_id == co.id))
                val = _to_float(r.scalar_one_or_none()) or 0
            except ImportError: val = 0

        results.append({
            "name_query": nm,
            "name_resolved": _company_name(co),
            "found": True,
            "value": val,
        })

    return {"metric": metric, "results": results}


async def _tool_search_tasks(args: dict, db: AsyncSession) -> dict:
    query = (args.get("query") or "").strip()
    year = args.get("year")
    status = args.get("status")
    limit = min(int(args.get("limit", 30)), 100)
    if not query:
        return {"error": "Параметр 'query' обязателен"}

    from app.models.task import Task  # type: ignore[import]

    stmt = select(Task).where(func.lower(Task.title).like(f"%{query.lower()}%"))
    if year: stmt = stmt.where(Task.portfolio_year == year)
    if status: stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(Task.due_date.asc().nullslast()).limit(limit)

    res = await db.execute(stmt)
    tasks = list(res.scalars().all())

    maps = await _build_lookup_maps(db, need_companies=True, need_directions=True)
    cons_for = await _consultants_for_tasks(db, [t.id for t in tasks])

    return {
        "query": query,
        "filter": {"year": year, "status": status, "limit": limit},
        "matches": len(tasks),
        "tasks": [_enrich_task(t, co_map=maps["companies"], dir_map=maps["directions"],
                                consultants_for=cons_for)
                  for t in tasks],
    }


# ─────────────────── Pack 7.6 handlers (unchanged from 7.6) ───────────────────

async def _tool_get_financials(args: dict, db: AsyncSession) -> dict:
    name = args.get("company_name", "")
    year = args.get("year")
    standard = args.get("standard")
    if not year:
        return {"error": "Параметр 'year' обязателен"}
    co = await _find_company_by_name(db, name)
    if not co:
        return {"error": f"Компания '{name}' не найдена"}

    try:
        from app.models.financial import FinancialReport, FinancialLine  # type: ignore[import]
    except ImportError:
        return {"error": "Модель FinancialReport не доступна"}

    stmt = select(FinancialReport).where(
        FinancialReport.company_id == co.id, FinancialReport.year == year
    )
    if standard: stmt = stmt.where(FinancialReport.standard == standard)
    res = await db.execute(stmt.order_by(FinancialReport.created_at.desc()).limit(5))
    reports = list(res.scalars().all())
    if not reports:
        return {"company": _company_name(co), "year": year, "found": False,
                "message": f"Нет финансовой отчётности за {year} год"}

    out_reports = []
    for r in reports:
        line_res = await db.execute(
            select(FinancialLine).where(FinancialLine.report_id == r.id)
            .order_by(FinancialLine.line_code.asc()).limit(200)
        )
        lines = list(line_res.scalars().all())
        line_data = [{
            "code": l.line_code, "name": l.line_name,
            "value": _to_float(getattr(l, "value", None)),
            "section": getattr(l, "section_label", None),
        } for l in lines if _to_float(getattr(l, "value", None)) is not None][:50]

        out_reports.append({
            "id": str(r.id), "year": r.year, "quarter": r.quarter,
            "standard": r.standard, "report_type": r.report_type,
            "currency": r.currency, "unit_scale": r.unit_scale,
            "is_audited": r.is_audited,
            "lines_count": len(lines), "lines": line_data,
        })

    return {"company": _company_name(co), "year": year, "found": True,
            "reports_count": len(reports), "reports": out_reports}


async def _tool_get_governance(args: dict, db: AsyncSession) -> dict:
    name = args.get("company_name", "")
    year = args.get("year")
    co = await _find_company_by_name(db, name)
    if not co:
        return {"error": f"Компания '{name}' не найдена"}

    try:
        from app.models.governance import GovernanceData  # type: ignore[import]
    except ImportError:
        return {"error": "Модель GovernanceData не доступна"}

    stmt = select(GovernanceData).where(GovernanceData.company_id == co.id)
    if year: stmt = stmt.where(GovernanceData.year == year)
    stmt = stmt.order_by(GovernanceData.year.desc()).limit(5)

    res = await db.execute(stmt)
    items = list(res.scalars().all())
    if not items:
        return {"company": _company_name(co), "found": False,
                "message": "Данных по корпоративному управлению нет"}

    return {
        "company": _company_name(co), "found": True,
        "years_count": len(items),
        "years": [_model_to_dict(g) for g in items],
    }


async def _tool_get_credit_portfolio(args: dict, db: AsyncSession) -> dict:
    company_name = args.get("company_name")
    currency = args.get("currency")
    limit = min(int(args.get("limit", 30)), 100)

    try:
        from app.models.credit import CpLoan  # type: ignore[import]
    except ImportError:
        return {"error": "Модель CpLoan не доступна"}

    company_id = None
    if company_name:
        co = await _find_company_by_name(db, company_name)
        if not co:
            return {"error": f"Компания '{company_name}' не найдена", "loans": []}
        company_id = co.id

    stmt = select(CpLoan)
    if company_id: stmt = stmt.where(CpLoan.company_id == company_id)
    if currency: stmt = stmt.where(CpLoan.currency == currency.upper())
    stmt = stmt.order_by(CpLoan.debt_usd.desc().nullslast()).limit(limit)

    res = await db.execute(stmt)
    loans = list(res.scalars().all())
    maps = await _build_lookup_maps(db, need_companies=True)
    co_map = maps.get("companies", {})

    total_usd = sum(_to_float(getattr(l, "debt_usd", 0)) or 0 for l in loans)

    out_loans = []
    for l in loans:
        ld = _model_to_dict(l)
        ld["company"] = co_map.get(getattr(l, "company_id", None), "?")
        out_loans.append(ld)

    return {
        "filter": {"company_name": company_name, "currency": currency, "limit": limit},
        "loans_count": len(loans),
        "total_debt_usd": round(total_usd, 2),
        "loans": out_loans,
    }


async def _tool_get_kpi_summary(args: dict, db: AsyncSession) -> dict:
    year = args.get("year")
    if not year:
        return {"error": "Параметр 'year' обязателен"}

    from app.models.company import Company  # type: ignore[import]
    from app.models.project import Project  # type: ignore[import]
    from app.models.task import Task  # type: ignore[import]

    # Companies: total in DB (no year filter — companies aren't year-scoped)
    co_count = (await db.execute(select(func.count()).select_from(Company))).scalar_one() or 0

    # Projects: split into 3 groups for honest reporting
    proj_total = (await db.execute(select(func.count()).select_from(Project))).scalar_one() or 0
    proj_in_year = (await db.execute(
        select(func.count()).select_from(Project).where(Project.portfolio_year == year)
    )).scalar_one() or 0
    proj_no_year = (await db.execute(
        select(func.count()).select_from(Project).where(Project.portfolio_year.is_(None))
    )).scalar_one() or 0

    # Tasks: filtered by portfolio_year
    task_res = await db.execute(select(Task).where(Task.portfolio_year == year))
    tasks = list(task_res.scalars().all())

    done = sum(1 for t in tasks if (getattr(t, "status", "") or "").lower() in _DONE_STATUSES)
    active = sum(1 for t in tasks if (getattr(t, "status", "") or "").lower() in _ACTIVE_STATUSES)
    overdue = sum(1 for t in tasks if _is_overdue(getattr(t, "due_date", None), getattr(t, "status", None)))
    carried = sum(1 for t in tasks if _is_carried_over(t))

    by_co: dict[Any, dict] = {}
    co_res = await db.execute(select(Company))
    cos = list(co_res.scalars().all())
    co_map = {co.id: _company_name(co) for co in cos}

    for t in tasks:
        cid = getattr(t, "company_id", None)
        if not cid: continue
        b = by_co.setdefault(cid, {"total": 0, "done": 0, "overdue": 0, "carried": 0})
        b["total"] += 1
        if (getattr(t, "status", "") or "").lower() in _DONE_STATUSES: b["done"] += 1
        if _is_overdue(getattr(t, "due_date", None), getattr(t, "status", None)): b["overdue"] += 1
        if _is_carried_over(t): b["carried"] += 1

    top_overdue = sorted(by_co.items(), key=lambda x: -x[1]["overdue"])[:5]
    top_overdue_data = [{
        "company": co_map.get(cid, "?"), "overdue": b["overdue"], "total": b["total"],
        "carried_over": b["carried"],
        "done_pct": round(b["done"]/b["total"]*100) if b["total"] else 0,
    } for cid, b in top_overdue if b["overdue"] > 0]

    ratings_count = 0
    esg_count = 0
    try:
        from app.models.agency_rating import AgencyRating  # type: ignore[import]
        ratings_count = (await db.execute(select(func.count()).select_from(AgencyRating))).scalar_one() or 0
    except ImportError: pass
    try:
        from app.models.esg import EsgMetric  # type: ignore[import]
        esg_count = (await db.execute(
            select(func.count()).select_from(EsgMetric).where(EsgMetric.year == year)
        )).scalar_one() or 0
    except ImportError: pass

    return {
        "_meta": {
            "tool": "get_kpi_summary",
            "scope_year": year,
            "note": (
                "projects.in_year = projects WHERE portfolio_year=YEAR. "
                "projects.total_db = ALL projects in DB (any year). "
                "projects.no_year = projects WHERE portfolio_year IS NULL. "
                "All task counts are scoped to portfolio_year=YEAR. "
                "tasks_carried_over = tasks WHERE linked_year IS NOT NULL AND linked_year != portfolio_year (i.e. moved INTO this year from another year). "
                "completion_pct = tasks_done / tasks * 100 (only tasks with portfolio_year=YEAR)."
            ),
        },
        "year": year,
        "totals": {
            "companies_total_db": int(co_count),
            "projects_in_year": int(proj_in_year),
            "projects_total_db": int(proj_total),
            "projects_no_year": int(proj_no_year),
            "tasks_in_year": len(tasks),
            "tasks_done_in_year": done,
            "tasks_active_in_year": active,
            "tasks_overdue_in_year": overdue,
            "tasks_carried_over_into_year": carried,
            "completion_pct": round(done/len(tasks)*100) if tasks else 0,
            "ratings_total_db": int(ratings_count),
            "esg_metrics_in_year": int(esg_count),
        },
        "top_overdue_companies": top_overdue_data,
    }


async def _tool_search_audit_log(args: dict, db: AsyncSession) -> dict:
    action = args.get("action")
    entity_type = args.get("entity_type")
    actor_email = args.get("actor_email")
    days_back = int(args.get("days_back", 7))
    limit = min(int(args.get("limit", 30)), 100)

    try:
        from app.models.audit import AuditLog  # type: ignore[import]
    except ImportError:
        try:
            from app.models.audit_log import AuditLog  # type: ignore
        except ImportError:
            return {"error": "Модель AuditLog не доступна"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    stmt = select(AuditLog).where(AuditLog.created_at >= cutoff)
    if action: stmt = stmt.where(AuditLog.action == action)
    if entity_type: stmt = stmt.where(AuditLog.entity_type == entity_type)
    if actor_email: stmt = stmt.where(AuditLog.actor_email == actor_email)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)

    res = await db.execute(stmt)
    items = list(res.scalars().all())

    return {
        "filter": {"action": action, "entity_type": entity_type, "actor_email": actor_email,
                   "days_back": days_back, "limit": limit},
        "matches": len(items),
        "events": [_model_to_dict(e) for e in items],
    }


async def _tool_get_ratings_history(args: dict, db: AsyncSession) -> dict:
    name = args.get("company_name", "")
    agency = args.get("agency")
    is_esg = args.get("is_esg")
    co = await _find_company_by_name(db, name)
    if not co:
        return {"error": f"Компания '{name}' не найдена"}

    try:
        from app.models.agency_rating import AgencyRating  # type: ignore[import]
    except ImportError:
        return {"error": "Модель AgencyRating не доступна"}

    stmt = select(AgencyRating).where(AgencyRating.company_id == co.id)
    if agency: stmt = stmt.where(AgencyRating.agency.ilike(f"%{agency}%"))
    if is_esg is not None: stmt = stmt.where(AgencyRating.is_esg == bool(is_esg))
    stmt = stmt.order_by(AgencyRating.rating_date.desc().nullslast()).limit(100)

    res = await db.execute(stmt)
    items = list(res.scalars().all())

    return {
        "company": _company_name(co),
        "filter": {"agency": agency, "is_esg": is_esg},
        "ratings_count": len(items),
        "ratings": [_model_to_dict(r) for r in items],
    }


# ─────────────────── Pack 7.7 NEW handlers ───────────────────

async def _find_task_by_query(db: AsyncSession, q: str) -> Optional[Any]:
    """Find single task by num exact match, then num substring, then title substring."""
    from app.models.task import Task  # type: ignore[import]
    qs = (q or "").strip()
    if not qs:
        return None
    # exact num
    r = await db.execute(select(Task).where(Task.num == qs).limit(1))
    t = r.scalar_one_or_none()
    if t: return t
    # num substring
    r = await db.execute(select(Task).where(Task.num.ilike(f"%{qs}%")).limit(1))
    t = r.scalar_one_or_none()
    if t: return t
    # title substring (most relevant by recency)
    r = await db.execute(
        select(Task).where(func.lower(Task.title).like(f"%{qs.lower()}%"))
        .order_by(Task.created_at.desc()).limit(1)
    )
    return r.scalar_one_or_none()


async def _find_project_by_query(db: AsyncSession, q: str) -> Optional[Any]:
    from app.models.project import Project  # type: ignore[import]
    qs = (q or "").strip()
    if not qs:
        return None
    r = await db.execute(select(Project).where(Project.num == qs).limit(1))
    p = r.scalar_one_or_none()
    if p: return p
    r = await db.execute(select(Project).where(Project.num.ilike(f"%{qs}%")).limit(1))
    p = r.scalar_one_or_none()
    if p: return p
    r = await db.execute(
        select(Project).where(func.lower(Project.title).like(f"%{qs.lower()}%"))
        .order_by(Project.created_at.desc()).limit(1)
    )
    return r.scalar_one_or_none()


async def _tool_get_task_details(args: dict, db: AsyncSession) -> dict:
    num = (args.get("num") or "").strip()
    include_history = bool(args.get("include_history", True))
    if not num:
        return {"error": "Параметр 'num' обязателен"}

    t = await _find_task_by_query(db, num)
    if not t:
        return {"error": f"Задача '{num}' не найдена"}

    maps = await _build_lookup_maps(db, need_companies=True, need_directions=True)
    cons_for = await _consultants_for_tasks(db, [t.id])
    task_dict = _enrich_task(t, co_map=maps["companies"], dir_map=maps["directions"],
                              consultants_for=cons_for, include_heavy=True)

    # Comments (TaskComment)
    comments_data = []
    try:
        from app.models.task import TaskComment  # type: ignore[import]
        c_res = await db.execute(
            select(TaskComment).where(TaskComment.task_id == t.id)
            .order_by(TaskComment.created_at.desc()).limit(30)
        )
        comments_data = [_model_to_dict(c) for c in c_res.scalars().all()]
    except ImportError:
        pass

    # Attachments
    attachments_data = []
    try:
        from app.models.task import TaskAttachment  # type: ignore[import]
        a_res = await db.execute(
            select(TaskAttachment).where(TaskAttachment.task_id == t.id).limit(20)
        )
        attachments_data = [_model_to_dict(a) for a in a_res.scalars().all()]
    except ImportError:
        pass

    # History
    history_data = []
    if include_history:
        try:
            from app.models.task import TaskHistory  # type: ignore[import]
            h_res = await db.execute(
                select(TaskHistory).where(TaskHistory.task_id == t.id)
                .order_by(TaskHistory.created_at.desc()).limit(50)
            )
            history_data = [_model_to_dict(h) for h in h_res.scalars().all()]
        except ImportError:
            pass

    # Project context
    project_info = None
    if getattr(t, "project_id", None):
        try:
            from app.models.project import Project  # type: ignore[import]
            p_res = await db.execute(select(Project).where(Project.id == t.project_id))
            p = p_res.scalar_one_or_none()
            if p:
                project_info = {"id": str(p.id), "num": getattr(p, "num", None),
                                 "title": getattr(p, "title", None),
                                 "status": getattr(p, "status", None),
                                 "portfolio_year": getattr(p, "portfolio_year", None)}
        except ImportError:
            pass

    return {
        "task": task_dict,
        "project": project_info,
        "comments_count": len(comments_data),
        "comments": comments_data,
        "attachments_count": len(attachments_data),
        "attachments": attachments_data,
        "history_count": len(history_data),
        "history": history_data[:30],
    }


async def _tool_get_project_details(args: dict, db: AsyncSession) -> dict:
    num = (args.get("num") or "").strip()
    include_tasks = bool(args.get("include_tasks", True))
    if not num:
        return {"error": "Параметр 'num' обязателен"}

    p = await _find_project_by_query(db, num)
    if not p:
        return {"error": f"Проект '{num}' не найден"}

    maps = await _build_lookup_maps(db, need_companies=True, need_directions=True)
    proj_dict = _enrich_project(p, co_map=maps["companies"], dir_map=maps["directions"],
                                 include_heavy=True)

    # Project comments
    comments_data = []
    try:
        from app.models.project import ProjectComment  # type: ignore[import]
        c_res = await db.execute(
            select(ProjectComment).where(ProjectComment.project_id == p.id)
            .order_by(ProjectComment.created_at.desc()).limit(30)
        )
        comments_data = [_model_to_dict(c) for c in c_res.scalars().all()]
    except ImportError:
        pass

    # Tasks of this project
    tasks_data = []
    if include_tasks:
        from app.models.task import Task  # type: ignore[import]
        t_res = await db.execute(
            select(Task).where(Task.project_id == p.id)
            .order_by(Task.due_date.asc().nullslast()).limit(100)
        )
        tasks = list(t_res.scalars().all())
        cons_for = await _consultants_for_tasks(db, [t.id for t in tasks])
        tasks_data = [_enrich_task(t, co_map=maps["companies"], dir_map=maps["directions"],
                                     consultants_for=cons_for)
                       for t in tasks]

    return {
        "project": proj_dict,
        "comments_count": len(comments_data),
        "comments": comments_data,
        "tasks_count": len(tasks_data),
        "tasks": tasks_data,
    }


async def _tool_search_comments(args: dict, db: AsyncSession) -> dict:
    query = (args.get("query") or "").strip()
    days_back = int(args.get("days_back", 90))
    limit = min(int(args.get("limit", 30)), 100)
    if not query:
        return {"error": "Параметр 'query' обязателен"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    matches: list[dict] = []

    # Task comments
    try:
        from app.models.task import TaskComment, Task  # type: ignore[import]
        r = await db.execute(
            select(TaskComment).where(
                func.lower(TaskComment.body).like(f"%{query.lower()}%"),
                TaskComment.created_at >= cutoff,
            ).order_by(TaskComment.created_at.desc()).limit(limit)
        )
        tcs = list(r.scalars().all())
        # Resolve task titles
        task_ids = list({c.task_id for c in tcs})
        title_map: dict = {}
        if task_ids:
            tr = await db.execute(select(Task).where(Task.id.in_(task_ids)))
            for t in tr.scalars().all():
                title_map[t.id] = {"num": getattr(t, "num", None),
                                    "title": getattr(t, "title", None)}
        for c in tcs:
            d = _model_to_dict(c)
            d["entity"] = "task"
            d["task"] = title_map.get(c.task_id)
            matches.append(d)
    except ImportError:
        pass

    # Project comments
    try:
        from app.models.project import ProjectComment, Project  # type: ignore[import]
        r = await db.execute(
            select(ProjectComment).where(
                func.lower(ProjectComment.body).like(f"%{query.lower()}%"),
                ProjectComment.created_at >= cutoff,
            ).order_by(ProjectComment.created_at.desc()).limit(limit)
        )
        pcs = list(r.scalars().all())
        proj_ids = list({c.project_id for c in pcs})
        ptitle_map: dict = {}
        if proj_ids:
            pr = await db.execute(select(Project).where(Project.id.in_(proj_ids)))
            for p in pr.scalars().all():
                ptitle_map[p.id] = {"num": getattr(p, "num", None),
                                      "title": getattr(p, "title", None)}
        for c in pcs:
            d = _model_to_dict(c)
            d["entity"] = "project"
            d["project"] = ptitle_map.get(c.project_id)
            matches.append(d)
    except ImportError:
        pass

    # General entity-based comments
    try:
        from app.models.comment import Comment  # type: ignore[import]
        r = await db.execute(
            select(Comment).where(
                func.lower(Comment.body).like(f"%{query.lower()}%"),
                Comment.created_at >= cutoff,
            ).order_by(Comment.created_at.desc()).limit(limit)
        )
        for c in r.scalars().all():
            d = _model_to_dict(c)
            d["entity"] = getattr(c, "entity_type", "?")
            matches.append(d)
    except ImportError:
        pass

    matches.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    matches = matches[:limit]

    return {
        "query": query,
        "filter": {"days_back": days_back, "limit": limit},
        "matches_count": len(matches),
        "comments": matches,
    }


async def _tool_list_consultants(args: dict, db: AsyncSession) -> dict:
    big4_only = bool(args.get("big4_only", False))
    active_only = bool(args.get("active_only", True))
    company_name = args.get("company_name")

    try:
        from app.models.consultant import Consultant, ConsultantAssignment  # type: ignore[import]
    except ImportError:
        return {"error": "Модель Consultant не доступна"}

    # Get consultants
    stmt = select(Consultant)
    if big4_only: stmt = stmt.where(Consultant.is_big4 == True)  # noqa: E712
    if active_only: stmt = stmt.where(Consultant.is_active == True)  # noqa: E712
    stmt = stmt.order_by(Consultant.sort_order.asc())
    res = await db.execute(stmt)
    consultants = list(res.scalars().all())

    # Filter by company_name (consultants who have assignments on this company's tasks)
    company_filter_ids: Optional[set] = None
    if company_name:
        co = await _find_company_by_name(db, company_name)
        if not co:
            return {"error": f"Компания '{company_name}' не найдена"}
        from app.models.task import Task  # type: ignore[import]
        t_res = await db.execute(select(Task.id).where(Task.company_id == co.id))
        co_task_ids = [row[0] for row in t_res.all()]
        if co_task_ids:
            ca_res = await db.execute(
                select(ConsultantAssignment.consultant_id).where(
                    ConsultantAssignment.task_id.in_(co_task_ids)
                ).distinct()
            )
            company_filter_ids = {row[0] for row in ca_res.all()}
        else:
            company_filter_ids = set()

    # Count assignments per consultant
    cons_ids = [c.id for c in consultants]
    counts: dict = {}
    if cons_ids:
        cnt_res = await db.execute(
            select(ConsultantAssignment.consultant_id, func.count(ConsultantAssignment.id))
            .where(ConsultantAssignment.consultant_id.in_(cons_ids))
            .group_by(ConsultantAssignment.consultant_id)
        )
        counts = {row[0]: row[1] for row in cnt_res.all()}

    out = []
    for c in consultants:
        if company_filter_ids is not None and c.id not in company_filter_ids:
            continue
        d = _model_to_dict(c)
        d["assignment_count"] = int(counts.get(c.id, 0))
        out.append(d)
    out.sort(key=lambda x: -x.get("assignment_count", 0))

    return {
        "filter": {"big4_only": big4_only, "active_only": active_only,
                    "company_name": company_name},
        "consultants_count": len(out),
        "consultants": out,
    }


async def _tool_list_carried_over(args: dict, db: AsyncSession) -> dict:
    year = args.get("year")
    company_name = args.get("company_name")
    kind = args.get("kind", "both")
    limit = min(int(args.get("limit", 50)), 200)
    if not year:
        return {"error": "Параметр 'year' обязателен"}

    company_id = None
    if company_name:
        co = await _find_company_by_name(db, company_name)
        if not co:
            return {"error": f"Компания '{company_name}' не найдена"}
        company_id = co.id

    maps = await _build_lookup_maps(db, need_companies=True, need_directions=True)
    co_map = maps["companies"]
    dir_map = maps["directions"]

    out: dict = {"year": year, "filter": {"company_name": company_name, "kind": kind}}

    if kind in ("tasks", "both"):
        from app.models.task import Task  # type: ignore[import]
        t_stmt = select(Task).where(
            Task.portfolio_year == year,
            Task.linked_year.isnot(None),
            Task.linked_year != year,
        )
        if company_id: t_stmt = t_stmt.where(Task.company_id == company_id)
        t_stmt = t_stmt.order_by(Task.due_date.asc().nullslast()).limit(limit)
        t_res = await db.execute(t_stmt)
        tasks = list(t_res.scalars().all())
        cons_for = await _consultants_for_tasks(db, [t.id for t in tasks])
        out["tasks_count"] = len(tasks)
        out["tasks"] = [_enrich_task(t, co_map=co_map, dir_map=dir_map, consultants_for=cons_for)
                        for t in tasks]

    if kind in ("projects", "both"):
        from app.models.project import Project  # type: ignore[import]
        p_stmt = select(Project).where(
            Project.portfolio_year == year,
            Project.linked_year.isnot(None),
            Project.linked_year != year,
        )
        if company_id: p_stmt = p_stmt.where(Project.company_id == company_id)
        p_stmt = p_stmt.order_by(Project.due_date.asc().nullslast()).limit(limit)
        p_res = await db.execute(p_stmt)
        projects = list(p_res.scalars().all())
        out["projects_count"] = len(projects)
        out["projects"] = [_enrich_project(p, co_map=co_map, dir_map=dir_map)
                           for p in projects]

    return out




# ─────────────────── Pack 7.8 verification handlers ───────────────────

async def _tool_verify_count(args: dict, db: AsyncSession) -> dict:
    """Whitelisted COUNT queries with explicit SQL trace for verification."""
    table = args.get("table", "")
    portfolio_year = args.get("portfolio_year")
    linked_year = args.get("linked_year")
    company_name = args.get("company_name")
    status = args.get("status")
    is_carried_over = args.get("is_carried_over")
    is_overdue_flag = args.get("is_overdue")
    currency = args.get("currency")

    company_id = None
    if company_name:
        co = await _find_company_by_name(db, company_name)
        if not co:
            return {"error": f"Компания '{company_name}' не найдена"}
        company_id = co.id

    sql_parts = [f"SELECT COUNT(*) FROM {table}"]
    where_parts: list[str] = []

    if table == "tasks":
        from app.models.task import Task  # type: ignore[import]
        stmt = select(func.count()).select_from(Task)
        if portfolio_year is not None:
            stmt = stmt.where(Task.portfolio_year == portfolio_year)
            where_parts.append(f"portfolio_year = {portfolio_year}")
        if linked_year is not None:
            stmt = stmt.where(Task.linked_year == linked_year)
            where_parts.append(f"linked_year = {linked_year}")
        if company_id:
            stmt = stmt.where(Task.company_id == company_id)
            where_parts.append(f"company_id = '{company_id}'")
        if status:
            stmt = stmt.where(Task.status == status)
            where_parts.append(f"status = '{status}'")
        if is_carried_over is True:
            stmt = stmt.where(Task.linked_year.isnot(None), Task.linked_year != Task.portfolio_year)
            where_parts.append("linked_year IS NOT NULL AND linked_year != portfolio_year")
        elif is_carried_over is False:
            stmt = stmt.where(or_(Task.linked_year.is_(None), Task.linked_year == Task.portfolio_year))
            where_parts.append("(linked_year IS NULL OR linked_year = portfolio_year)")
        # is_overdue requires post-query filter (depends on date), so we count via fetch
        if is_overdue_flag is True:
            t_res = await db.execute(select(Task).where(*[]))  # fallback path
            # Better: re-build query with filters then filter in Python
            qq = select(Task)
            if portfolio_year is not None: qq = qq.where(Task.portfolio_year == portfolio_year)
            if linked_year is not None: qq = qq.where(Task.linked_year == linked_year)
            if company_id: qq = qq.where(Task.company_id == company_id)
            if status: qq = qq.where(Task.status == status)
            if is_carried_over is True:
                qq = qq.where(Task.linked_year.isnot(None), Task.linked_year != Task.portfolio_year)
            r = await db.execute(qq)
            ts = list(r.scalars().all())
            count = sum(1 for t in ts if _is_overdue(getattr(t, "due_date", None), getattr(t, "status", None)))
            where_parts.append("is_overdue = true (due_date < today AND status NOT IN done)")
            return {
                "_meta": {"tool": "verify_count", "method": "Python post-filter for is_overdue"},
                "table": table, "count": count,
                "filters_applied": where_parts,
                "sql_approx": "SELECT * FROM tasks WHERE " + " AND ".join(where_parts) if where_parts else "SELECT * FROM tasks",
            }
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    elif table == "projects":
        from app.models.project import Project  # type: ignore[import]
        stmt = select(func.count()).select_from(Project)
        if portfolio_year is not None:
            stmt = stmt.where(Project.portfolio_year == portfolio_year)
            where_parts.append(f"portfolio_year = {portfolio_year}")
        if linked_year is not None:
            stmt = stmt.where(Project.linked_year == linked_year)
            where_parts.append(f"linked_year = {linked_year}")
        if company_id:
            stmt = stmt.where(Project.company_id == company_id)
            where_parts.append(f"company_id = '{company_id}'")
        if status:
            stmt = stmt.where(Project.status == status)
            where_parts.append(f"status = '{status}'")
        if is_carried_over is True:
            stmt = stmt.where(Project.linked_year.isnot(None), Project.linked_year != Project.portfolio_year)
            where_parts.append("linked_year IS NOT NULL AND linked_year != portfolio_year")
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    elif table == "companies":
        from app.models.company import Company  # type: ignore[import]
        stmt = select(func.count()).select_from(Company)
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    elif table == "consultant_assignments":
        try:
            from app.models.consultant import ConsultantAssignment  # type: ignore[import]
        except ImportError:
            return {"error": "Модель ConsultantAssignment не доступна"}
        stmt = select(func.count()).select_from(ConsultantAssignment)
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    elif table == "agency_ratings":
        try:
            from app.models.agency_rating import AgencyRating  # type: ignore[import]
        except ImportError:
            return {"error": "Модель AgencyRating не доступна"}
        stmt = select(func.count()).select_from(AgencyRating)
        if company_id:
            stmt = stmt.where(AgencyRating.company_id == company_id)
            where_parts.append(f"company_id = '{company_id}'")
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    elif table == "esg_metrics":
        try:
            from app.models.esg import EsgMetric  # type: ignore[import]
        except ImportError:
            return {"error": "Модель EsgMetric не доступна"}
        stmt = select(func.count()).select_from(EsgMetric)
        if company_id:
            stmt = stmt.where(EsgMetric.company_id == company_id)
            where_parts.append(f"company_id = '{company_id}'")
        if portfolio_year is not None:
            stmt = stmt.where(EsgMetric.year == portfolio_year)
            where_parts.append(f"year = {portfolio_year}")
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    elif table == "cp_loans":
        try:
            from app.models.credit import CpLoan  # type: ignore[import]
        except ImportError:
            return {"error": "Модель CpLoan не доступна"}
        stmt = select(func.count()).select_from(CpLoan)
        if company_id:
            stmt = stmt.where(CpLoan.company_id == company_id)
            where_parts.append(f"company_id = '{company_id}'")
        if currency:
            stmt = stmt.where(CpLoan.currency == currency.upper())
            where_parts.append(f"currency = '{currency.upper()}'")
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    elif table == "financial_reports":
        try:
            from app.models.financial import FinancialReport  # type: ignore[import]
        except ImportError:
            return {"error": "Модель FinancialReport не доступна"}
        stmt = select(func.count()).select_from(FinancialReport)
        if company_id:
            stmt = stmt.where(FinancialReport.company_id == company_id)
            where_parts.append(f"company_id = '{company_id}'")
        if portfolio_year is not None:
            stmt = stmt.where(FinancialReport.year == portfolio_year)
            where_parts.append(f"year = {portfolio_year}")
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    elif table == "audit_log":
        try:
            from app.models.audit import AuditLog  # type: ignore[import]
        except ImportError:
            return {"error": "Модель AuditLog не доступна"}
        stmt = select(func.count()).select_from(AuditLog)
        r = await db.execute(stmt)
        count = int(r.scalar_one() or 0)

    else:
        return {"error": f"Таблица '{table}' не разрешена для verify_count"}

    sql = f"SELECT COUNT(*) FROM {table}"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    return {
        "_meta": {
            "tool": "verify_count",
            "method": "Direct COUNT(*) on whitelisted table",
            "note": "Эта цифра — РЕАЛЬНЫЙ COUNT из БД. Используй её как источник истины.",
        },
        "table": table,
        "count": count,
        "filters_applied": where_parts,
        "sql_used": sql,
    }


async def _tool_compare_years(args: dict, db: AsyncSession) -> dict:
    """Compare a single metric across multiple years in one call."""
    years = args.get("years", []) or []
    metric = args.get("metric", "")
    company_name = args.get("company_name")
    if not years or not metric:
        return {"error": "Параметры 'years' и 'metric' обязательны"}

    company_id = None
    if company_name:
        co = await _find_company_by_name(db, company_name)
        if not co:
            return {"error": f"Компания '{company_name}' не найдена"}
        company_id = co.id

    from app.models.task import Task  # type: ignore[import]
    from app.models.project import Project  # type: ignore[import]

    by_year: dict = {}

    for yr in years:
        if metric == "projects_in_year":
            stmt = select(func.count()).select_from(Project).where(Project.portfolio_year == yr)
            if company_id: stmt = stmt.where(Project.company_id == company_id)
            r = await db.execute(stmt)
            by_year[str(yr)] = int(r.scalar_one() or 0)
            continue

        # Tasks-based metrics need full row fetch to compute overdue/carry
        t_stmt = select(Task).where(Task.portfolio_year == yr)
        if company_id: t_stmt = t_stmt.where(Task.company_id == company_id)
        t_res = await db.execute(t_stmt)
        ts = list(t_res.scalars().all())

        if metric == "tasks_in_year":
            by_year[str(yr)] = len(ts)
        elif metric == "tasks_done_in_year":
            by_year[str(yr)] = sum(1 for t in ts if (getattr(t, "status", "") or "").lower() in _DONE_STATUSES)
        elif metric == "tasks_overdue_in_year":
            by_year[str(yr)] = sum(1 for t in ts if _is_overdue(getattr(t, "due_date", None), getattr(t, "status", None)))
        elif metric == "tasks_carried_over_into_year":
            by_year[str(yr)] = sum(1 for t in ts if _is_carried_over(t))
        elif metric == "completion_pct":
            done = sum(1 for t in ts if (getattr(t, "status", "") or "").lower() in _DONE_STATUSES)
            by_year[str(yr)] = round(done/len(ts)*100, 1) if ts else 0

    # Compute deltas (year[i+1] - year[i])
    deltas: dict = {}
    sorted_years = sorted(years)
    for i in range(1, len(sorted_years)):
        prev_y, cur_y = sorted_years[i-1], sorted_years[i]
        prev_v = by_year.get(str(prev_y), 0) or 0
        cur_v = by_year.get(str(cur_y), 0) or 0
        delta_abs = cur_v - prev_v
        delta_pct = round((delta_abs / prev_v) * 100, 1) if prev_v else None
        deltas[f"{prev_y}->{cur_y}"] = {"abs": delta_abs, "pct": delta_pct}

    return {
        "_meta": {
            "tool": "compare_years",
            "metric_definition": {
                "tasks_in_year": "COUNT(tasks) WHERE portfolio_year = YEAR",
                "tasks_done_in_year": "COUNT(tasks) WHERE portfolio_year=YEAR AND lower(status) IN (done|completed|finished)",
                "tasks_overdue_in_year": "COUNT(tasks) WHERE portfolio_year=YEAR AND due_date < today AND status NOT IN done",
                "tasks_carried_over_into_year": "COUNT(tasks) WHERE portfolio_year=YEAR AND linked_year IS NOT NULL AND linked_year != portfolio_year",
                "completion_pct": "tasks_done_in_year / tasks_in_year * 100 (only same year)",
                "projects_in_year": "COUNT(projects) WHERE portfolio_year = YEAR",
            }.get(metric, "?"),
            "filter_company": company_name,
        },
        "metric": metric,
        "by_year": by_year,
        "deltas": deltas,
    }


# ─────────────────── Dispatch ───────────────────

_HANDLERS = {
    "get_company_full": _tool_get_company_full,
    "list_overdue_tasks": _tool_list_overdue_tasks,
    "compare_companies": _tool_compare_companies,
    "search_tasks": _tool_search_tasks,
    "get_financials": _tool_get_financials,
    "get_governance": _tool_get_governance,
    "get_credit_portfolio": _tool_get_credit_portfolio,
    "get_kpi_summary": _tool_get_kpi_summary,
    "search_audit_log": _tool_search_audit_log,
    "get_ratings_history": _tool_get_ratings_history,
    # Pack 7.7
    "get_task_details": _tool_get_task_details,
    "get_project_details": _tool_get_project_details,
    "search_comments": _tool_search_comments,
    "list_consultants": _tool_list_consultants,
    "list_carried_over": _tool_list_carried_over,
    # Pack 7.8
    "verify_count": _tool_verify_count,
    "compare_years": _tool_compare_years,
}


async def execute_tool(name: str, args: dict, db: AsyncSession) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await handler(args or {}, db)
    except Exception as e:
        return {"error": f"Tool '{name}' failed: {e}"}
