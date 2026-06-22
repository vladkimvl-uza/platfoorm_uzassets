"""Executive Overview — министерский обзор сектор→компания→проекты+дедлайны.

Доступ по скоупу (как Executive Dashboard): owner/unrestricted видит весь
портфель, scoped-пользователь — только разрешённые компании.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.models.user import User
from app.schemas.exec_overview import ExecOverviewResponse
from app.services.exec_overview import build_exec_overview

log = logging.getLogger(__name__)
router = APIRouter(prefix="/exec-overview", tags=["exec-overview"])


async def _scope(db: AsyncSession, user: User):
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


async def _company_financials(db: AsyncSession, user: User, year: Optional[int]) -> dict[str, dict]:
    """Best-effort: по каждой компании выручка+прибыль за последний доступный
    год (NSBU, иначе IFRS), абс. UZS. Переиспользует portfolio summary."""
    from app.services.financials_portfolio.service import FinancialsPortfolioService

    yr = year or date.today().year
    years_str = ",".join(str(yr - i) for i in range(0, 3))
    svc = FinancialsPortfolioService()
    out: dict[str, dict] = {}
    for std in ("NSBU", "IFRS"):
        try:
            res = await svc.summary(db, user, standard=std, years=years_str, currency="UZS")
        except Exception:
            continue
        for it in res.get("items", []):
            cid = it.get("company_id")
            by_year = it.get("by_year", {})
            if not cid or cid in out or not by_year:
                continue
            for y in sorted(by_year.keys(), reverse=True):
                m = by_year[y] or {}
                rev, prof = m.get("revenue"), m.get("profit")
                if rev is not None or prof is not None:
                    out[cid] = {"revenue": rev, "profit": prof, "fin_year": int(y)}
                    break
        if out:
            break  # предпочитаем NSBU
    return out


@router.get("", response_model=ExecOverviewResponse)
async def exec_overview(
    year: Optional[int] = Query(None, description="Портфельный год (по умолчанию все)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExecOverviewResponse:
    scope = await _scope(db, user)
    fin_map: dict[str, dict] = {}
    try:
        fin_map = await _company_financials(db, user, year)
    except Exception as e:  # noqa: BLE001
        log.warning("exec-overview financials failed: %s", e)
    return await build_exec_overview(db, scope, year, date.today(), fin_map)
