"""Admin broadcast service (Pack 11.2).

Responsibilities:
  1. `compute_next_run_at()`     — given a template, compute next fire time
  2. `resolve_recipients()`      — expand targeting rules into actual user IDs
  3. `dispatch_template()`       — create dispatch + notifications + WS push
  4. `acknowledge_notification()` — record ack, update counts
  5. `analytics_for_template()`  — aggregate stats for the admin view
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # 2026-05-26: explicit warning so missing tzdata is observable, not silent.
    import logging as _early_log
    _early_log.getLogger(__name__).warning(
        "zoneinfo unavailable — scheduled broadcasts will fall back to UTC. "
        "Install backports.zoneinfo or upgrade Python ≥3.9."
    )
    ZoneInfo = None  # type: ignore[assignment]

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_broadcast import (
    AdminBroadcastAck,
    AdminBroadcastDispatch,
    AdminBroadcastTemplate,
)
from app.models.notification import NOTIFICATION_TYPES, Notification
from app.models.user import Group, Role, User
from app.services.notifications_service import notifications_ws_manager

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#   Schedule computation
# ════════════════════════════════════════════════════════════

def _tz(name: Optional[str]) -> Any:
    """Return tzinfo object; falls back to UTC if zoneinfo unavailable.

    2026-05-26: silent fallback к UTC заменён на warning — раньше
    некорректный tz-name в template config приводил к молчаливому drift'у
    schedule на несколько часов.
    """
    if not name or ZoneInfo is None:
        return UTC
    try:
        return ZoneInfo(name)
    except Exception as e:
        log.warning("Invalid timezone %r in broadcast template: %s — using UTC fallback", name, e)
        return UTC


def _parse_hhmm(s: Optional[str]) -> tuple[int, int]:
    if not s or ":" not in s:
        return (9, 0)
    h, m = s.split(":", 1)
    try:
        return (int(h), int(m))
    except Exception as e:
        log.warning("Invalid HH:MM %r in broadcast template: %s — using 09:00 fallback", s, e)
        return (9, 0)


def compute_next_run_at(
    template: AdminBroadcastTemplate,
    *,
    after: Optional[datetime] = None,
) -> Optional[datetime]:
    """Compute the next time the template should fire, in UTC.

    Returns None when no further runs are scheduled (oneshot already fired,
    end_at passed, no valid weekdays, etc.).
    """
    now = (after or datetime.now(UTC))
    # If start_at is in the future and we have no last_run yet, schedule at start_at
    if template.schedule_start_at and template.schedule_start_at > now and not template.last_run_at:
        candidate = template.schedule_start_at
        if not template.schedule_end_at or candidate <= template.schedule_end_at:
            return candidate
        return None
    if template.schedule_end_at and now > template.schedule_end_at:
        return None

    if template.schedule_mode == "oneshot":
        if template.last_run_at:
            return None  # already fired
        if template.schedule_start_at:
            return template.schedule_start_at
        return now  # fire immediately

    cfg = template.schedule_config or {}
    tz = _tz(cfg.get("tz") or "Asia/Tashkent")
    hh, mm = _parse_hhmm(cfg.get("time"))

    local_now = now.astimezone(tz)
    base = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    if template.schedule_mode == "interval":
        weekdays = cfg.get("weekdays")  # list of int 0..6
        if weekdays:
            # Find next day whose weekday is in list, at hh:mm
            for offset in range(0, 8):
                candidate = (base + timedelta(days=offset))
                if candidate.weekday() in weekdays and candidate > local_now:
                    utc_candidate = candidate.astimezone(UTC)
                    if template.schedule_end_at and utc_candidate > template.schedule_end_at:
                        return None
                    return utc_candidate
            return None

        every_days = int(cfg.get("every_days") or 0)
        every_weeks = int(cfg.get("every_weeks") or 0)
        every_months = int(cfg.get("every_months") or 0)
        step_days = every_days + (every_weeks * 7) + (every_months * 30)
        if step_days <= 0:
            step_days = 1

        if template.last_run_at:
            last_local = template.last_run_at.astimezone(tz)
            candidate = (last_local + timedelta(days=step_days)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        else:
            candidate = base if base > local_now else base + timedelta(days=step_days)
        utc_candidate = candidate.astimezone(UTC)
        if template.schedule_end_at and utc_candidate > template.schedule_end_at:
            return None
        return utc_candidate

    # cron mode — minimal support: not implemented fully, fallback to interval if cron present
    return None


# ════════════════════════════════════════════════════════════
#   Recipient resolution
# ════════════════════════════════════════════════════════════

def _eval_filter_expr(user: User, expr: Optional[dict]) -> bool:
    """Evaluate user against template.target_filter_expr."""
    if not expr or not isinstance(expr, dict):
        return True
    ops = expr.get("ops") or []
    combine = (expr.get("combine") or "AND").upper()
    results: list[bool] = []
    for atom in ops:
        field = atom.get("field"); op = atom.get("op"); val = atom.get("value")
        if not field or not op:
            continue
        actual = getattr(user, field, None)
        try:
            if   op == "=":  results.append(actual == val)
            elif op == "!=": results.append(actual != val)
            elif op == ">":  results.append(actual is not None and float(actual) >  float(val))
            elif op == ">=": results.append(actual is not None and float(actual) >= float(val))
            elif op == "<":  results.append(actual is not None and float(actual) <  float(val))
            elif op == "<=": results.append(actual is not None and float(actual) <= float(val))
            else: results.append(False)
        except (TypeError, ValueError):
            results.append(False)
    if not results:
        return True
    return all(results) if combine == "AND" else any(results)


async def resolve_recipients(
    db: AsyncSession, template: AdminBroadcastTemplate,
) -> list[User]:
    """Expand template targeting into a deduped list of active User rows."""
    user_ids: set[UUID] = set()

    if template.target_all:
        rows = (await db.execute(
            select(User).where(User.is_active.is_(True)),
        )).scalars().all()
        return [u for u in rows if _eval_filter_expr(u, template.target_filter_expr)]

    if template.target_user_ids:
        for uid in template.target_user_ids:
            try: user_ids.add(UUID(str(uid)))
            except Exception: pass

    if template.target_group_codes:
        rows = (await db.execute(
            select(User).join(User.groups).where(
                and_(Group.code.in_(template.target_group_codes), User.is_active.is_(True)),
            ),
        )).scalars().all()
        for u in rows: user_ids.add(u.id)

    if template.target_role_codes:
        rows = (await db.execute(
            select(User).join(User.roles).where(
                and_(Role.code.in_(template.target_role_codes), User.is_active.is_(True)),
            ),
        )).scalars().all()
        for u in rows: user_ids.add(u.id)

    # company / sector targeting — placeholder for future user.company_id link
    # (currently no direct user-company FK in the platform; skipped silently)

    if not user_ids:
        return []

    users = (await db.execute(
        select(User).where(and_(User.id.in_(user_ids), User.is_active.is_(True))),
    )).scalars().all()
    return [u for u in users if _eval_filter_expr(u, template.target_filter_expr)]


# ════════════════════════════════════════════════════════════
#   Dispatch
# ════════════════════════════════════════════════════════════

async def dispatch_template(
    db: AsyncSession,
    *,
    template: AdminBroadcastTemplate,
    triggered_by_id: Optional[UUID] = None,
    trigger: str = "schedule",
) -> AdminBroadcastDispatch:
    """Create one dispatch + N notifications for the resolved recipients."""
    now = datetime.now(UTC)

    recipients = await resolve_recipients(db, template)

    dispatch = AdminBroadcastDispatch(
        template_id=template.id,
        dispatched_at=now,
        recipients_count=len(recipients),
        delivered_count=0, read_count=0, acked_count=0,
        dispatched_by_id=triggered_by_id,
        trigger=trigger,
    )
    db.add(dispatch)
    await db.flush()

    deadline = (now + timedelta(hours=template.ack_deadline_hours)) if template.ack_deadline_hours else None
    requires_ack = template.ack_mode != "none"

    # Make sure broadcast notification type is in catalog (graceful — service tolerates unknown types)
    notif_type = "broadcast.announcement"
    if notif_type not in NOTIFICATION_TYPES:
        NOTIFICATION_TYPES[notif_type] = {"priority": template.priority, "label": "Объявление"}

    delivered = 0
    ws_pushes: list[tuple[UUID, dict]] = []

    for u in recipients:
        notif = Notification(
            created_at=now,
            recipient_user_id=u.id,
            type=notif_type,
            priority=template.priority,
            title=template.title,
            body=template.body,
            payload={"broadcast": True, "template_name": template.name},
            link_url=template.link_url,
            source_module="broadcast",
            source_entity_id=str(template.id),
            source_user_id=template.created_by_id,
            broadcast_template_id=template.id,
            broadcast_dispatch_id=dispatch.id,
            requires_ack=requires_ack,
            ack_mode=template.ack_mode if requires_ack else None,
            ack_question=template.ack_question,
            ack_options=template.ack_options,
            is_sticky=template.is_sticky,
            ack_deadline=deadline,
            show_site_banner=template.show_site_banner_on_overdue,
        )
        db.add(notif)
        delivered += 1
        # Buffer WS push; send after commit so notif.id is final
        ws_pushes.append((u.id, {
            "id": "pending",
            "type": notif_type,
            "title": template.title,
            "body": template.body,
            "priority": template.priority,
            "is_sticky": template.is_sticky,
            "requires_ack": requires_ack,
            "ack_mode": template.ack_mode if requires_ack else None,
        }))

    dispatch.delivered_count = delivered
    template.last_run_at = now
    template.total_dispatches = (template.total_dispatches or 0) + 1
    template.total_recipients_lifetime = (template.total_recipients_lifetime or 0) + delivered
    template.next_run_at = compute_next_run_at(template, after=now)

    await db.commit()
    # Pack 13.2.3: fire-and-forget TG forward (own DB session, never blocks)
    try:
        from app.services.telegram_notify_hook_bg import schedule_forward
        schedule_forward(str(notif.id))
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning('tg-forward schedule failed: %s', _e)
    await db.refresh(dispatch)

    # WS push (best-effort, errors swallowed)
    for uid, payload in ws_pushes:
        try:
            await notifications_ws_manager.send_to_user(uid, {"event": "broadcast.delivered", "payload": payload})
        except Exception:
            pass

    return dispatch


# ════════════════════════════════════════════════════════════
#   Ack
# ════════════════════════════════════════════════════════════

async def acknowledge_notification(
    db: AsyncSession, *, notification: Notification, user: User,
    response_text: Optional[str] = None,
    response_value: Optional[str] = None,
    response_file: Optional[dict] = None,
) -> AdminBroadcastAck:
    """Record an ack and update dispatch/template counters."""
    if notification.recipient_user_id != user.id:
        raise PermissionError("Not your notification")
    if notification.acknowledged_at:
        # Already acknowledged — return existing ack if any
        existing = (await db.execute(
            select(AdminBroadcastAck).where(AdminBroadcastAck.notification_id == notification.id),
        )).scalars().first()
        if existing:
            return existing

    now = datetime.now(UTC)
    ack = AdminBroadcastAck(
        notification_id=notification.id,
        dispatch_id=notification.broadcast_dispatch_id,
        template_id=notification.broadcast_template_id,
        user_id=user.id,
        acknowledged_at=now,
        response_text=response_text,
        response_value=response_value,
        response_file=response_file,
    )
    db.add(ack)

    notification.acknowledged_at = now
    notification.ack_response = {
        "text": response_text, "value": response_value, "file": response_file,
    }
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = now

    # Counters
    if notification.broadcast_dispatch_id:
        d = await db.get(AdminBroadcastDispatch, notification.broadcast_dispatch_id)
        if d:
            d.acked_count = (d.acked_count or 0) + 1
    if notification.broadcast_template_id:
        t = await db.get(AdminBroadcastTemplate, notification.broadcast_template_id)
        if t:
            t.total_acks_lifetime = (t.total_acks_lifetime or 0) + 1

    await db.commit()
    await db.refresh(ack)
    return ack


# ════════════════════════════════════════════════════════════
#   Preview recipients
# ════════════════════════════════════════════════════════════

async def preview_recipients(
    db: AsyncSession, template: AdminBroadcastTemplate, *, sample_size: int = 20,
) -> dict[str, Any]:
    """Resolve targeting and return total + sample for admin UI."""
    users = await resolve_recipients(db, template)
    sample = [
        {"id": str(u.id), "email": u.email, "full_name": u.full_name}
        for u in users[:sample_size]
    ]
    return {"total": len(users), "sample": sample}


# ════════════════════════════════════════════════════════════
#   Analytics
# ════════════════════════════════════════════════════════════

async def analytics_for_template(
    db: AsyncSession, template: AdminBroadcastTemplate, *, history_limit: int = 10,
) -> dict[str, Any]:
    """Aggregate stats for the admin view."""
    last = (await db.execute(
        select(AdminBroadcastDispatch)
        .where(AdminBroadcastDispatch.template_id == template.id)
        .order_by(AdminBroadcastDispatch.dispatched_at.desc())
        .limit(1),
    )).scalars().first()

    history = (await db.execute(
        select(AdminBroadcastDispatch)
        .where(AdminBroadcastDispatch.template_id == template.id)
        .order_by(AdminBroadcastDispatch.dispatched_at.desc())
        .limit(history_limit),
    )).scalars().all()

    # Response distribution over last dispatch
    distribution: dict[str, int] = {}
    non_responders: list[dict] = []
    if last:
        acks = (await db.execute(
            select(AdminBroadcastAck).where(AdminBroadcastAck.dispatch_id == last.id),
        )).scalars().all()
        for a in acks:
            key = (a.response_value or "Подтверждено")
            distribution[key] = distribution.get(key, 0) + 1

        # Non-responders: notifications in this dispatch without ack
        non_acked = (await db.execute(
            select(Notification, User)
            .join(User, User.id == Notification.recipient_user_id)
            .where(and_(
                Notification.broadcast_dispatch_id == last.id,
                Notification.acknowledged_at.is_(None),
            ))
            .limit(50),
        )).all()
        for _notif, u in non_acked:
            non_responders.append({"id": str(u.id), "email": u.email, "full_name": u.full_name})

    return {
        "template_id": template.id,
        "template_name": template.name,
        "is_active": template.is_active,
        "dispatches_total": template.total_dispatches,
        "last_run_at": template.last_run_at,
        "next_run_at": template.next_run_at,
        "last_recipients": last.recipients_count if last else 0,
        "last_delivered":  last.delivered_count  if last else 0,
        "last_read":       last.read_count       if last else 0,
        "last_acked":      last.acked_count      if last else 0,
        "response_distribution": distribution,
        "non_responders": non_responders,
        "history": [
            {
                "id": h.id, "template_id": h.template_id, "dispatched_at": h.dispatched_at,
                "recipients_count": h.recipients_count, "delivered_count": h.delivered_count,
                "read_count": h.read_count, "acked_count": h.acked_count,
                "dispatched_by_id": h.dispatched_by_id, "trigger": h.trigger, "error": h.error,
            } for h in history
        ],
    }
