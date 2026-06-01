"""Per-company activity feed orchestration (Pack 149).

Merges task_history + audit_log streams for ONE company. Over-fetches per
source to avoid silently dropping events when one dominates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import ensure_company_access
from app.models.user import User
from app.repositories.company_activity_repository import CompanyActivityRepository

# Mark `archived` / `DELETE` task-history events as critical — destructive.
_TASK_HIST_CRITICAL = {"archived", "DELETE", "delete"}

# Machine-formatted diff: "field: 'old' → 'new'" — NOT human-readable.
_DIFF_LIKE = re.compile(r"^\s*[\w_]+:\s*['\"]?.*?(→|->).+")

_ENTITY_RU = {
    "task":                   "Задача",
    "project":                "Проект",
    "comment":                "Комментарий",
    "kpi_submission":         "KPI",
    "bp_submission":          "Бизнес-план",
    "moderation_submission":  "Модерация",
    "user":                   "Пользователь",
    "user_session":           "Сессия",
    "mfa_attempt":            "MFA",
    "company":                "Компания",
    "broadcast":              "Рассылка",
    "attachment":             "Файл",
}


def _audit_title(
    action: str, entity_type: Optional[str],
    notes: Optional[str], http_path: Optional[str],
) -> str:
    """Build a human-readable title for an audit_log row.

    Priority:
      1. `notes` IF it's a real human sentence (NOT a machine diff)
      2. Friendly «<EntityType> · <action>» fallback
    """
    if notes and notes.strip():
        n = notes.strip()
        if not _DIFF_LIKE.match(n) and "→" not in n[:60]:
            return n[:140]
    et = (entity_type or "").lower()
    et_ru = _ENTITY_RU.get(et, entity_type or "—")
    return f"{et_ru} · {action}"


@dataclass
class CompanyActivityService:
    async def get_feed(
        self,
        code: str,
        db: AsyncSession,
        user: User,
        *,
        limit: int,
        days: int,
    ) -> dict[str, Any]:
        repo = CompanyActivityRepository(db)
        company = await repo.get_company_by_code(code)
        if not company:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, "Company not found"
            )
        await ensure_company_access(db, user, company.id)

        since = datetime.now(UTC) - timedelta(days=days)
        over = limit * 3

        th_rows = await repo.task_history(
            company_id=company.id, since=since, limit=over,
        )
        al_rows = await repo.audit_log(
            company_id=company.id, since=since, limit=over,
        )
        total_th = await repo.task_history_count(
            company_id=company.id, since=since,
        )
        total_al = await repo.audit_log_count(
            company_id=company.id, since=since,
        )

        items: list[dict] = []
        for r in th_rows:
            items.append({
                "kind": "task_history",
                "ts": r["ts"].isoformat(),
                "actor": r["actor"] or "—",
                "action": r["action"],
                "field": r["field_name"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "title": r["title"],
                "entity_id": r["entity_id"],
                "entity_type": "task",
                "is_critical": (r["action"] or "") in _TASK_HIST_CRITICAL,
            })
        for r in al_rows:
            items.append({
                "kind": "audit_log",
                "ts": r["ts"].isoformat(),
                "actor": r["actor"] or "—",
                "action": r["action"],
                "field": None,
                "title": _audit_title(
                    r["action"], r["entity_type"],
                    r.get("notes"), r.get("http_path"),
                ),
                "entity_id": r["entity_id"],
                "entity_type": r["entity_type"],
                "is_critical": bool(r["is_critical"]),
                "notes": r["notes"],
                "http_path": r.get("http_path"),
            })

        items.sort(key=lambda x: x["ts"], reverse=True)
        items = items[:limit]

        return {
            "company_code": company.code,
            "company_label": company.name_short or company.name_ru,
            "items": items,
            "total": len(items),
            "total_available": total_th + total_al,
            "since": since.isoformat(),
            "days": days,
        }
