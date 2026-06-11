"""Procurement apply handler (Pack 148-followup B1 extension).

Mirrors PUT /forensic/companies/{code} — patches the JSONB snapshot
`system_config['raw_snapshot.procurementData']` in place.

Action: "update_company"
  proposed_value shape (from CompanyPatch in routes/forensic.py):
    {
      "year": int,
      "year_fields": { plan, fact, n9p, n9f, q1p..q4f } | None,
      "plan_status": str | None,
      "forensic_status": str | None,
      "auditor": str | None,
      "audit_years": str | None,
    }
  target_entity_id holds the company `code` (lowercase abbr).
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.moderation_service import register_apply_handler

_SNAPSHOT_KEY = "raw_snapshot.procurementData"
_YEAR_FIELDS = ("plan", "fact", "n9p", "n9f",
                "q1p", "q1f", "q2p", "q2f", "q3p", "q3f", "q4p", "q4f")


async def _load_snapshot(db) -> list[dict]:
    res = await db.execute(text("SELECT value FROM system_config WHERE key = :k LIMIT 1"), {"k": _SNAPSHOT_KEY})
    row = res.first()
    if not row or not row[0]:
        return []
    snap = row[0]
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except json.JSONDecodeError:
            return []
    return snap if isinstance(snap, list) else []


async def _save_snapshot(db, snap: list[dict]) -> None:
    await db.execute(text("""
        INSERT INTO system_config (id, key, value, description, is_secret, created_at, updated_at)
        VALUES (gen_random_uuid(), :k, CAST(:v AS jsonb), :d, FALSE, NOW(), NOW())
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, updated_at = NOW()
    """), {
        "k": _SNAPSHOT_KEY,
        "v": json.dumps(snap, ensure_ascii=False),
        "d": "Procurement plan/fact data (PROCUREMENT_DATA) mutable via /forensic endpoints",
    })


def _ensure_year_row(co: dict, year: int) -> dict:
    if not isinstance(co.get("years"), list):
        co["years"] = []
    for yr in co["years"]:
        if yr.get("y") == year:
            return yr
    new_yr: dict = {"y": year}
    co["years"].append(new_yr)
    return new_yr


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict[str, Any]:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()

    if action != "update_company":
        raise ValueError(f"unknown procurement action: {action!r}")

    code = (sub.target_entity_id or "").lower()
    if not code:
        raise ValueError("missing target_entity_id (company code)")

    payload = dict(sub.proposed_value or {})
    year = payload.get("year")
    if not isinstance(year, int):
        raise ValueError(f"invalid year in payload: {year!r}")

    snap = await _load_snapshot(db)
    if not snap:
        raise ValueError("procurement snapshot not initialised — no data to patch")

    co = next((c for c in snap if isinstance(c, dict) and (c.get("k") or "").lower() == code), None)
    if co is None:
        raise ValueError(f"company '{code}' not found in snapshot")

    # Meta fields (None = skip; explicit empty-string clears)
    for src_key, dst_key in [
        ("plan_status",     "plan"),
        ("forensic_status", "forensic"),
        ("auditor",         "auditor"),
        ("audit_years",     "aYears"),
    ]:
        v = payload.get(src_key)
        if v is not None:
            co[dst_key] = v

    # Year-level numeric fields
    yf = payload.get("year_fields") or {}
    if isinstance(yf, dict) and yf:
        yr = _ensure_year_row(co, year)
        for f in _YEAR_FIELDS:
            v = yf.get(f)
            if v is not None:
                yr[f] = v

    await _save_snapshot(db, snap)
    await db.commit()

    return {
        "action": "update_company",
        "code": code,
        "year": year,
        "meta_fields_set": [k for k in ("plan_status", "forensic_status", "auditor", "audit_years") if payload.get(k) is not None],
        "year_fields_set": [k for k in _YEAR_FIELDS if isinstance(yf, dict) and yf.get(k) is not None],
    }


register_apply_handler("procurement", apply)
