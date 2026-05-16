"""Forensic & Procurement audit endpoints.

Endpoint:
  GET /api/forensic/overview      → list of 22 companies with plan/fact/forensic data

Source: system_config['firebase_dump.procurementData'] (Phase 4 already snapshotted
this 10 KB JSONB from /pf/procurementData). Each row has the monolith shape:
  {
    n: 'НГМК', k: 'ngmk', s: 'mining',
    yP24, yF24, nP24, nF24,           # 2024 plan/fact (annual + 9m)
    yP25, yF25, nP25, nF25,           # 2025
    yP26,                              # 2026 plan only
    plan: 'Утверждён' | 'Не утверждён' | ...,
    forensic: 'Завершён' | 'В процессе' | 'Тендер в 2026' | 'Не начат',
    auditor: 'KPMG' | 'PwC' | 'Deloitte' | 'E&Y' | '',
    aYears: '2024' | '2022-2024' | '',
    years?: [{y, plan, fact, n9p, n9f, q1p, q1f, ...}]   # newer schema
  }

The endpoint passes data through with minimal transformation — just enriches
each row with `sector_color` (from companies table sector → color) so the
frontend can colour-tag without an extra lookup.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import _has_permission
from app.models.company import Company, Sector
from app.models.user import User


log = logging.getLogger(__name__)
router = APIRouter(prefix="/forensic", tags=["forensic"])


# Sector → colour mapping (mirrors monolith _pSC palette)
_SECTOR_COLOR = {
    "mining":    "#9B8EC4",
    "oilgas":    "#1D9E75",
    "energy":    "#EF9F27",
    "transport": "#378ADD",
    "other":     "#888780",
}


@router.get("/overview")
async def forensic_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Returns the full list of 22 companies with plan/fact/forensic data.

    Response shape:
      {
        "companies": [
          {n, k, s, sector_color,
           yP24, yF24, nP24, nF24, yP25, yF25, nP25, nF25, yP26,
           plan, forensic, auditor, aYears, years?},
          ...
        ],
        "kpis": {
          "total_companies": 22,
          "plan_approved": <count>,
          "forensic_done": <count>,
          "with_auditor": <count>
        }
      }
    """
    if not _has_permission(user, "procurement.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "procurement.view required")

    # 1. Read snapshot from system_config (Phase 4 puts it here)
    res = await db.execute(text(
        "SELECT value FROM system_config "
        "WHERE key = 'firebase_dump.procurementData' LIMIT 1"
    ))
    row = res.first()
    if not row or not row[0]:
        return {
            "companies": [],
            "kpis": {
                "total_companies": 0,
                "plan_approved": 0,
                "forensic_done": 0,
                "with_auditor": 0,
            },
        }

    snap = row[0]
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except json.JSONDecodeError:
            log.warning("forensic/overview: failed to parse JSONB snapshot")
            return {"companies": [], "kpis": {}}

    if not isinstance(snap, list):
        return {"companies": [], "kpis": {}}

    # Scope filter: snapshot хранит company.code в поле `k`, не UUID.
    # Резолвим allowed_company_ids → codes → фильтруем snapshot.
    allowed_codes: Optional[set[str]] = None
    if not has_unrestricted_view(user):
        scope_ids = await allowed_company_ids(db, user)
        if not scope_ids:
            return {
                "companies": [],
                "kpis": {
                    "total_companies": 0,
                    "plan_approved": 0,
                    "forensic_done": 0,
                    "with_auditor": 0,
                },
            }
        code_q = await db.execute(
            select(Company.code).where(Company.id.in_(scope_ids))
        )
        allowed_codes = {c.lower() for (c,) in code_q.all() if c}

    # 2. Enrich each row with sector_color from sector code
    companies: list[dict[str, Any]] = []
    plan_approved = forensic_done = with_auditor = 0
    for raw in snap:
        if not isinstance(raw, dict):
            continue
        # Scope-фильтр для не-admin юзеров. Пропускаем записи компаний,
        # которых нет в allowed_companies (snapshot хранит code в поле `k`).
        if allowed_codes is not None:
            row_code = (raw.get("k") or "").strip().lower()
            if not row_code or row_code not in allowed_codes:
                continue
        sector = (raw.get("s") or "other").lower()
        enriched = dict(raw)
        enriched["sector_color"] = _SECTOR_COLOR.get(sector, _SECTOR_COLOR["other"])

        # KPIs
        if (raw.get("plan") or "").startswith("Утверждён"):
            plan_approved += 1
        if raw.get("forensic") == "Завершён":
            forensic_done += 1
        if (raw.get("auditor") or "").strip():
            with_auditor += 1

        companies.append(enriched)

    # Sort by sector order then name (mirrors monolith _pSC palette order)
    sector_order = {"mining": 0, "oilgas": 1, "energy": 2, "transport": 3, "other": 4}
    companies.sort(key=lambda c: (
        sector_order.get((c.get("s") or "other").lower(), 99),
        c.get("n") or "",
    ))

    return {
        "companies": companies,
        "kpis": {
            "total_companies": len(companies),
            "plan_approved": plan_approved,
            "forensic_done": forensic_done,
            "with_auditor": with_auditor,
        },
    }
