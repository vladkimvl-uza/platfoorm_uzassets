"""Webhook service (Pack 12.1).

Central entry points:
  emit_event(db, code, payload, correlation_id=None)
      → fan out an event to all matching subscriptions; queues WebhookDelivery rows
  create_subscription(...)
      → generates a signing secret and stores it
  sign_payload(secret, body, timestamp)
      → HMAC-SHA256, returns hex digest

Worker (webhook_worker.py) pulls pending deliveries, signs them, sends via httpx,
and updates the row state machine with retries / exponential backoff.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import (
    WD_PENDING,
    WebhookDelivery,
    WebhookSubscription,
)
from app.services.webhook_events import is_registered, matches_subscription

logger = logging.getLogger(__name__)


# Module-scoped HMAC server-side key used for hashing the *user-provided*
# signing secret at-rest, so a DB dump alone doesn't expose plaintext signing
# secrets. The signing itself uses secret_plain (the user secret), NOT this key.
# Loaded from env (UZA_WEBHOOK_HMAC_SECRET ≥ 32 bytes) or from audit HMAC file.
def _load_webhook_server_hmac() -> bytes:
    env_val = os.getenv("UZA_WEBHOOK_HMAC_SECRET", "")
    if env_val and len(env_val) >= 32:
        return env_val.encode("utf-8")
    secret_path = os.environ.get("AUDIT_HMAC_SECRET_PATH", "/app/keys/audit_hmac.key")
    if os.path.exists(secret_path):
        with open(secret_path, "rb") as f:
            secret = f.read().strip()
        if len(secret) >= 32:
            return secret
    raise RuntimeError(
        "Webhook HMAC secret missing. Set UZA_WEBHOOK_HMAC_SECRET (≥32 bytes) "
        f"or mount a key file at {secret_path}."
    )

_SERVER_HMAC = _load_webhook_server_hmac()


# ════════════════════════════════════════════════════════════
#   Signing
# ════════════════════════════════════════════════════════════

def generate_signing_secret() -> tuple[str, str, str]:
    """Return (plaintext_secret, secret_hint, server_hash).

    plaintext_secret = the secret stored AND used to sign deliveries.
    secret_hint      = last 4 chars (for display in UI lists, never the secret itself).
    server_hash      = HMAC of the secret with the server-side key (verification only).
    """
    plaintext = "whsec_" + secrets.token_urlsafe(32)
    hint = "…" + plaintext[-4:]
    server_hash = hmac.new(_SERVER_HMAC, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()
    return plaintext, hint, server_hash


def sign_payload(secret: str, body: bytes, timestamp_unix: int) -> str:
    """HMAC-SHA256 over `timestamp.body` — Stripe-style canonical form."""
    msg = f"{timestamp_unix}.".encode() + body
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


# ════════════════════════════════════════════════════════════
#   Subscription CRUD helpers
# ════════════════════════════════════════════════════════════

async def create_subscription(
    db: AsyncSession, *,
    service_account_id: UUID,
    created_by_id: UUID,
    name: str, description: Optional[str],
    target_url: str,
    events: list[str],
    verify_ssl: bool,
    custom_headers: Optional[dict],
    max_attempts: int,
    timeout_seconds: int,
) -> tuple[WebhookSubscription, str]:
    plaintext, hint, server_hash = generate_signing_secret()
    now = datetime.now(UTC)
    sub = WebhookSubscription(
        created_at=now, updated_at=now,
        service_account_id=service_account_id,
        created_by_id=created_by_id,
        name=name, description=description,
        target_url=target_url,
        secret_hint=hint, secret_hash=server_hash, secret_plain=plaintext,
        verify_ssl=verify_ssl,
        custom_headers=custom_headers,
        events=list(events or []),
        is_active=True,
        max_attempts=max_attempts,
        timeout_seconds=timeout_seconds,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub, plaintext


# ════════════════════════════════════════════════════════════
#   emit_event — fan out to matching subscriptions
# ════════════════════════════════════════════════════════════

async def emit_event(
    db: AsyncSession,
    code: str,
    payload: dict[str, Any],
    *,
    correlation_id: Optional[UUID] = None,
    commit: bool = True,
) -> int:
    """Queue WebhookDelivery rows for every active subscription that matches `code`.

    Returns the number of queued deliveries.

    Caller is responsible for the transaction. If commit=False, caller commits.
    """
    if not is_registered(code):
        # Don't crash callers — log + skip. Event registry should evolve.
        logger.warning(f"emit_event called with unregistered code: {code}")
        return 0

    subs = (await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.is_active.is_(True)),
    )).scalars().all()

    queued = 0
    now = datetime.now(UTC)
    for sub in subs:
        if not matches_subscription(code, sub.events or []):
            continue
        d = WebhookDelivery(
            created_at=now,
            subscription_id=sub.id,
            event_code=code,
            event_payload=payload,
            correlation_id=correlation_id,
            status=WD_PENDING,
            attempt_number=0,
            scheduled_at=now,  # deliver immediately
        )
        db.add(d)
        queued += 1

    if commit:
        await db.commit()
    return queued


def emit_event_fire_and_forget(
    db_session_factory,
    code: str,
    payload: dict[str, Any],
    *,
    correlation_id: Optional[UUID] = None,
) -> None:
    """Spawn an asyncio task to emit an event without blocking the caller.

    Use from non-async paths or where the caller doesn't want to await.
    Opens its own session via the supplied factory (e.g. AsyncSessionLocal).
    """
    async def _run():
        try:
            async with db_session_factory() as session:
                await emit_event(session, code, payload, correlation_id=correlation_id)
        except Exception:
            logger.exception(f"Failed to emit event {code}")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        # No running loop — caller is sync. Skip emission rather than crash.
        logger.warning(f"emit_event_fire_and_forget called outside event loop; skipping {code}")


# ════════════════════════════════════════════════════════════
#   Retry scheduling
# ════════════════════════════════════════════════════════════

# Exponential backoff in seconds for attempts 1..5
_BACKOFF_TABLE = [
    0,          # attempt 1: scheduled_at = now (no delay)
    60,         # attempt 2: 1 minute
    5 * 60,     # attempt 3: 5 minutes
    30 * 60,    # attempt 4: 30 minutes
    2 * 60 * 60,  # attempt 5: 2 hours
]


def compute_next_retry(attempt_number: int) -> Optional[timedelta]:
    """Return the delay before the *next* attempt, or None if no more retries.

    attempt_number is the attempt that just failed (1-indexed).
    """
    next_attempt_index = attempt_number  # index for the upcoming attempt
    if next_attempt_index >= len(_BACKOFF_TABLE):
        return None
    return timedelta(seconds=_BACKOFF_TABLE[next_attempt_index])


# ════════════════════════════════════════════════════════════
#   Replay / Test helpers
# ════════════════════════════════════════════════════════════

async def enqueue_replay(
    db: AsyncSession, original: WebhookDelivery,
) -> WebhookDelivery:
    """Create a new delivery row that re-sends an existing payload."""
    sub = await db.get(WebhookSubscription, original.subscription_id)
    if sub is None or not sub.is_active:
        raise ValueError("Subscription not active or missing")

    now = datetime.now(UTC)
    new = WebhookDelivery(
        created_at=now,
        subscription_id=original.subscription_id,
        event_code=original.event_code,
        event_payload=original.event_payload,
        correlation_id=original.correlation_id,
        status=WD_PENDING,
        attempt_number=0,
        scheduled_at=now,
        is_replay=True,
        replay_of_id=original.id,
    )
    db.add(new)
    await db.commit()
    await db.refresh(new)
    return new


async def enqueue_test(
    db: AsyncSession, sub: WebhookSubscription, payload: Optional[dict], triggered_by_id: UUID,
) -> WebhookDelivery:
    """Send a synthetic webhook.test event to a specific subscription."""
    body = payload or {
        "subscription_id": str(sub.id),
        "triggered_by_id": str(triggered_by_id),
        "note": "Synthetic test event — proves endpoint connectivity",
    }
    now = datetime.now(UTC)
    d = WebhookDelivery(
        created_at=now,
        subscription_id=sub.id,
        event_code="webhook.test",
        event_payload=body,
        status=WD_PENDING,
        attempt_number=0,
        scheduled_at=now,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d
