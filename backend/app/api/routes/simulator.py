"""Scenario simulator — live what-if по макро-факторам.

Слайдеры макро-факторов (курс USD, нефть, инфляция, ставка ЦБ, …) →
мгновенный пересчёт влияния на метрику (выручка/EBITDA/чистая прибыль) по
каждой компании портфеля и в сумме. Формула совпадает с движком декомпозиции:
    Δметрика = база × (Δфактор как доля) × β(фактор, метрика, компания)
RBAC: компании ограничены allowed_company_ids.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.decomposition_engine import _resolve_beta, _get_base_value

router = APIRouter(prefix="/simulator", tags=["simulator"])

# Слайдеры — % изменение фактора. Диапазоны подобраны под реалистичные шоки.
FACTORS = [
    {"code": "usd_rate",        "label": "Курс USD/UZS",   "min": -15, "max": 15, "step": 1, "accent": "#378ADD"},
    {"code": "oil_price_brent", "label": "Нефть Brent",    "min": -30, "max": 30, "step": 1, "accent": "#1E2A4A"},
    {"code": "eur_rate",        "label": "Курс EUR/UZS",   "min": -15, "max": 15, "step": 1, "accent": "#534AB7"},
    {"code": "inflation_pct",   "label": "Инфляция",       "min": -40, "max": 40, "step": 2, "accent": "#EF9F27"},
    {"code": "cb_rate_pct",     "label": "Ставка ЦБ",      "min": -30, "max": 30, "step": 2, "accent": "#E24B4A"},
    {"code": "gdp_growth_pct",  "label": "Рост ВВП",       "min": -40, "max": 40, "step": 2, "accent": "#1D9E75"},
]
METRICS = [
    {"code": "revenue",    "label": "Выручка"},
    {"code": "ebitda",     "label": "EBITDA"},
    {"code": "net_income", "label": "Чистая прибыль"},
]


@router.get("/factors")
async def factors(user: User = Depends(get_current_user)):
    return {"factors": FACTORS, "metrics": METRICS}


class RunPayload(BaseModel):
    target_metric: str = "revenue"
    year: int = 2026
    shocks: dict[str, float] = {}  # {factor_code: pct_change}


@router.post("/run")
async def run(
    payload: RunPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    metric = payload.target_metric if payload.target_metric in {m["code"] for m in METRICS} else "revenue"
    year = int(payload.year or 2026)
    base_year = year - 1
    shocks = {k: float(v) for k, v in (payload.shocks or {}).items()
              if k in {f["code"] for f in FACTORS} and v}

    allowed = await allowed_company_ids(db, user)
    cids = [str(c) for c in allowed] if isinstance(allowed, list) else None

    # Список компаний (scoped)
    sql = "SELECT id::text, COALESCE(name_short, name_ru) AS nm FROM companies"
    params: dict = {}
    if allowed == []:
        return {"metric": metric, "year": year, "by_company": [], "totals": _empty_totals(),
                "coverage": {"companies": 0, "with_base": 0, "with_beta": 0}, "shocks": shocks}
    if cids is not None:
        sql += " WHERE id::text = ANY(:cids)"
        params["cids"] = cids
    sql += " ORDER BY nm"
    companies = (await db.execute(text(sql), params)).all()

    from uuid import UUID as _UUID
    rows = []
    base_sum = Decimal("0"); delta_sum = Decimal("0")
    n_base = 0; n_beta = 0
    for cid, name in companies:
        cuuid = _UUID(cid)
        base = await _get_base_value(db, cuuid, metric, base_year)
        if base and base != 0:
            n_base += 1
        comp_delta = Decimal("0")
        used_beta = False
        for fcode, pct in shocks.items():
            beta = await _resolve_beta(db, None, cuuid, fcode, metric)
            if not beta or beta == 0:
                continue
            used_beta = True
            comp_delta += base * (Decimal(str(pct)) / Decimal("100")) * beta
        if used_beta:
            n_beta += 1
        forecast = base + comp_delta
        base_sum += base
        delta_sum += comp_delta
        rows.append({
            "company_id": cid,
            "name": name,
            "base": float(round(base, 2)),
            "delta": float(round(comp_delta, 2)),
            "forecast": float(round(forecast, 2)),
            "delta_pct": float(round(comp_delta / base * 100, 2)) if base and base != 0 else 0.0,
        })

    # Сортировка: по абсолютной величине влияния
    rows.sort(key=lambda r: -abs(r["delta"]))
    forecast_sum = base_sum + delta_sum
    totals = {
        "base": float(round(base_sum, 2)),
        "delta": float(round(delta_sum, 2)),
        "forecast": float(round(forecast_sum, 2)),
        "delta_pct": float(round(delta_sum / base_sum * 100, 2)) if base_sum and base_sum != 0 else 0.0,
    }
    return {
        "metric": metric, "year": year, "shocks": shocks,
        "by_company": rows,
        "totals": totals,
        "coverage": {"companies": len(companies), "with_base": n_base, "with_beta": n_beta},
        "unit": "млн UZS",
    }


def _empty_totals():
    return {"base": 0.0, "delta": 0.0, "forecast": 0.0, "delta_pct": 0.0}
