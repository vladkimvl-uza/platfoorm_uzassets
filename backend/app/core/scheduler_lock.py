"""Postgres advisory-lock helper for single-instance schedulers.

When uvicorn runs with --workers N (we use 4), each worker calls lifespan
and starts its own asyncio scheduler task. That causes scheduled jobs to
fire N times (e.g. broadcast delivered 4 copies, TLS certbot called 4x).

This helper acquires a session-scoped Postgres advisory lock at scheduler
startup. Only the first worker to acquire it actually runs the scheduler;
the others observe the lock failure and exit their start function.

The advisory lock is held for the lifetime of the underlying psycopg
connection — so as long as the holding worker stays alive, others can't
take over. When that worker dies, the lock is released automatically and
the next call to start_scheduler() (on next lifespan or via supervisor
restart) picks it up.

Each scheduler picks a unique integer lock_id (pick a number, document it
in LOCK_IDS below, never re-use).

Usage in scheduler start function:

    from app.core.scheduler_lock import try_acquire_scheduler_lock

    held = await try_acquire_scheduler_lock("broadcasts")
    if not held:
        log.info("[broadcast_scheduler] another worker holds the lock — skipping")
        return
    # ... start asyncio task ...
"""
from __future__ import annotations

import logging

from sqlalchemy import text

log = logging.getLogger(__name__)


# Each named lock gets a stable int64 lock_id (Postgres advisory locks take
# bigint = signed int64, range ±2^63). Pick a fixed app-namespace prefix to
# avoid collisions with other apps sharing the database, but keep the value
# inside int64. Document new entries here so they don't collide.
LOCK_IDS: dict[str, int] = {
    "broadcasts":     0x457A5_00000001,  # broadcast_scheduler (uzAssets prefix)
    "tls_renewal":    0x457A5_00000002,  # tls_scheduler
}


_held_connections: dict[str, object] = {}  # name -> raw connection holding the lock


async def try_acquire_scheduler_lock(name: str) -> bool:
    """Attempt to acquire a session-scoped advisory lock for `name`.

    Returns True if THIS process now owns the lock (and should run the scheduler).
    Returns False if another process already holds it (skip the scheduler).

    The held connection is parked in `_held_connections[name]` to keep the
    lock alive for the lifetime of the process. Do not close it manually.
    """
    if name not in LOCK_IDS:
        raise ValueError(f"Unknown scheduler lock name: {name!r}. Add to LOCK_IDS.")
    if name in _held_connections:
        # Already held by this process — idempotent.
        return True

    lock_id = LOCK_IDS[name]

    # Need a *dedicated* connection that stays open. Reusing get_db() session
    # would release the lock as soon as the request finishes. We grab one
    # from the engine pool and intentionally never release it.
    from app.database import engine

    conn = await engine.connect()
    try:
        result = await conn.execute(text("SELECT pg_try_advisory_lock(:k)").bindparams(k=lock_id))
        ok = bool(result.scalar())
    except Exception as e:
        await conn.close()
        log.warning("[scheduler_lock:%s] acquire failed: %s", name, e)
        return False

    if not ok:
        # Another worker holds it — release the connection (the lock isn't ours).
        await conn.close()
        return False

    # We hold the lock. Park the connection so the lock stays alive.
    _held_connections[name] = conn
    log.info("[scheduler_lock:%s] acquired (lock_id=0x%x)", name, lock_id)
    return True


async def release_scheduler_lock(name: str) -> None:
    """Explicit release — used during graceful shutdown. Optional; if not called,
    Postgres releases automatically when the connection drops."""
    conn = _held_connections.pop(name, None)
    if conn is None:
        return
    try:
        lock_id = LOCK_IDS[name]
        await conn.execute(text("SELECT pg_advisory_unlock(:k)").bindparams(k=lock_id))
        await conn.close()
        log.info("[scheduler_lock:%s] released", name)
    except Exception as e:
        log.warning("[scheduler_lock:%s] release failed: %s", name, e)
