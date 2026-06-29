"""Pure helpers / constants for Shareholder Dashboard."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Optional

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

SECTOR_ORDER = ["mining_metallurgy", "oil_gas", "energy", "transport_communications", "other"]
SECTOR_LABELS = {
    "mining_metallurgy":         "Горнодобывающий",
    "oil_gas":                   "Нефтегазовый",
    "energy":                    "Энергетика",
    "transport_communications":  "Транспорт и коммуникации",
    "other":                     "Другой сектор",
}
SECTOR_COLORS = {
    "mining_metallurgy":         "#9B8EC4",
    "oil_gas":                   "#0A7B5E",
    "energy":                    "#EF9F27",
    "transport_communications":  "#378ADD",
    "other":                     "#888780",
}

# Drill-modal sector colors (different from shareholder palette)
DDM_SECTOR_COLOR = {
    "mining_metallurgy":         "#7F77DD",
    "oil_gas":                   "#1D9E75",
    "energy":                    "#EF9F27",
    "transport_communications":  "#378ADD",
    "other":                     "#888780",
}

AGENCIES_CREDIT = ["Fitch", "S&P", "Moody's"]
AGENCY_ESG = "Sustainable Fitch"
# Все ESG-агентства — ESG-кольцо считает покрытие по ОБЪЕДИНЕНИЮ (раньше только
# Sustainable Fitch → покрытие занижалось, игнорируя S&P ESG и CDP).
AGENCIES_ESG = ["Sustainable Fitch", "S&P ESG", "CDP"]
AGENCY_LABELS = {
    "Fitch":             "FITCH RATINGS",
    "S&P":               "S&P GLOBAL",
    "Moody's":           "MOODY'S",
    "Sustainable Fitch": "ESG",
}
AGENCY_COLORS = {
    "Fitch":             "#1D9E75",
    "S&P":               "#E24B4A",
    "Moody's":           "#7F77DD",
    "Sustainable Fitch": "#1D9E75",
}

STATUS_DEFS = [
    ("init",      "Инициирование",    "#7F77DD"),
    ("new",       "Не начато",        "#CBD5E1"),
    ("active",    "В процессе",       "#378ADD"),
    ("review",    "На согласовании",  "#EF9F27"),
    ("done",      "Завершено",        "#1D9E75"),
    ("quarterly", "Ежеквартально",    "#A855F7"),
    ("monthly",   "Ежемесячно",       "#A855F7"),
    ("ongoing",   "Постоянно",        "#A855F7"),
]

BUCKET_LABEL = {
    "total":    "ВСЕГО",
    "done":     "ЗАВЕРШЕНО",
    "active":   "В ПРОЦЕССЕ",
    "overdue":  "ПРОСРОЧЕНО",
    "deferred": "ПЕРЕНЕСЕНО",
}
BUCKET_TITLE = {
    "total":    "Все элементы портфеля",
    "done":     "Завершённые элементы",
    "active":   "Элементы в процессе исполнения",
    "overdue":  "Просроченные элементы",
    "deferred": "Перенесённые элементы",
}
BUCKET_ACCENT = {
    "total":    "#7F77DD",
    "done":     "#1D9E75",
    "active":   "#EF9F27",
    "overdue":  "#E24B4A",
    "deferred": "#7F77DD",
}

CREDIT_SCALE = {
    "AAA": 22, "AA+": 21, "AA": 20, "AA-": 19,
    "A+": 18, "A": 17, "A-": 16,
    "BBB+": 15, "BBB": 14, "BBB-": 13,
    "BB+": 12, "BB": 11, "BB-": 10,
    "B+": 9, "B": 8, "B-": 7,
    "CCC+": 6, "CCC": 5, "CCC-": 4,
    "CC": 3, "C": 2, "D": 1,
}


# Повторяющиеся статусы — НЕ «просрочены» по своей природе (закрываются циклично).
RECURRING_STATUSES = frozenset({"monthly", "ongoing", "quarterly"})


def is_overdue(due: Optional[date], status: str) -> bool:
    if not due or status == "done" or status in RECURRING_STATUSES:
        return False
    return due < datetime.now(UTC).date()


def matches_bucket(status: str, due_date, linked_year, today: date, bucket: str) -> bool:
    if bucket == "total":
        return True
    if bucket == "done":
        return status == "done"
    if bucket == "active":
        return status == "active"
    if bucket == "overdue":
        return (due_date is not None and due_date < today
                and status != "done" and status not in RECURRING_STATUSES)
    if bucket == "deferred":
        return linked_year is not None
    return False


def credit_rank(rating_obj: Optional[dict]) -> int:
    if not rating_obj or not rating_obj.get("rating"):
        return 0
    return CREDIT_SCALE.get(rating_obj["rating"].strip(), 0)


def best_credit_rank(row: dict) -> int:
    return max(
        credit_rank(row.get("fitch")),
        credit_rank(row.get("sp")),
        credit_rank(row.get("moody")),
    )


def best_credit_label(row: dict) -> Optional[str]:
    best_r = 0
    best_label = None
    for ag_key in ("fitch", "sp", "moody"):
        v = row.get(ag_key)
        r = credit_rank(v)
        if r > best_r:
            best_r = r
            best_label = v["rating"]
    return best_label


def best_esg_score(row: dict) -> float:
    scores = []
    for k in ("sf", "sp_esg", "cdp"):
        v = row.get(k)
        if v and v.get("score") is not None:
            try:
                scores.append(float(v["score"]))
            except (ValueError, TypeError):
                pass
    return max(scores) if scores else 0


def item_dict_drill(r, is_overdue_flag: bool, days_overdue: Optional[int]) -> dict:
    return {
        "id":                str(r.id),
        "num":               r.num,
        "title":             r.title,
        "status":            r.status,
        "priority":          r.priority,
        "due_date":          r.due_date.isoformat() if r.due_date else None,
        "is_overdue":        is_overdue_flag,
        "days_overdue":      days_overdue,
        "progress_percent":  int(r.progress_percent or 0),
        "assignee_name":     r.assignee_name,
    }


def item_sort_key(it: dict):
    ov = 0 if it["is_overdue"] else 1
    due = it["due_date"] or "9999-99-99"
    return (ov, due, -(it["progress_percent"] or 0))
