"""In-process scheduler for admin broadcasts (Pack 11.2).

A single asyncio task that runs in the FastAPI lifespan. Every 60 s it
scans `admin_broadcast_template` for rows whose `next_run_at <= now()` and
dispatches each one. Suitable for a single backend container.

For multi-instance deployments, switch to APScheduler with a DB job store
or move to Celery beat.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select

from app.models.admin_broadcast import AdminBroadcastTemplate
from app.services.admin_broadcast_service import (
    compute_next_run_at, dispatch_template,
)


log = logging.getLogger(__name__)

_TASK: Optional[asyncio.Task] = None
_STOP = asyncio.Event()
SCAN_INTERVAL_SEC = 60


async def _tick() -> int:
    """One scan pass. Returns number of templates dispatched."""
    from app.database import AsyncSessionLocal  # local import to avoid circular

    fired = 0
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Templates ready to fire
        rows = (await db.execute(
            select(AdminBroadcastTemplate).where(and_(
                AdminBroadcastTemplate.is_active.is_(True),
                AdminBroadcastTemplate.next_run_at.is_not(None),
                AdminBroadcastTemplate.next_run_at <= now,
            )),
        )).scalars().all()

        for tpl in rows:
            try:
                # Re-check next_run_at right before dispatch (avoid races)
                if tpl.next_run_at and tpl.next_run_at > now:
                    continue
                if tpl.schedule_end_at and now > tpl.schedule_end_at:
                    tpl.is_active = False
                    tpl.next_run_at = None
                    await db.commit()
                    continue

                log.info(f"[broadcast-scheduler] firing template {tpl.id} ({tpl.name})")
                await dispatch_template(db, template=tpl, trigger="schedule")
                fired += 1
            except Exception as e:  # noqa: BLE001
                log.exception(f"[broadcast-scheduler] dispatch failed for {tpl.id}: {e}")
                # Backoff: defer next_run_at by 15 min so we don't spin
                try:
                    from datetime import timedelta
                    tpl.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=15)
                    await db.commit()
                except Exception:
                    pass
    return fired


async def _run_loop() -> None:
    log.info("[broadcast-scheduler] loop started")
    # Initial settling pause
    try:
        await asyncio.wait_for(_STOP.wait(), timeout=10.0)
        return
    except asyncio.TimeoutError:
        pass

    while not _STOP.is_set():
        try:
            await _tick()
        except Exception as e:  # noqa: BLE001
            log.exception(f"[broadcast-scheduler] tick error: {e}")
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SCAN_INTERVAL_SEC)
        except asyncio.TimeoutError:
            continue
    log.info("[broadcast-scheduler] loop stopped")


def start_scheduler() -> None:
    """Spawn the background task. Idempotent."""
    global _TASK
    if _TASK and not _TASK.done():
        return
    _STOP.clear()
    loop = asyncio.get_event_loop()
    _TASK = loop.create_task(_run_loop(), name="broadcast-scheduler")
    log.info("[broadcast-scheduler] task spawned")


async def stop_scheduler() -> None:
    """Signal the task to exit and wait for it."""
    global _TASK
    _STOP.set()
    if _TASK:
        try:
            await asyncio.wait_for(_TASK, timeout=5.0)
        except asyncio.TimeoutError:
            _TASK.cancel()
        _TASK = None
