"""In-process автозахват срезов прогресса (Контрольная вышка).

Раз в час проверяет: если за сегодня по текущему году ещё нет снимка —
фиксирует один (scope='auto'). Так отслеживание идёт само, без ручной
кнопки; первый запуск создаёт базовый срез автоматически.

Single-container: один asyncio-таск в lifespan + advisory-lock (как
broadcast_scheduler). Для multi-instance — advisory-lock не даёт дублей.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import func, select

from app.models.progress_snapshot import ProgressSnapshot

log = logging.getLogger(__name__)

_TASK: Optional[asyncio.Task] = None
_STOP = asyncio.Event()
SCAN_INTERVAL_SEC = 3600  # проверка раз в час


async def _tick() -> int:
    """Один проход: если за сегодня снимка нет — захватить. Возвращает 0/1."""
    from app.api.routes.monitoring import capture_snapshot
    from app.database import AsyncSessionLocal

    now = datetime.now(UTC)
    today = now.date()
    year = now.year

    async with AsyncSessionLocal() as db:
        last = (await db.execute(
            select(func.max(ProgressSnapshot.captured_at))
            .where(ProgressSnapshot.year == year),
        )).scalar()
        if last is not None and last.date() == today:
            return 0  # уже есть срез за сегодня (авто или ручной)

        snap = await capture_snapshot(
            db, year=year,
            label=f"Авто · {today.strftime('%d.%m.%Y')}",
            captured_by=None, scope="auto",
        )
        log.info("[snapshot-scheduler] auto-captured %s for %s", snap.id, year)
        return 1


async def _run_loop() -> None:
    log.info("[snapshot-scheduler] loop started")
    # Небольшая пауза на старте (дать приложению подняться)
    try:
        await asyncio.wait_for(_STOP.wait(), timeout=30.0)
        return
    except TimeoutError:
        pass

    while not _STOP.is_set():
        try:
            await _tick()
        except Exception as e:
            log.exception("[snapshot-scheduler] tick error: %s", e)
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SCAN_INTERVAL_SEC)
        except TimeoutError:
            continue
    log.info("[snapshot-scheduler] loop stopped")


def start_scheduler() -> None:
    """Запустить фоновый таск автозахвата. Идемпотентно + advisory-lock."""
    global _TASK
    if _TASK and not _TASK.done():
        return
    _STOP.clear()
    loop = asyncio.get_event_loop()

    async def _start_with_lock() -> None:
        from app.core.scheduler_lock import try_acquire_scheduler_lock
        held = await try_acquire_scheduler_lock("snapshots")
        if not held:
            log.info("[snapshot-scheduler] another worker holds the lock — idle")
            return
        await _run_loop()

    _TASK = loop.create_task(_start_with_lock(), name="snapshot-scheduler")
    log.info("[snapshot-scheduler] task spawned")


async def stop_scheduler() -> None:
    global _TASK
    _STOP.set()
    if _TASK:
        try:
            await asyncio.wait_for(_TASK, timeout=5.0)
        except TimeoutError:
            _TASK.cancel()
        _TASK = None
