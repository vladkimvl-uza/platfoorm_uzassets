"""Per-company activity feed (Pack 149).

GET /companies/{code}/activity?limit=30
  — Returns the most recent audit-log + task-history events scoped to ONE
    company. Enforced via per-company scope: user without access to the
    company gets 403.

Use case: Activity widget on CompanyWorkspace Overview tab. Shows who
touched what in this company recently.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.models.company import Company
from app.models.user import User


log = logging.getLogger(__name__)
router = APIRouter(prefix="/companies", tags=["company-activity"])


# ─── action label helpers ─────────────────────────────────────────────

# Mark `archived` / `DELETE` task-history events as critical so the UI
# shows a red dot — they represent destructive or near-destructive actions.
_TASK_HIST_CRITICAL = {"archived", "DELETE", "delete"}


# Detect machine-formatted diff notes like `field: 'old' → 'new', other: …`
# — these are NOT human-readable, must NOT be used as title.
_DIFF_LIKE = re.compile(r"^\s*[\w_]+:\s*['\"]?.*?(→|->).+")


def _audit_title(action: str, entity_type: str | None, notes: str | None,
                 http_path: str | None) -> str:
    """Build a human-readable title for an audit_log row.

    Priority:
      1. `notes` IF it's a real human sentence (NOT a machine diff like
         "field: 'a' → 'b'"). Service code is supposed to write Russian
         descriptions; raw diff dumps fail that check.
      2. Friendly «<EntityType> · <action>» fallback.

    Raw HTTP paths NEVER make it into the title — they're available via the
    `http_path` field in the response for tooltips.
    """
    if notes and notes.strip():
        n = notes.strip()
        if not _DIFF_LIKE.match(n) and "→" not in n[:60]:
            return n[:140]
    et = (entity_type or "").lower()
    et_ru = {
        "task": "Задача",
        "project": "Проект",
        "comment": "Комментарий",
        "kpi_submission": "KPI",
        "bp_submission": "Бизнес-план",
        "moderation_submission": "Модерация",
        "user": "Пользователь",
        "user_session": "Сессия",
        "mfa_attempt": "MFA",
        "company": "Компания",
        "broadcast": "Рассылка",
        "attachment": "Файл",
    }.get(et, entity_type or "—")
    return f"{et_ru} · {action}"


@router.get("/{code}/activity")
async def company_activity_feed(
    code: str,
    limit: int = Query(30, ge=1, le=200),
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Aggregate recent activity for this company:

      - task_history: status_changed, field_updated, archived, result_set/cleared
      - audit_log:    user-visible events tagged with this company in entity_id

    To avoid silently dropping events when one stream dominates, we over-fetch
    `limit*3` from EACH source and only cap to `limit` after the merge+sort.
    We also report `total_available` (rows in window before the cap) so the UI
    «Все (N)» button doesn't lie when actual activity exceeds `limit`.
    """
    company = (await db.execute(
        select(Company).where(Company.code == code.lower())
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")

    await ensure_company_access(db, user, company.id)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    over = limit * 3  # over-fetch budget per source

    # ─── Task history scoped to this company's tasks ──────────────
    th_rows = (await db.execute(text("""
        SELECT th.created_at AS ts,
               th.action,
               th.field_name,
               th.old_value, th.new_value,
               t.id::text AS entity_id, t.title,
               COALESCE(u.full_name, u.email) AS actor
        FROM task_history th
        JOIN tasks t ON t.id = th.task_id
        LEFT JOIN users u ON u.id = th.actor_id
        WHERE t.company_id = :co AND th.created_at >= :since
        ORDER BY th.created_at DESC
        LIMIT :lim
    """), {"co": company.id, "since": since, "lim": over})).mappings().all()

    # ─── Audit log scoped to entities belonging to this company ────
    al_rows = (await db.execute(text("""
        SELECT al.created_at AS ts,
               al.action,
               al.actor_email AS actor,
               al.entity_type,
               al.entity_id,
               COALESCE(al.notes, '') AS notes,
               al.is_critical,
               al.http_path
        FROM audit_log al
        WHERE al.created_at >= :since
          AND (
            al.entity_id IN (
              SELECT id::text FROM tasks    WHERE company_id = :co
              UNION ALL
              SELECT id::text FROM projects WHERE company_id = :co
            )
            OR al.entity_id = :co_str
          )
        ORDER BY al.created_at DESC
        LIMIT :lim
    """), {"co": company.id, "co_str": str(company.id), "since": since,
           "lim": over})).mappings().all()

    # ─── Honest count: rows in window (capped at 1000 to keep query cheap) ──
    total_th = (await db.execute(text("""
        SELECT COUNT(*) FROM task_history th
        JOIN tasks t ON t.id = th.task_id
        WHERE t.company_id = :co AND th.created_at >= :since
    """), {"co": company.id, "since": since})).scalar() or 0
    total_al = (await db.execute(text("""
        SELECT COUNT(*) FROM audit_log al
        WHERE al.created_at >= :since
          AND (
            al.entity_id IN (
              SELECT id::text FROM tasks    WHERE company_id = :co
              UNION ALL
              SELECT id::text FROM projects WHERE company_id = :co
            )
            OR al.entity_id = :co_str
          )
    """), {"co": company.id, "co_str": str(company.id), "since": since})).scalar() or 0

    # ─── Merge + sort + cap ──────────────────────────────────────
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
            "title": _audit_title(r["action"], r["entity_type"], r.get("notes"), r.get("http_path")),
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
        "total_available": int(total_th) + int(total_al),
        "since": since.isoformat(),
        "days": days,
    }
