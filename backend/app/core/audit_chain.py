"""Audit-log integrity via HMAC chain.

For each new audit entry:
    prev_hash  = entry_hash of the previous row (or 64 zeros for the first)
    entry_hash = HMAC-SHA256(secret, prev_hash || canonical_entry_json)

Tampering with any past row will break the chain at that point and beyond.
A `verify_chain()` routine walks all rows and reports the first mismatch.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog

log = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64


def _secret() -> bytes:
    s = settings.read_audit_hmac_secret()
    if not s:
        raise RuntimeError(
            "Audit HMAC secret missing at "
            f"{settings.AUDIT_HMAC_SECRET_PATH} — run scripts/generate-keys.sh"
        )
    return s


def canonicalize(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def compute_entry_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    """Compute HMAC-SHA256 over prev_hash || canonical(payload). Hex digest.

    Recipe is identical to `app.services.audit_service._compute_hash` so the
    two audit writers produce a single coherent chain that verify_chain can
    walk linearly.
    """
    secret = _secret()
    msg = (prev_hash or "").encode() + canonicalize(payload)
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _normalize_blob(v):
    """Canonical form for diff/payload (mutable dicts/lists) in the hash.
    None → None; primitives → unchanged; containers → sorted-keys JSON string.
    Ensures verifier and writer agree even when JSON serialization order
    drifts between Python versions.
    """
    if v is None:
        return None
    if isinstance(v, str | int | float | bool):
        return v
    return json.dumps(v, sort_keys=True, separators=(",", ":"), default=str)


def build_chain_body(
    *,
    actor_id,
    actor_email,
    action,
    module,
    entity_type,
    entity_id,
    http_method,
    http_path,
    http_status,
    diff,
    payload,
    ip_address,
    user_agent,
    notes,
) -> dict:
    """Single source of truth for the HMAC payload schema. Used by both
    writers (append_audit_entry, audit_service.write_event) AND the verifier
    (verify_chain). Adding/removing fields here is a chain-break event —
    rebuild is required after any change.

    All metadata is included so that DB-level tampering with diff/payload/
    ip_address/user_agent/notes is detectable.
    """
    return {
        "actor_id":    str(actor_id) if actor_id else None,
        "actor_email": actor_email,
        "action":      action,
        "module":      module,
        "entity_type": entity_type,
        "entity_id":   entity_id,
        "http_method": http_method,
        "http_path":   http_path,
        "http_status": http_status,
        "diff":        _normalize_blob(diff),
        "payload":     _normalize_blob(payload),
        "ip_address":  ip_address,
        "user_agent":  (user_agent or "")[:512] or None if user_agent is not None else None,
        "notes":       notes,
    }


async def append_audit_entry(
    db: AsyncSession,
    *,
    actor_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    diff: Optional[dict] = None,
    payload: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    notes: Optional[str] = None,
    is_critical: bool = False,
) -> AuditLog:
    """Append a new entry to `audit_log` with a valid HMAC chain link.

    Concurrency: acquires a row-level exclusive lock on the audit_chain_lock
    sentinel row (id=1). This serializes all audit writers across processes
    and connections reliably — pg_advisory_xact_lock empirically allowed
    interleaving under load in our setup, while SELECT FOR UPDATE on a
    real row is a well-defined PG primitive.

    Defense in depth: UNIQUE index uq_audit_log_prev_hash catches any
    race that bypasses the lock with IntegrityError.
    """
    await db.execute(text("SELECT id FROM audit_chain_lock WHERE id = 1 FOR UPDATE"))

    # Chain tip = entry_hash that no other row references as prev_hash.
    # Using created_at DESC is unsafe — concurrent tx timestamps can be
    # reversed relative to insert order. NOT EXISTS via UNIQUE index on
    # prev_hash is O(log N).
    result = await db.execute(text("""
        SELECT al.entry_hash
        FROM audit_log al
        WHERE NOT EXISTS (
            SELECT 1 FROM audit_log al2
            WHERE al2.prev_hash = al.entry_hash
        )
        LIMIT 1
    """))
    prev_hash = result.scalar_one_or_none() or GENESIS_HASH

    body = build_chain_body(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        module=None,
        entity_type=entity_type,
        entity_id=entity_id,
        http_method=None,
        http_path=None,
        http_status=None,
        diff=diff,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
        notes=notes,
    )
    entry_hash = compute_entry_hash(prev_hash, body)

    entry = AuditLog(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        diff=diff,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
        notes=notes,
        is_critical=is_critical,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(entry)
    await db.flush()
    return entry


async def verify_chain(db: AsyncSession, *, limit: int | None = None) -> dict:
    """Walk the audit chain by following prev_hash → entry_hash pointers
    instead of relying on created_at ordering.

    Why: created_at = transaction-start time in Postgres. Under serialized
    inserts (sentinel lock), the SECOND writer's transaction begins AFTER
    the first one commits — but its `now()` can still land within
    microseconds of the first writer's `now()`, occasionally even
    BEFORE it (clock precision / wall-clock vs transaction snapshot).
    Ordering by created_at is fundamentally unsafe; chain integrity must
    follow the cryptographic links, not the timestamps.

    Algorithm:
      1. Build dict {prev_hash: row} since prev_hash is UNIQUE
      2. Start at GENESIS_HASH → find first row with prev_hash = GENESIS
      3. Verify its hash, follow row.entry_hash as next prev_hash
      4. Continue until no successor exists (= chain head)
      5. Report break if a row is reachable but its entry_hash mismatches
    """
    stmt = select(AuditLog)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    total = len(rows)

    # Build the by-prev_hash index. UNIQUE constraint guarantees no collisions.
    by_prev: dict[str, AuditLog] = {}
    for r in rows:
        # Defensive: if duplicate prev_hash slips through (shouldn't happen
        # post unique-index), flag immediately.
        if r.prev_hash in by_prev:
            return {
                "checked": 0, "ok": False,
                "broken_at": str(r.id),
                "reason": f"duplicate_prev_hash:{r.prev_hash[:16]}",
            }
        by_prev[r.prev_hash] = r

    expected_prev = GENESIS_HASH
    checked = 0
    while expected_prev in by_prev:
        row = by_prev[expected_prev]
        body = build_chain_body(
            actor_id=row.actor_id,
            actor_email=row.actor_email,
            action=row.action,
            module=row.module,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            http_method=row.http_method,
            http_path=row.http_path,
            http_status=row.http_status,
            diff=row.diff,
            payload=row.payload,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            notes=row.notes,
        )
        expected_entry = compute_entry_hash(expected_prev, body)
        if row.entry_hash != expected_entry:
            return {
                "checked": checked + 1, "ok": False,
                "broken_at": str(row.id),
                "reason": "entry_hash_mismatch",
            }
        checked += 1
        expected_prev = row.entry_hash
        if limit and checked >= limit:
            break

    # If we couldn't walk all rows, some are orphaned (prev_hash references
    # a non-existent ancestor).
    if checked < total and not limit:
        return {
            "checked": checked, "ok": False,
            "broken_at": None,
            "reason": f"orphan_rows: walked {checked} of {total}",
        }

    return {"checked": checked, "ok": True, "broken_at": None}
