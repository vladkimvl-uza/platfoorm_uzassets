"""Audit service (Pack 9.0).

Two responsibilities:
  1. Write events (called from middleware and explicit code points)
  2. Read events + aggregate stats for /admin/audit/* endpoints

Security flag detection runs lazily in the overview endpoint (cheap aggregates).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
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

    # ── Owner firehose ──
    # Владелец(ы) получают уведомление о КАЖДОМ явном изменении контента
    # (кто что добавил/изменил/удалил). Берём только явные content-события:
    # у них http_method is None (middleware-логи GET/автосейвов его ставят →
    # отсекаем шум). Действия самих owner'ов не дублируем.
    try:
        if http_method is None and action and action != "VIEW" and actor_id is not None:
            from app.models.user import User
            from app.services.notifications_service import notify
            # Имя автора — чтобы было видно КТО изменил
            arow = (await db.execute(
                select(User.full_name, User.email).where(User.id == actor_id),
            )).first()
            actor_name = (arow[0] or arow[1]) if arow else (actor_email or "Кто-то")
            owner_rows = (await db.execute(
                select(User.id).where(User.is_owner.is_(True), User.is_active.is_(True)),
            )).all()
            link = (meta or {}).get("link") if isinstance(meta, dict) else None
            title = (entity_label or module or "Изменение")[:140]
            body = (f"{actor_name} {notes}" if notes else f"{actor_name} · {action}")[:400]
            for (oid,) in owner_rows:
                if str(oid) == str(actor_id):
                    continue
                await notify(
                    db, recipient_id=oid, type="owner.activity",
                    title=title, body=body, priority="normal", link_url=link,
                    source_module=module, source_entity_id=entity_id,
                    source_user_id=actor_id, commit=False,
                )
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).warning("owner activity fanout failed", exc_info=True)

    return row


# ─── Query helpers ───────────────────────────────────────────

# Быстрые чипы-категории → набор ILIKE-паттернов по action (server-side, полный
# по всем страницам). Зеркало клиентского actionCategory во фронте.
_ACTION_CATEGORY_PATTERNS: dict[str, list[str]] = {
    "logins":    ["%login%", "%logout%", "%session%", "%mfa%", "auth.%", "%telegram.link%", "%telegram.unlink%"],
    "access":    ["%role%", "%permission%", "%group%", "user.assign%", "user.remove%",
                  "user.create%", "user.invite%", "user.delete%", "user.deactivate%",
                  "user.activate%", "user.update%", "user.unlock%"],
    "data":      ["%create%", "%update%", "%change%", "%grant%", "%assign%", "%import%",
                  "%edit%", "%approve%", "%reject%"],
    "deletions": ["%delete%", "%revoke%", "%deactivate%"],
    # drill-down категории (виджеты дашборда аудита):
    "views":     ["view", "get", "%.view"],
    "changes":   ["create", "update", "%create", "%update", "%edit", "%import%", "%change%", "%approve%"],
    "errors":    ["error", "failed", "%.failed", "%denied%"],
}


async def query_events(
    db: AsyncSession,
    *,
    actor_email: Optional[str] = None,
    module: Optional[str] = None,
    action: Optional[str] = None,
    action_category: Optional[str] = None,
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
    if action_category and action_category in _ACTION_CATEGORY_PATTERNS:
        pats = _ACTION_CATEGORY_PATTERNS[action_category]
        conds.append(or_(*[func.lower(AuditLog.action).like(p) for p in pats]))
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
    since = datetime.now(UTC) - timedelta(hours=hours)
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

    online_since = datetime.now(UTC) - timedelta(minutes=15)
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
    since = datetime.now(UTC) - timedelta(hours=hours)
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


async def aggregate_by_user(
    db: AsyncSession,
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    search: Optional[str] = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    """Агрегат активности по пользователям (экран «Журнал → по пользователям»).

    Для каждого актора: всего действий, последняя активность + разбивка по типам
    (изменения / удаления / просмотры / входы / ошибки). Имена резолвятся из users.
    """
    conds = [AuditLog.actor_id.is_not(None)]
    if since:
        conds.append(AuditLog.created_at >= since)
    if until:
        conds.append(AuditLog.created_at <= until)
    if search:
        conds.append(func.lower(AuditLog.actor_email).like(f"%{search.lower()}%"))

    rows = (await db.execute(
        select(
            AuditLog.actor_id,
            func.max(AuditLog.actor_email).label("email"),
            func.max(AuditLog.actor_role).label("role"),
            func.count().label("total"),
            func.max(AuditLog.created_at).label("last_at"),
            func.count().filter(AuditLog.action.in_(["CREATE", "UPDATE"])).label("changes"),
            func.count().filter(AuditLog.action == "DELETE").label("deletions"),
            func.count().filter(AuditLog.action == "VIEW").label("views"),
            func.count().filter(func.lower(AuditLog.action).like("login%")).label("logins"),
            func.count().filter(AuditLog.action.in_(["ERROR", "FAILED"])).label("errors"),
        )
        .where(and_(*conds))
        .group_by(AuditLog.actor_id)
        .order_by(func.max(AuditLog.created_at).desc())
        .limit(limit),
    )).all()

    from app.models.user import User
    ids = [r.actor_id for r in rows if r.actor_id]
    names: dict[Any, Optional[str]] = {}
    if ids:
        nres = await db.execute(
            select(User.id, User.full_name, User.username).where(User.id.in_(ids))
        )
        for uid, fn, un in nres.all():
            names[uid] = fn or un

    palette = ["#7F77DD", "#1D9E75", "#378ADD", "#EF9F27", "#D4537E", "#4FB0C6", "#B07CC6"]
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        email = r.email or "—"
        name = names.get(r.actor_id) or (email.split("@")[0] if email != "—" else "—")
        parts = (name or email).replace(".", " ").replace("_", " ").split()
        initials = "".join(p[0].upper() for p in parts[:2]) if parts else "?"
        out.append({
            "actor_id": str(r.actor_id),
            "email": email,
            "name": name,
            "role": r.role,
            "initials": initials,
            "accent": palette[i % len(palette)],
            "total": int(r.total),
            "last_at": r.last_at,
            "changes": int(r.changes),
            "deletions": int(r.deletions),
            "views": int(r.views),
            "logins": int(r.logins),
            "errors": int(r.errors),
        })
    return out


# Разрыв > этого порога завершает «сессию» активности (мин).
_SESSION_GAP_MIN = 30
# Время «в разделе» до следующего действия не может превышать (мин) — иначе это
# простой/уход, а не работа в разделе.
_DWELL_CAP_MIN = 15


def _humanize(action: str, module: str | None, entity: str | None) -> str:
    """Короткое читаемое описание (зеркало фронтового describe для сводок)."""
    a = (action or "").lower()
    if "login" in a or a.startswith("auth.login"):
        return "вход в систему"
    if "logout" in a:
        return "выход"
    if "refresh" in a or "session" in a:
        return "продление сессии"
    if a in ("view", "get") or a.endswith(".view"):
        return f"просмотр: {MODULE_LABELS.get(module or '', module or 'раздел')}"
    if a in ("create", "post") or "create" in a:
        return f"создание{(' · ' + entity) if entity else ''}"
    if a in ("update", "put", "patch") or "update" in a or "edit" in a:
        return f"изменение{(' · ' + entity) if entity else ''}"
    if a == "delete" or "delete" in a:
        return f"удаление{(' · ' + entity) if entity else ''}"
    if "import" in a:
        return f"импорт{(' · ' + entity) if entity else ''}"
    if a in ("error", "failed") or "denied" in a:
        return "ошибка/отказ"
    return f"{action}{(' · ' + entity) if entity else ''}"


def _type_of(action: str) -> str:
    a = (action or "").lower()
    if "login" in a or "logout" in a or "session" in a or "mfa" in a or a.startswith("auth"):
        return "logins"
    if a in ("view", "get") or a.endswith(".view"):
        return "views"
    if a == "delete" or "delete" in a or "revoke" in a:
        return "deletions"
    if a in ("error", "failed") or "denied" in a:
        return "errors"
    if a in ("create", "update", "post", "put", "patch") or any(
        k in a for k in ("create", "update", "edit", "import", "change", "approve", "assign", "grant")
    ):
        return "changes"
    return "other"


async def aggregate_user_activity(
    db: AsyncSession,
    *,
    actor_id: str,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> dict[str, Any]:
    """Персональная аналитика активности пользователя (модалка «по людям»):

    - **sessions**: окна непрерывной активности за период (start/end/duration/events),
      разрыв > _SESSION_GAP_MIN завершает сессию. + суммарное «время в системе».
    - **by_module**: где провёл больше всего времени (оценка dwell-времени между
      последовательными действиями, capped) + кол-во действий.
    - **by_type**: разбивка changes/views/logins/deletions/errors.
    - **recent**: последние действия, схлопнутые по повторам (action+module).
    """
    conds = [AuditLog.actor_id == actor_id]
    if since:
        conds.append(AuditLog.created_at >= since)
    if until:
        conds.append(AuditLog.created_at <= until)
    rows = (await db.execute(
        select(
            AuditLog.created_at, AuditLog.action, AuditLog.module,
            AuditLog.entity_label, AuditLog.http_path, AuditLog.ip_address,
        )
        .where(and_(*conds))
        .order_by(AuditLog.created_at.asc())
    )).all()

    gap = timedelta(minutes=_SESSION_GAP_MIN)
    cap = _DWELL_CAP_MIN * 60

    sessions: list[dict[str, Any]] = []
    by_module: dict[str, dict[str, Any]] = {}
    by_type: dict[str, int] = {"changes": 0, "views": 0, "logins": 0, "deletions": 0, "errors": 0, "other": 0}
    cur: Optional[dict[str, Any]] = None
    total_active = 0.0

    for i, r in enumerate(rows):
        t = r.created_at
        by_type[_type_of(r.action)] = by_type.get(_type_of(r.action), 0) + 1
        # dwell-время до следующего действия (для оценки времени в разделе)
        dwell = 0.0
        if i + 1 < len(rows):
            delta = (rows[i + 1].created_at - t).total_seconds()
            dwell = min(max(delta, 0), cap) if delta <= gap.total_seconds() else 0
        mod = r.module or _module_from_path_safe(r.http_path)
        if mod:
            b = by_module.setdefault(mod, {"count": 0, "seconds": 0.0})
            b["count"] += 1
            b["seconds"] += dwell
        # сессии
        if cur is None or (t - cur["_last"]) > gap:
            if cur is not None:
                sessions.append(_finalize_session(cur))
            cur = {"start": t, "_last": t, "end": t, "events": 1}
        else:
            cur["_last"] = t
            cur["end"] = t
            cur["events"] += 1
        total_active += dwell
    if cur is not None:
        sessions.append(_finalize_session(cur))

    # время в системе ≈ сумма длительностей сессий (надёжнее dwell-суммы)
    in_system_sec = sum(s["duration_sec"] for s in sessions)

    modules_out = sorted(
        ({"module": m, "label": MODULE_LABELS.get(m, m), "count": v["count"],
          "seconds": int(v["seconds"])} for m, v in by_module.items()),
        key=lambda x: (-x["seconds"], -x["count"]),
    )

    # схлопнутая лента последних действий (повтор action+module → count)
    recent: list[dict[str, Any]] = []
    for r in reversed(rows):
        mod = r.module or _module_from_path_safe(r.http_path)
        desc = _humanize(r.action, mod, r.entity_label)
        if recent and recent[-1]["desc"] == desc and recent[-1]["module"] == mod:
            recent[-1]["count"] += 1
            recent[-1]["last_at"] = recent[-1]["last_at"]  # newest already
        else:
            recent.append({
                "desc": desc, "action": r.action,
                "module": mod, "label": MODULE_LABELS.get(mod or "", mod),
                "at": r.created_at, "last_at": r.created_at, "count": 1,
                "type": _type_of(r.action),
            })
        if len(recent) >= 60:
            break

    return {
        "total_events": len(rows),
        "in_system_seconds": int(in_system_sec),
        "sessions_count": len(sessions),
        "sessions": [
            {"start": s["start"], "end": s["end"], "duration_sec": s["duration_sec"], "events": s["events"]}
            for s in sessions
        ],
        "by_module": modules_out,
        "by_type": by_type,
        "recent": recent,
    }


def _finalize_session(s: dict[str, Any]) -> dict[str, Any]:
    dur = int((s["end"] - s["start"]).total_seconds())
    return {"start": s["start"], "end": s["end"], "duration_sec": dur, "events": s["events"]}


def _module_from_path_safe(path: str | None) -> str | None:
    try:
        return module_from_path(path or "")
    except Exception:
        return None


async def top_modules(db: AsyncSession, hours: int = 24) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(hours=hours)
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
    now = datetime.now(UTC)

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
    since = datetime.now(UTC) - timedelta(hours=hours)
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
