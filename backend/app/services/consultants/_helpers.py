"""Pure helpers / constants for Consultants domain."""
from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Optional
from uuid import uuid4

from app.models.consultant import Consultant

# Direction labels — mirrors legacy DIRS array
DIRS = [
    {"id": "strategy",    "label": "Стратегическое управление",  "color": "#1e2787"},
    {"id": "finance",     "label": "Финансы / риски / аудит",    "color": "#D97706"},
    {"id": "procurement", "label": "Система закупок",            "color": "#3B6D11"},
    {"id": "orgdev",      "label": "Организационное развитие",   "color": "#534AB7"},
    {"id": "digital",     "label": "Цифровизация",               "color": "#1D9E75"},
    {"id": "operations",  "label": "Операционная эффективность", "color": "#EF4444"},
    {"id": "governance",  "label": "Корпоративное управление",   "color": "#72243E"},
    {"id": "esg",         "label": "ESG",                        "color": "#1D9E75"},
    {"id": "pr",          "label": "Связи с общественностью",    "color": "#D4537E"},
    {"id": "pmo",         "label": "PMO",                        "color": "#2563EB"},
    {"id": "analytics",   "label": "Сводный отдел",              "color": "#7C3AED"},
]

DIR_ID_TO_LABEL = {d["id"]: d["label"] for d in DIRS}
DIR_ID_TO_COLOR = {d["id"]: d["color"] for d in DIRS}

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


# Статусы без точки завершения / завершённые — не бывают «просрочены»
# (1:1 с фронтом ConsultantsDrillModal.isOverdue).
_NON_OVERDUE_STATUSES = frozenset({"done", "quarterly", "monthly", "ongoing"})


def is_overdue(due: Optional[date]) -> bool:
    if not due:
        return False
    return due < datetime.now(UTC).date()


def is_overdue_task(status: Optional[str], due: Optional[date]) -> bool:
    """Просрочена ли задача С УЧЁТОМ статуса: рекуррентные (quarterly/monthly/
    ongoing) и завершённые не имеют финального дедлайна → не просрочены.
    Единый предикат для overview/by_company (раньше бэк считал recurring
    просроченными, а фронт-дрилл — нет, отсюда расхождение чисел)."""
    if status in _NON_OVERDUE_STATUSES:
        return False
    return is_overdue(due)


def slugify_consultant(name: str) -> str:
    table = str.maketrans({
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    })
    base = name.lower().translate(table)
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:48]
    if not base or not CODE_RE.match(base):
        base = "cons_" + uuid4().hex[:8]
    return base


def serialize_consultant(c: Consultant) -> dict:
    return {
        "id": str(c.id),
        "code": c.code,
        "name": c.name_ru,
        "name_en": c.name_en,
        "abbr": c.abbr,
        "color": c.color_hex,
        "is_big4": c.is_big4,
        "is_active": c.is_active,
        "sort_order": c.sort_order,
    }
