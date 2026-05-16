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

from sqlalchemy import select
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
    """Compute HMAC-SHA256 over prev_hash || canonical(payload). Hex digest."""
    secret = _secret()
    mac = hmac.new(secret, prev_hash.encode("ascii"), hashlib.sha256)
    mac.update(b"|")
    mac.update(canonicalize(payload))
    return mac.hexdigest()


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
) -> AuditLog:
    """Append a new entry to `audit_log` with a valid HMAC chain link.

    Concurrency note: under high write rates, two transactions may compute
    the same prev_hash. The unique index on `entry_hash` will fail one and
    the caller must retry. For single-process backends, this is rare; for
    multi-process backends, wrap calls in advisory locks if needed.
    """
    # Fetch the most recent entry's hash (chain head)
    result = await db.execute(
        select(AuditLog.entry_hash)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )
    prev_hash = result.scalar_one_or_none() or GENESIS_HASH

    body = {
        "actor_id":    str(actor_id) if actor_id else None,
        "actor_email": actor_email,
        "action":      action,
        "entity_type": entity_type,
        "entity_id":   entity_id,
        "diff":        diff,
        "payload":     payload,
        "ip_address":  ip_address,
        "user_agent":  user_agent,
        "notes":       notes,
    }
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
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(entry)
    await db.flush()
    return entry


async def verify_chain(db: AsyncSession, *, limit: int | None = None) -> dict:
    """Walk the audit chain, return summary.

    Returns: {"checked": N, "ok": bool, "broken_at": <id or None>}.
    """
    stmt = select(AuditLog).order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    if limit:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    expected_prev = GENESIS_HASH
    for i, row in enumerate(rows, 1):
        body = {
            "actor_id":    str(row.actor_id) if row.actor_id else None,
            "actor_email": row.actor_email,
            "action":      row.action,
            "entity_type": row.entity_type,
            "entity_id":   row.entity_id,
            "diff":        row.diff,
            "payload":     row.payload,
            "ip_address":  row.ip_address,
            "user_agent":  row.user_agent,
            "notes":       row.notes,
        }
        if row.prev_hash != expected_prev:
            return {"checked": i, "ok": False, "broken_at": str(row.id), "reason": "prev_hash_mismatch"}
        expected = compute_entry_hash(expected_prev, body)
        if row.entry_hash != expected:
            return {"checked": i, "ok": False, "broken_at": str(row.id), "reason": "entry_hash_mismatch"}
        expected_prev = row.entry_hash

    return {"checked": len(rows), "ok": True, "broken_at": None}
