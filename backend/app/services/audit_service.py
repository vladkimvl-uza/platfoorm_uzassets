"""Audit service (Pack 9.0).

Two responsibilities:
  1. Write events (called from middleware and explicit code points)
  2. Read events + aggregate stats for /admin/audit/* endpoints

Security flag detection runs lazily in the overview endpoint (cheap aggregates).
"""
from __future__ import annotations

import hmac
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


# ─── Constants ───────────────────────────────────────────────

def _load_hmac_secret() -> bytes:
    """Load audit HMAC secret from the same file `app.core.audit_chain` uses.
    File-only — fail fast if the key isn't on disk (no hardcoded default).
    """
    secret_path = os.environ.get("AUDIT_HMAC_SECRET_PATH", "/app/keys/audit_hmac.key")
    if not os.path.exists(secret_path):
        raise RuntimeError(
            f"Audit HMAC secret not found at {secret_path}. "
            "Generate via scripts/generate-keys.sh and mount it into the container."
        )
    with open(secret_path, "rb") as f:
        secret = f.read().strip()
    if len(secret) < 32:
        raise RuntimeError(f"Audit HMAC secret too short ({len(secret)} bytes); need ≥ 32.")
    return secret

_HMAC_SECRET = _load_hmac_secret()

# Color hints for stat cards (matches Vue palette)
ACCENT = {
    "events":   "#7F77DD",
    "users":    "#378ADD",
    "changes":  "#1D9E75",
    "views":    "#EF9F27",
    "errors":   "#E24B4A",
    "critical": "#D4537E",
}

MODULE_LABELS = {
    "kpi":         "KPI",
    "bp":          "Бизнес-план",
    "business_plan":"Бизнес-план",
    "governance":  "Governance",
    "esg":         "ESG",
    "financials":  "Финансы",
    "procurement": "Закупки",
    "ratings":     "Рейтинги",
    "admin":       "Админка",
    "rbac":        "RBAC",
    "audit":       "Audit",
    "auth":        "Аутентификация",
    "dashboard":   "Дашборд",
}


def module_from_path(path: str) -> Optional[str]:
    """Map URL path → module name. Skip nav/static."""
    if not path:
        return None
    parts = [p for p in path.split("/") if p and p not in ("api", "v1")]
    if not parts:
        return None
    head = parts[0].lower().replace("-", "_")
    aliases = {
        "kpi":            "kpi",
        "bp":             "bp",
        "business_plan":  "bp",
        "businessplan":   "bp",
        "governance":     "governance",
        "esg":            "esg",
        "financials":     "financials",
        "finance":        "financials",
        "procurement":    "procurement",
        "ratings":        "ratings",
        "rbac":           "rbac",
        "admin":          "admin",
        "audit":          "audit",
        "auth":           "auth",
        "dashboard":      "dashboard",
    }
    return aliases.get(head)


def action_from_method(method: str, status: int = 200) -> str:
    """Map HTTP method + status → action verb."""
    m = (method or "").upper()
    if status >= 500:
        return "ERROR"
    if status >= 400:
        return "FAILED" if status == 401 or status == 403 else "ERROR"
    if m == "GET":
        return "VIEW"
    if m == "POST":
        return "CREATE"
    if m in ("PUT", "PATCH"):
        return "UPDATE"
    if m == "DELETE":
        return "DELETE"
    return m or "UNKNOWN"


# ─── HMAC chain ──────────────────────────────────────────────

def _canonical(entry: dict[str, Any]) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hash(prev_hash: Optional[str], entry: dict[str, Any]) -> str:
    msg = (prev_hash or "").encode() + _canonical(entry).encode()
    return hmac.new(_HMAC_SECRET, msg, hashlib.sha256).hexdigest()


async def _latest_hash(db: AsyncSession) -> Optional[str]:
    """Find the current chain tip — the entry_hash that no other row uses
    as its prev_hash. Using created_at ordering is unsafe because concurrent
    transactions can land out-of-order timestamps; chain integrity must
    follow the cryptographic links.

    With the UNIQUE index on prev_hash, this query is O(log N) via index
    anti-join.
    """
    row = await db.execute(text("""
        SELECT al.entry_hash
        FROM audit_log al
        WHERE al.entry_hash IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM audit_log al2
            WHERE al2.prev_hash = al.entry_hash
          )
        LIMIT 1
    """))
    return row.scalar_one_or_none()


# ─── Write ───────────────────────────────────────────────────

