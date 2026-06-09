"""In-process рассылка deadline.approaching / deadline.missed.

Раз в час сканирует проекты/задачи: дедлайн в ближайшие 3 дня → approaching;
дедлайн в прошлом и не закрыт → missed. Получатели: watcher'ы + исполнитель.
Дедуп через deadline_notified (сущность, тип, дата) — повторно не шлём, но
при сдвиге дедлайна (новая дата) уведомляем заново.

Single-container: один asyncio-таск в lifespan + advisory-lock.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import text

log = logging.getLogger(__name__)

_TASK: Optional[asyncio.Task] = None
_STOP = asyncio.Event()
SCAN_INTERVAL_SEC = 3600
_EXCLUDE_STATUS = ("done", "quarterly", "monthly", "ongoing", "deferred")
_APPROACH_DAYS = 3


async def _recipients(db, entity_type: str, entity_id: str, assignee_email: Optional[str], creator_id) -> set:
    """Получатели дедлайн-уведомления: watcher'ы + исполнитель + автор."""
    from app.services import watch_service
    ids = set(await watch_service.watcher_ids(db, entity_type, entity_id))
    if assignee_email:
        r = await db.execute(
            text("SELECT id FROM users WHERE lower(email) = lower(:em) AND is_active = true"),
            {"em": assignee_email},
        )
        uid = r.scalar_one_or_none()
        if uid:
            ids.add(uid)
    if creator_id:
        ids.add(creator_id)
    return ids


async def _tick() -> int:
    from app.database import AsyncSessionLocal
    from app.services.notifications_service import notify

    today = datetime.now(UTC).date()
    sent = 0
    async with AsyncSessionLocal() as db:
        for etype, tbl in (("project", "projects"), ("task", "tasks")):
            kind_label = "Проект" if etype == "project" else "Задача"
            for kind, where in (
                ("approaching", "e.due_date::date >= :today AND e.due_date::date <= :soon"),
                ("due_1d", "e.due_date::date = :tomorrow"),
                ("missed", "e.due_date::date < :today"),
            ):
                rows = (await db.execute(
                    text(
                        f"SELECT e.id::text, e.num, e.title, e.due_date::date, e.assignee_email, e.company_id::text, e.creator_id "
                        f"FROM {tbl} e WHERE e.due_date IS NOT NULL "
                        f"  AND e.status <> ALL(:excl) AND {where} "
                        f"  AND NOT EXISTS (SELECT 1 FROM deadline_notified dn "
                        f"      WHERE dn.entity_type = :et AND dn.entity_id = e.id::text "
                        f"        AND dn.kind = :kind AND dn.due_date = e.due_date::date) "
                        f"LIMIT 500"
                    ),
                    {"today": today, "soon": today + timedelta(days=_APPROACH_DAYS),
                     "tomorrow": today + timedelta(days=1),
                     "excl": list(_EXCLUDE_STATUS), "et": etype, "kind": kind},
                )).all()
                for eid, num, title, due, assignee, cid, creator in rows:
                    recips = await _recipients(db, etype, eid, assignee, creator)
                    days = abs((due - today).days)
                    if kind == "due_1d":
                        ntype = "deadline.approaching"
                        ntitle = f"Дедлайн завтра: {title}"[:255]
                        body = f"{kind_label} · срок завтра, {due.strftime('%d.%m.%Y')}"
                    elif kind == "approaching":
                        ntype = "deadline.approaching"
                        ntitle = f"Дедлайн приближается: {title}"[:255]
                        body = f"{kind_label} · до {due.strftime('%d.%m.%Y')}" + (f" ({days} дн)" if days else " (сегодня)")
                    else:
                        ntype = "deadline.missed"
                        ntitle = f"Дедлайн пропущен: {title}"[:255]
                        body = f"{kind_label} · просрочено {days} дн (до {due.strftime('%d.%m.%Y')})"
                    link = f"/library/companies/{cid}" if cid else None
                    for uid in recips:
                        try:
                            await notify(
                                db, recipient_id=uid, type=ntype, title=ntitle, body=body,
                                payload={"entity_type": etype, "entity_id": eid, "due_date": str(due)},
                                link_url=link, source_module=tbl, source_entity_id=eid,
                                company_id=cid,
                                commit=True,
                            )
                            sent += 1
                        except Exception:
                            continue
                    # дедуп — отметить отправленным (даже если получателей не было,
                    # чтобы не сканировать одно и то же каждый час)
                    await db.execute(
                        text(
                            "INSERT INTO deadline_notified (entity_type, entity_id, kind, due_date) "
                            "VALUES (:et, :eid, :kind, :due) ON CONFLICT DO NOTHING"
                        ),
                        {"et": etype, "eid": eid, "kind": kind, "due": due},
                    )
                    await db.commit()
    if sent:
        log.info("[deadline-scheduler] sent %d deadline notifications", sent)
    return sent


async def _run_loop() -> None:
    log.info("[deadline-scheduler] loop started")
    try:
        await asyncio.wait_for(_STOP.wait(), timeout=40.0)
        return
    except TimeoutError:
        pass
    while not _STOP.is_set():
        try:
            await _tick()
        except Exception as e:
            log.exception("[deadline-scheduler] tick error: %s", e)
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SCAN_INTERVAL_SEC)
        except TimeoutError:
            continue
    log.info("[deadline-scheduler] loop stopped")


def start_scheduler() -> None:
    global _TASK
    if _TASK and not _TASK.done():
        return
    _STOP.clear()
    loop = asyncio.get_event_loop()

    async def _start_with_lock() -> None:
        from app.core.scheduler_lock import try_acquire_scheduler_lock
        held = await try_acquire_scheduler_lock("deadlines")
        if not held:
            log.info("[deadline-scheduler] another worker holds the lock — idle")
            return
        await _run_loop()

    _TASK = loop.create_task(_start_with_lock(), name="deadline-scheduler")
    log.info("[deadline-scheduler] task spawned")


async def stop_scheduler() -> None:
    global _TASK
    _STOP.set()
    if _TASK:
        try:
            await asyncio.wait_for(_TASK, timeout=5.0)
        except TimeoutError:
            _TASK.cancel()
        _TASK = None
