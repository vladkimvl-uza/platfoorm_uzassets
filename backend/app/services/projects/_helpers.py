"""Pure helpers for Projects domain (no DB / no IO)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.models.project import Project
from app.schemas.project import ProjectBrief

# Phase 16: Direction palette
DIR_PALETTE = {
    "strategy":    ("Стратегическое управление",  "#1e2787"),
    "finance":     ("Финансы / риски / аудит",    "#D97706"),
    "procurement": ("Система закупок",            "#3B6D11"),
    "orgdev":      ("Организационное развитие",   "#534AB7"),
    "digital":     ("Цифровизация",               "#1D9E75"),
    "operations":  ("Операционная эффективность", "#EF4444"),
    "governance":  ("Корпоративное управление",   "#72243E"),
    "esg":         ("ESG",                        "#1D9E75"),
    "pr":          ("Связи с общественностью",    "#D4537E"),
    "pmo":         ("PMO",                        "#2563EB"),
    "analytics":   ("Сводный отдел",              "#7C3AED"),
}


# Legacy-specific fields that live in `Project.extra` (JSONB)
EXTRA_FIELDS = {
    "consultant", "consultant_comment", "economic_effect",
    "quarters", "direction", "scope",
}


def enrich_with_direction_meta(items) -> None:
    """For each item with non-null direction code, populate `direction_meta`."""
    for item in items:
        if getattr(item, "direction_meta", None) is not None:
            continue
        code = getattr(item, "direction", None)
        if not code:
            continue
        code = str(code).lower().strip()
        if code in DIR_PALETTE:
            label, color = DIR_PALETTE[code]
            item.direction_meta = {"code": code, "label": label, "color": color}


def project_to_brief(
    p: Project,
    board_name: Optional[str],
    company_code: Optional[str],
    company_name: Optional[str],
    tasks_total: int = 0,
    tasks_done: int = 0,
    tasks_sum: float = 0.0,   # Σ дробных весов задач — для среднего прогресса
) -> ProjectBrief:
    """2026-05-26: добавлены linked_year / linked_project_id — без них
    save «Перенос FY+1» уходил в DB, но rehydrate возвращал null →
    UI показывал «не сохранилось»."""
    is_overdue = bool(p.due_date and p.status != "done" and p.due_date < date.today())
    extra = p.extra or {}
    return ProjectBrief(
        id=p.id, num=p.num, title=p.title,
        status=p.status, priority=p.priority,
        board_id=p.board_id, board_name=board_name,
        company_id=p.company_id, company_code=company_code, company_name=company_name,
        assignee_email=p.assignee_email, assignee_name=p.assignee_name,
        assignee_id=p.assignee_id,
        due_date=p.due_date, portfolio_year=p.portfolio_year,
        linked_year=p.linked_year,
        linked_project_id=p.linked_project_id,
        # Прогресс = СРЕДНЕЕ по весам задач (статус→%, quarterly по кварталам).
        progress_percent=(round(tasks_sum / tasks_total * 100)
                          if tasks_total > 0 else 0),
        is_overdue=is_overdue, tags=p.tags,
        sort_order=getattr(p, "sort_order", 0) or 0,
        tasks_total=tasks_total, tasks_done=tasks_done,
        # Legacy-specific
        quarters=extra.get("quarters") if isinstance(extra.get("quarters"), dict) else None,
        consultant=extra.get("consultant"),
        direction=extra.get("direction"),
        created_at=p.created_at, updated_at=p.updated_at,
    )


def serialize_comment(c, name: Optional[str], email: Optional[str]) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "author_id": str(c.author_id) if c.author_id else None,
        "author_name": name,
        "author_email": email,
        "body": c.body,
        "is_edited": c.is_edited,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