async def write_event(
    db: AsyncSession,
    *,
    actor_id: Optional[UUID] = None,
    actor_email: Optional[str] = None,
    actor_role: Optional[str] = None,
    action: str,
    module: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    entity_label: Optional[str] = None,
    http_method: Optional[str] = None,
    http_path: Optional[str] = None,
    http_status: Optional[int] = None,
    duration_ms: Optional[int] = None,
    diff: Optional[dict[str, Any]] = None,
    payload: Optional[dict[str, Any]] = None,
    meta: Optional[dict[str, Any]] = None,
    notes: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    is_critical: bool = False,
) -> AuditLog:
    """Insert a single audit row. Computes HMAC chain hashes.

    Serialized via Postgres advisory lock (key 9211) to prevent prev_hash
    race conditions across concurrent writers (worker processes + middleware
    inserts hitting the same head simultaneously).
    """
    # Serialize via sentinel row lock — see audit_chain.append_audit_entry
    # for rationale (advisory lock was empirically racy under load).
    await db.execute(text("SELECT id FROM audit_chain_lock WHERE id = 1 FOR UPDATE"))
    prev = await _latest_hash(db)
    # Use the unified chain body so this writer and the explicit
    # `append_audit_entry` writer produce identical hashes.
    # ALL persisted metadata is in the HMAC so DB-level tampering with
    # diff/payload/ip_address/user_agent/notes will break verification.
    from app.core.audit_chain import build_chain_body
    entry = build_chain_body(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        http_method=http_method,
        http_path=http_path,
        http_status=http_status,
        diff=diff,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
        notes=notes,
    )
    entry_hash = _compute_hash(prev, entry)

    row = AuditLog(
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        http_method=http_method,
        http_path=http_path,
        http_status=http_status,
        duration_ms=duration_ms,
        diff=diff,
        payload=payload,
        meta=meta,
        notes=notes,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:512] or None,
        is_critical=is_critical,
        prev_hash=prev,
        entry_hash=entry_hash,
    )
    db.add(row)
    await db.flush()
    return row


# ─── Query helpers ───────────────────────────────────────────

