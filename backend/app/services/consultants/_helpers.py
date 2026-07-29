"""Pure helpers / constants for Consultants domain."""
from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Optional
from uuid import uuid4

from app.core.progress import is_task_overdue
from app.models.consultant import Consultant

# Direction labels — mirrors legacy DIRS array
DIRS = [
    {"id": "strategy",    "label": "Стратегическое управление",  "color": "#6B7FD7"},
    {"id": "finance",     "label": "Финансы / риски / аудит",    "color": "#E0A458"},
    {"id": "procurement", "label": "Система закупок",            "color": "#7BA05B"},
    {"id": "orgdev",      "label": "Организационное развитие",   "color": "#A78BC7"},
    {"id": "digital",     "label": "Цифровизация",               "color": "#5FB3C4"},
    {"id": "operations",  "label": "Операционная эффективность", "color": "#E08A7B"},
    {"id": "governance",  "label": "Корпоративное управление",   "color": "#C77B96"},
    {"id": "esg",         "label": "ESG",                        "color": "#5FA98A"},
    {"id": "pr",          "label": "Связи с общественностью",    "color": "#D89BB5"},
    {"id": "pmo",         "label": "PMO",                        "color": "#7B9BD1"},
    {"id": "analytics",   "label": "Сводный отдел",              "color": "#9B8EC4"},
]

DIR_ID_TO_LABEL = {d["id"]: d["label"] for d in DIRS}
DIR_ID_TO_COLOR = {d["id"]: d["color"] for d in DIRS}

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def is_overdue(due: Optional[date]) -> bool:
    if not due:
        return False
    return due < datetime.now(UTC).date()


def is_overdue_task(status: Optional[str], due: Optional[date]) -> bool:
    """Просрочена ли задача С УЧЁТОМ статуса. Делегирует единому канону
    core.progress.is_task_overdue (рекуррентные/завершённые не просрочены).
    P0 аудита: раньше набор статусов дублировался в нескольких модулях."""
    return is_task_overdue(status, due)


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
