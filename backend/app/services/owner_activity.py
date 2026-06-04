"""Owner activity notifications.

The platform OWNER(s) want an in-app feed of every meaningful change across ALL
companies — status changes, comments, file uploads, and any data edited through
the module editors (KPI / financials / ESG / governance / ratings / BP / credit /
investment / …).

This is driven from the audit middleware (the single chokepoint that sees every
mutating request), so no per-endpoint wiring is needed. Delivery is IN-APP ONLY
(the notification bell) — Telegram/e-mail per change would be spam — and is
throttled per (owner, module, actor) so the KPI editor's 1.5s auto-save can't
flood the feed.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User
from app.services.notifications_service import notify

log = logging.getLogger(__name__)

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# Path-prefix → human label. module_from_path() in audit_service doesn't cover
# tasks/comments/attachments, so we classify by path here. Order: longest first.
_PATH_LABELS: list[tuple[str, str]] = [
    ("/business-plan", "Бизнес-план"),
    ("/credit-portfolio", "Кредитный портфель"),
    ("/invest-projects", "Инвест-проекты"),
    ("/tasks", "Задачи"),
    ("/projects", "Проекты"),
    ("/comments", "Комментарии"),
    ("/attachments", "Файлы"),
    ("/kpi", "KPI"),
    ("/financials", "Финансы"),
    ("/bp", "Бизнес-план"),
    ("/esg", "ESG"),
    ("/governance", "Корпоративное управление"),
    ("/ratings", "Рейтинги"),
    ("/credit", "Кредитный портфель"),
    ("/investment", "Инвест-проекты"),
    ("/finmodel", "Финмодель"),
    ("/treasury", "Казначейство"),
    ("/procurement", "Закупки"),
    ("/companies", "Компании"),
    ("/notes", "Заметки"),
    ("/elasticity", "Эластичность"),
]

# Window for collapsing rapid edits (e.g. editor auto-save) into one entry.
_THROTTLE_MINUTES = 10


def _classify(path: str) -> Optional[str]:
    p = path.split("?", 1)[0]
    for pre, label in _PATH_LABELS:
        if p == pre or p.startswith(pre + "/"):
            return label
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


async def notify_owners_of_change(
    db: AsyncSession,
    *,
    http_path: str,
    http_method: str,
    status: int,
    actor_id: Optional[str],
    actor_email: Optional[str],
) -> None:
    """Best-effort: notify all active OWNERs (except the actor) of a change.

    Only fires for successful mutating requests on a recognised data module.
    Throttled per (owner, module, actor) to avoid auto-save floods.
    """
    method = (http_method or "").upper()
    if method not in _MUTATING or status >= 400:
        return
    label = _classify(http_path or "")
    if label is None:
        return

    actor_uuid: Optional[UUID] = None
    if actor_id:
        try:
            actor_uuid = UUID(str(actor_id))
        except (ValueError, TypeError):
            actor_uuid = None

    owner_ids = (
        await db.execute(
            select(User.id).where(User.is_owner.is_(True), User.is_active.is_(True))
        )
    ).scalars().all()

    verb = _verb(method, (http_path or "").split("?", 1)[0])
    title = f"{label}: {verb}"
    body = actor_email or "пользователь"
    since = datetime.now(UTC) - timedelta(minutes=_THROTTLE_MINUTES)

    for oid in owner_ids:
        if actor_uuid is not None and oid == actor_uuid:
            continue  # don't notify an owner about their own action
        try:
            # Throttle: skip if a recent same (module, actor) entry already exists.
            dup = (
                await db.execute(
                    select(Notification.id).where(
                        Notification.recipient_user_id == oid,
                        Notification.type == "owner.activity",
                        Notification.source_module == label,
                        Notification.source_user_id == actor_uuid,
                        Notification.created_at > since,
                    ).limit(1)
                )
            ).first()
            if dup is not None:
                continue
            await notify(
                db,
                recipient_id=oid,
                type="owner.activity",
                title=title,
                body=body,
                source_module=label,
                source_entity_id=(http_path or "")[:256],
                source_user_id=actor_uuid,
                in_app_only=True,
                commit=True,
            )
        except Exception as e:  # noqa: BLE001 — never break the request path
            log.warning("owner-activity notify failed for owner=%s: %s", oid, e)