async def query_events(
    db: AsyncSession,
    *,
    actor_email: Optional[str] = None,
    module: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    search: Optional[str] = None,
    only_critical: bool = False,
    api_key_id: Optional[str] = None,   # Pack 12.4
    only_api_key: bool = False,         # Pack 12.4
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    q = select(AuditLog)

    conds = []
    if actor_email:
        conds.append(AuditLog.actor_email == actor_email)
    if module:
        conds.append(AuditLog.module == module)
    if action:
        conds.append(AuditLog.action == action)
    if since:
        conds.append(AuditLog.created_at >= since)
    if until:
        conds.append(AuditLog.created_at <= until)
    if api_key_id:
        conds.append(AuditLog.api_key_id == api_key_id)
    if only_api_key:
        conds.append(AuditLog.api_key_id.is_not(None))
    if only_critical:
        conds.append(AuditLog.is_critical.is_(True))
    if search:
        like = f"%{search.lower()}%"
        conds.append(or_(
            func.lower(AuditLog.actor_email).like(like),
            func.lower(AuditLog.http_path).like(like),
            func.lower(AuditLog.entity_label).like(like),
            AuditLog.entity_id == search,
            AuditLog.ip_address == search,
        ))
    if conds:
        q = q.where(and_(*conds))

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar() or 0

    rows = (await db.execute(
        q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()

    return rows, total


# ─── Aggregates ──────────────────────────────────────────────

async def compute_stats(db: AsyncSession, hours: int = 24) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    prev_since = since - timedelta(hours=hours)

    base = select(AuditLog).where(AuditLog.created_at >= since)

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0

    prev_total = (await db.execute(
        select(func.count(AuditLog.id)).where(
            and_(AuditLog.created_at >= prev_since, AuditLog.created_at < since),
        ),
    )).scalar() or 0

    unique_users = (await db.execute(
        select(func.count(func.distinct(AuditLog.actor_id)))
        .where(and_(AuditLog.created_at >= since, AuditLog.actor_id.is_not(None))),
    )).scalar() or 0

    online_since = datetime.now(timezone.utc) - timedelta(minutes=15)
    online_users = (await db.execute(
        select(func.count(func.distinct(AuditLog.actor_id)))
        .where(and_(AuditLog.created_at >= online_since, AuditLog.actor_id.is_not(None))),
    )).scalar() or 0

    changes = (await db.execute(
        select(func.count(AuditLog.id)).where(and_(
            AuditLog.created_at >= since,
            AuditLog.action.in_(["CREATE", "UPDATE", "DELETE"]),
        )),
    )).scalar() or 0

    views = (await db.execute(
        select(func.count(AuditLog.id)).where(and_(
            AuditLog.created_at >= since,
            AuditLog.action == "VIEW",
        )),
    )).scalar() or 0

    errors = (await db.execute(
        select(func.count(AuditLog.id)).where(and_(
            AuditLog.created_at >= since,
            or_(AuditLog.action.in_(["ERROR", "FAILED"]),
                AuditLog.http_status >= 400),
        )),
    )).scalar() or 0

    critical = (await db.execute(
        select(func.count(AuditLog.id)).where(and_(
            AuditLog.created_at >= since,
            AuditLog.is_critical.is_(True),
        )),
    )).scalar() or 0

    delta = None
    if prev_total > 0:
        delta = round(((total - prev_total) / prev_total) * 100, 1)

    return {
        "period_hours": hours,
        "events_total": total,
        "unique_users": unique_users,
        "online_users": online_users,
        "changes": changes,
        "views": views,
        "errors": errors,
        "critical": critical,
        "delta_pct": delta,
    }


async def top_users(db: AsyncSession, hours: int = 24, limit: int = 5) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (await db.execute(
        select(
            AuditLog.actor_id,
            AuditLog.actor_email,
            func.count(AuditLog.id).label("c"),
        )
        .where(and_(AuditLog.created_at >= since, AuditLog.actor_email.is_not(None)))
        .group_by(AuditLog.actor_id, AuditLog.actor_email)
        .order_by(func.count(AuditLog.id).desc())
        .limit(limit),
    )).all()

    palette = ["#7F77DD", "#1D9E75", "#378ADD", "#EF9F27", "#D4537E"]
    out = []
    for i, (aid, email, c) in enumerate(rows):
        initials = "?"
        if email:
            local = email.split("@", 1)[0]
            parts = local.replace(".", " ").replace("_", " ").split()
            initials = "".join(p[0].upper() for p in parts[:2]) or local[:2].upper()
        out.append({
            "actor_id": aid,
            "email": email or "—",
            "initials": initials,
            "count": int(c),
            "accent": palette[i % len(palette)],
        })
    return out


async def top_modules(db: AsyncSession, hours: int = 24) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (await db.execute(
        select(AuditLog.module, func.count(AuditLog.id).label("c"))
        .where(and_(AuditLog.created_at >= since, AuditLog.module.is_not(None)))
        .group_by(AuditLog.module)
        .order_by(func.count(AuditLog.id).desc())
        .limit(8),
    )).all()
    return [
        {"module": m, "label": MODULE_LABELS.get(m, m), "count": int(c)}
        for m, c in rows
    ]


async def detect_security_flags(db: AsyncSession) -> list[dict[str, Any]]:
    """Cheap aggregates over recent activity, no separate table needed."""
    flags: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    # 1) repeated failed logins (>=3 by same email in last 10 min)
    since10 = now - timedelta(minutes=10)
    fails = (await db.execute(
        select(AuditLog.actor_email, AuditLog.ip_address, func.count(AuditLog.id).label("c"))
        .where(and_(
            AuditLog.created_at >= since10,
            or_(AuditLog.action.in_(["FAILED", "FAILED_LOGIN"]),
                AuditLog.http_status == 401),
        ))
        .group_by(AuditLog.actor_email, AuditLog.ip_address)
        .having(func.count(AuditLog.id) >= 3),
    )).all()
    for email, ip, c in fails:
        flags.append({
            "id": __import__("uuid").uuid4(),
            "severity": "critical",
            "kind": "repeated_fails",
            "title": f"{c} неудачных входа подряд",
            "detail": f"{email or 'unknown'} · IP {ip or '—'}",
            "created_at": now,
            "related_user_email": email,
            "related_ip": str(ip) if ip else None,
            "is_resolved": False,
        })

    # 2) Mass DELETE (>=10 by same user in 5 min)
    since5 = now - timedelta(minutes=5)
    massdel = (await db.execute(
        select(AuditLog.actor_email, func.count(AuditLog.id).label("c"))
        .where(and_(
            AuditLog.created_at >= since5,
            AuditLog.action == "DELETE",
            AuditLog.actor_email.is_not(None),
        ))
        .group_by(AuditLog.actor_email)
        .having(func.count(AuditLog.id) >= 10),
    )).all()
    for email, c in massdel:
        flags.append({
            "id": __import__("uuid").uuid4(),
            "severity": "warning",
            "kind": "mass_delete",
            "title": "Массовое удаление",
            "detail": f"{email} · {c} операций за 5 мин",
            "created_at": now,
            "related_user_email": email,
            "related_ip": None,
            "is_resolved": False,
        })

    return flags


async def timeline(db: AsyncSession, hours: int = 24, bucket: str = "hour") -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    trunc = func.date_trunc(bucket, AuditLog.created_at)

    rows = (await db.execute(
        select(
            trunc.label("ts"),
            AuditLog.action,
            func.count(AuditLog.id).label("c"),
        )
        .where(AuditLog.created_at >= since)
        .group_by(trunc, AuditLog.action)
        .order_by(trunc),
    )).all()

    by_ts: dict[datetime, dict[str, int]] = {}
    for ts, action, c in rows:
        d = by_ts.setdefault(ts, {})
        d[action.lower()] = int(c) + d.get(action.lower(), 0)

    return [
        {"ts": ts, **{
            "view":   d.get("view", 0),
            "update": d.get("update", 0),
            "create": d.get("create", 0),
            "delete": d.get("delete", 0),
            "error":  d.get("error", 0) + d.get("failed", 0),
            "login":  d.get("login", 0),
        }}
        for ts, d in sorted(by_ts.items())
    ]
