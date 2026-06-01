"""Health check and liveness probes.

Three endpoints:
  GET /health            — process liveness, no IO. Used by docker HEALTHCHECK.
  GET /health/ready      — readiness: DB + outbox worker + bot. Used by LB.
  GET /health/components — detail of each subsystem (admin-friendly).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.database import get_db
from app.models.mfa import OutboxStatus, TelegramOutbox

router = APIRouter(prefix="/health", tags=["health"])

# How fresh "fresh" is. If nothing was delivered/attempted in this window AND
# there's no pending backlog, we still report healthy (idle bot is fine).
OUTBOX_FRESH_WINDOW_MIN = 30
# Threshold above which a pending backlog is suspicious.
OUTBOX_BACKLOG_WARN = 25
OUTBOX_BACKLOG_FAIL = 100
# How long a single message is allowed to wait before we call the worker stuck.
OUTBOX_STUCK_MIN = 15


@router.get("")
async def health():
    """Liveness — always returns 200 if the app is running."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
async def ready(request: Request, db: AsyncSession = Depends(get_db)):
    """Readiness — fails (503) if any critical subsystem is degraded.

    2026-05-26: also honours app.state.healthy = False, set by audit_chain
    verifier on tamper detection (when AUDIT_CHAIN_HALT_ON_TAMPER=true).
    """
    # Forensic halt: tamper detected → don't serve traffic.
    if getattr(request.app.state, "healthy", True) is False:
        reason = getattr(request.app.state, "healthy_reason", "unknown")
        raise HTTPException(
            status_code=503,
            detail={"failing": ["app_state"], "reason": reason},
        )
    components = await _check_components(db)
    bad = [k for k, v in components.items() if v.get("status") == "fail"]
    if bad:
        raise HTTPException(status_code=503, detail={"failing": bad, "components": components})
    return {"status": "ready", "components": components}


@router.get("/components")
async def components(db: AsyncSession = Depends(get_db)):
    """Detailed per-subsystem status — never 503s, always returns the full report."""
    return {
        "status": "ok",
        "version": __version__,
        "components": await _check_components(db),
    }


async def _check_components(db: AsyncSession) -> dict[str, dict[str, Any]]:
    return {
        "database":  await _check_db(db),
        "outbox":    await _check_outbox(db),
        "bot":       await _check_bot(db),
    }


async def _check_db(db: AsyncSession) -> dict[str, Any]:
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "fail", "error": str(e)[:200]}


async def _check_outbox(db: AsyncSession) -> dict[str, Any]:
    """Worker is healthy if EITHER recent activity OR no backlog at all."""
    try:
        now = datetime.now(UTC)
        fresh_cutoff = now - timedelta(minutes=OUTBOX_FRESH_WINDOW_MIN)
        stuck_cutoff = now - timedelta(minutes=OUTBOX_STUCK_MIN)

        pending_total = (await db.execute(
            select(func.count()).select_from(TelegramOutbox)
            .where(TelegramOutbox.status == OutboxStatus.PENDING)
        )).scalar() or 0

        pending_stuck = (await db.execute(
            select(func.count()).select_from(TelegramOutbox)
            .where(
                TelegramOutbox.status == OutboxStatus.PENDING,
                TelegramOutbox.created_at < stuck_cutoff,
            )
        )).scalar() or 0

        last_delivered = (await db.execute(
            select(func.max(TelegramOutbox.delivered_at))
        )).scalar()

        recent_activity = last_delivered is not None and last_delivered > fresh_cutoff

        # Decision tree:
        #  - stuck items (older than 15 min still PENDING) → worker not running
        #  - large backlog (100+) → degraded
        #  - moderate backlog (25-100) with no recent activity → warn
        #  - otherwise → ok
        if pending_stuck > 0:
            status = "fail"
            note = f"{pending_stuck} item(s) PENDING > {OUTBOX_STUCK_MIN}m — worker likely down"
        elif pending_total >= OUTBOX_BACKLOG_FAIL:
            status = "fail"
            note = f"backlog {pending_total} >= {OUTBOX_BACKLOG_FAIL}"
        elif pending_total >= OUTBOX_BACKLOG_WARN and not recent_activity:
            status = "warn"
            note = f"backlog {pending_total} and no delivery in {OUTBOX_FRESH_WINDOW_MIN}m"
        else:
            status = "ok"
            note = None

        return {
            "status": status,
            "pending": pending_total,
            "pending_stuck": pending_stuck,
            "last_delivered_at": last_delivered.isoformat() if last_delivered else None,
            **({"note": note} if note else {}),
        }
    except Exception as e:
        return {"status": "fail", "error": str(e)[:200]}


async def _check_bot(db: AsyncSession) -> dict[str, Any]:
    """Bot is healthy if at least one outbox row was attempted recently OR
    there have been no items to attempt (truly idle deployment).

    We can't directly ping the bot process (no shared health endpoint).
    The closest signal we have is `attempted_at` on outbox rows — the
    worker sets this whenever it tries to deliver. If items exist but
    nothing has been attempted for a while, the bot worker is hung."""
    try:
        now = datetime.now(UTC)
        fresh_cutoff = now - timedelta(minutes=OUTBOX_FRESH_WINDOW_MIN)

        last_attempted = (await db.execute(
            select(func.max(TelegramOutbox.attempted_at))
        )).scalar()

        pending_total = (await db.execute(
            select(func.count()).select_from(TelegramOutbox)
            .where(TelegramOutbox.status == OutboxStatus.PENDING)
        )).scalar() or 0

        # If items are pending and worker hasn't touched them in 15 min → fail.
        if pending_total > 0 and (
            last_attempted is None or last_attempted < now - timedelta(minutes=OUTBOX_STUCK_MIN)
        ):
            return {
                "status": "fail",
                "last_attempted_at": last_attempted.isoformat() if last_attempted else None,
                "pending": pending_total,
                "note": "items pending but no recent attempt — worker stalled",
            }
        # If no recent attempts but no pending items either → idle but ok.
        if last_attempted is None or last_attempted < fresh_cutoff:
            return {
                "status": "ok",
                "last_attempted_at": last_attempted.isoformat() if last_attempted else None,
                "pending": pending_total,
                "note": "idle (no recent activity, no backlog)" if pending_total == 0 else None,
            }
        return {
            "status": "ok",
            "last_attempted_at": last_attempted.isoformat(),
            "pending": pending_total,
        }
    except Exception as e:
        return {"status": "fail", "error": str(e)[:200]}
