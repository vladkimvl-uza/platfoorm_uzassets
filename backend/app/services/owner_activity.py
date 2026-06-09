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

from app.models.notification import Notification
from app.services.notifications_service import notify

log = logging.getLogger(__name__)

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


async def notify_owners_of_change(
    db: AsyncSession,
    *,
    http_path: str,
    http_method: str,
    status: int,
    actor_id: Optional[str],
    actor_email: Optional[str],
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
    recipient_ids = await _recipients(db, company_id)

    verb = _verb(method, (http_path or "").split("?", 1)[0])
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
                in_app_only=True,
                commit=True,
            )
        except Exception as e:  # noqa: BLE001 — never break the request path
            log.warning("activity notify failed for user=%s: %s", rid, e)
