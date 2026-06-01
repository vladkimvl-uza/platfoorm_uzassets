"""Webhook delivery worker (Pack 12.1).

In-process asyncio task. Polls every POLL_INTERVAL_SECONDS for pending deliveries
whose `scheduled_at <= now()`, picks them up in batches with FOR UPDATE SKIP LOCKED
(future-safe for multi-instance), signs payload with the subscription's secret,
delivers via httpx, and updates the row state machine.

Backoff: see _BACKOFF_TABLE in webhook_service.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.webhook import (
    WD_EXHAUSTED,
    WD_PENDING,
    WD_SUCCEEDED,
    WebhookDelivery,
    WebhookSubscription,
)
from app.services.webhook_service import compute_next_retry, sign_payload

logger = logging.getLogger(__name__)


POLL_INTERVAL_SECONDS = 5
BATCH_SIZE            = 20
RESPONSE_BODY_CAP     = 4 * 1024     # truncate response body to 4 KB in storage
USER_AGENT            = "UzAssets-Webhooks/12.1"


# Module-level flag — set by `start_worker` and read by the loop to allow shutdown.
_running = False
_task: Optional[asyncio.Task] = None


# ════════════════════════════════════════════════════════════
#   Worker lifecycle
# ════════════════════════════════════════════════════════════

def start_worker() -> None:
    """Spawn the worker task. Idempotent — calling twice does nothing."""
    global _running, _task
    if _running:
        return
    _running = True
    loop = asyncio.get_event_loop()
    _task = loop.create_task(_run_forever(), name="webhook-worker")
    logger.info("Webhook worker started")


async def stop_worker() -> None:
    """Signal the loop to exit, then wait for it. Call from shutdown hook."""
    global _running, _task
    if not _running:
        return
    _running = False
    if _task is not None:
        try:
            await asyncio.wait_for(_task, timeout=15)
        except TimeoutError:
            _task.cancel()
        _task = None
    logger.info("Webhook worker stopped")


async def _run_forever() -> None:
    while _running:
        try:
            await _drain_once()
        except Exception:
            logger.exception("Webhook worker iteration crashed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# ════════════════════════════════════════════════════════════
#   Drain: one polling iteration
# ════════════════════════════════════════════════════════════

async def _drain_once() -> None:
    """Find up to BATCH_SIZE pending deliveries that are due, send them."""
    async with AsyncSessionLocal() as session:
        # SKIP LOCKED → safe for multi-instance: each worker grabs distinct rows
        result = await session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == WD_PENDING)
            .where(WebhookDelivery.scheduled_at <= datetime.now(UTC))
            .order_by(WebhookDelivery.scheduled_at)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True),
        )
        rows = result.scalars().all()
        if not rows:
            return

        # Pre-load subscriptions in one go
        sub_ids = list({r.subscription_id for r in rows})
        subs_by_id = {
            s.id: s for s in (await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.id.in_(sub_ids)),
            )).scalars().all()
        }

        async with httpx.AsyncClient() as client:
            for d in rows:
                sub = subs_by_id.get(d.subscription_id)
                if sub is None or not sub.is_active:
                    # Subscription was deleted or paused; mark cancelled-ish (exhausted)
                    d.status = WD_EXHAUSTED
                    d.completed_at = datetime.now(UTC)
                    d.error_message = "Subscription unavailable at delivery time"
                    continue

                await _attempt_delivery(client, session, d, sub)

        await session.commit()


async def _attempt_delivery(
    client: httpx.AsyncClient, session: AsyncSession,
    d: WebhookDelivery, sub: WebhookSubscription,
) -> None:
    """Single attempt. Mutates `d` and the subscription counters."""
    d.attempt_number = (d.attempt_number or 0) + 1
    d.attempted_at = datetime.now(UTC)

    body_bytes = json.dumps(d.event_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ts = int(time.time())
    sig = sign_payload(sub.secret_plain, body_bytes, ts)

    headers = {
        "Content-Type":          "application/json; charset=utf-8",
        "User-Agent":            USER_AGENT,
        "X-UzAssets-Event":      d.event_code,
        "X-UzAssets-Delivery":   str(d.id),
        "X-UzAssets-Timestamp":  str(ts),
        "X-UzAssets-Signature":  f"sha256={sig}",
        "X-UzAssets-Attempt":    str(d.attempt_number),
    }
    if sub.custom_headers:
        for k, v in sub.custom_headers.items():
            # Block override of canonical headers
            if not k.lower().startswith(("x-uzassets-", "content-type", "user-agent")):
                headers[k] = str(v)

    d.signature      = sig
    d.timestamp_sent = ts

    started = time.monotonic()
    try:
        resp = await client.post(
            sub.target_url,
            content=body_bytes,
            headers=headers,
            timeout=sub.timeout_seconds or 10,
            follow_redirects=False,
            verify=bool(sub.verify_ssl),
        )
        d.duration_ms = int((time.monotonic() - started) * 1000)
        d.http_status = resp.status_code
        d.response_body_snippet = (resp.text or "")[:RESPONSE_BODY_CAP]
        d.response_headers_snippet = _pick_headers(resp.headers)
        success = 200 <= resp.status_code < 300
        if not success:
            d.error_message = f"Non-2xx response: {resp.status_code}"
    except httpx.TimeoutException as e:
        d.duration_ms = int((time.monotonic() - started) * 1000)
        d.error_message = f"Timeout after {sub.timeout_seconds}s: {type(e).__name__}"
        success = False
    except httpx.RequestError as e:
        d.duration_ms = int((time.monotonic() - started) * 1000)
        d.error_message = f"{type(e).__name__}: {str(e)[:500]}"
        success = False
    except Exception as e:
        d.duration_ms = int((time.monotonic() - started) * 1000)
        d.error_message = f"Unexpected: {type(e).__name__}: {str(e)[:500]}"
        success = False

    now = datetime.now(UTC)
    sub.total_deliveries = (sub.total_deliveries or 0) + 1

    if success:
        d.status = WD_SUCCEEDED
        d.completed_at = now
        d.next_retry_at = None
        sub.last_success_at = now
        sub.consecutive_failures = 0
    else:
        sub.total_failures = (sub.total_failures or 0) + 1
        sub.last_failure_at = now
        sub.consecutive_failures = (sub.consecutive_failures or 0) + 1

        if d.attempt_number >= (sub.max_attempts or 5):
            d.status = WD_EXHAUSTED
            d.completed_at = now
        else:
            delay = compute_next_retry(d.attempt_number)
            if delay is None:
                d.status = WD_EXHAUSTED
                d.completed_at = now
            else:
                d.scheduled_at = now + delay
                d.next_retry_at = d.scheduled_at
                d.status = WD_PENDING  # re-queued

        # Auto-disable subscription if too many consecutive failures
        if sub.consecutive_failures >= 50:
            sub.is_active = False
            sub.disabled_at = now
            sub.disabled_reason = f"Auto-disabled after {sub.consecutive_failures} consecutive failures"
            logger.warning(
                f"Auto-disabled subscription {sub.id} ({sub.name}) "
                f"after {sub.consecutive_failures} failures",
            )


def _pick_headers(headers: httpx.Headers) -> dict[str, str]:
    """Return a small, useful subset of response headers (avoid storing huge headers blobs)."""
    keep = {
        "content-type", "x-request-id", "x-correlation-id",
        "retry-after", "server", "via", "x-trace-id",
    }
    out = {}
    for k, v in headers.items():
        if k.lower() in keep:
            out[k] = str(v)[:200]
    return out
