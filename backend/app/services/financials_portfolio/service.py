"""Portfolio summary use-case (Pack 7.40 / 7.54).

Aggregates financial metrics across all accessible companies into per-company
× year × metric breakdown with currency normalization (UZS → target).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.models.user import User
from app.repositories.financials_repository import FinancialsRepository

log = logging.getLogger(__name__)


# Maps actual line_code variants (any case) → canonical metric code
# returned in the response. Frontend reads only canonical names.
_PORTFOLIO_METRIC_ALIASES: dict[str, str] = {
    # P&L
    "revenue": "revenue",
    "cogs": "cogs",
    "grossProfit": "grossProfit",
    "gross_profit": "grossProfit",
    "opProfit": "opProfit",
    "operatingProfit": "opProfit",
    "operating_profit": "opProfit",
    "ebitda": "ebitda",
    "depreciation": "depreciation",
    "pbt": "pbt",
    "tax": "tax",
    "profit": "profit",
    "netProfit": "profit",
    "net_profit": "profit",
    "finCost": "finCost",
    "finIncome": "finIncome",
    "interestExp": "interestExp",
    "forex": "forex",
    # Balance Sheet
    "totalAssets": "totalAssets",
    "total_assets": "totalAssets",
    "totalLiabilities": "totalLiabilities",
    "total_liabilities": "totalLiabilities",
    "equity": "equity",
    "total_equity": "equity",
    "totalCA": "totalCA",
    "totalNCA": "totalNCA",
    "ppe": "ppe",
    "cash": "cash",
    "debt": "debt",
    "ltBorrowings": "ltBorrowings",
    "stBorrowings": "stBorrowings",
    "ltBankLoans": "ltBankLoans",
    "inventories": "inventories",
    "tradeReceivables": "tradeReceivables",
}


# Hardcoded fallback (matches frontend useCurrencyConverter fallback).
_RATE_FALLBACK = {
    "USD": {
        2021: 10610.00, 2022: 11050.00, 2023: 11420.00,
        2024: 12650.91, 2025: 12576.41, 2026: 12200.00,
    },
    "EUR": {
        2021: 12520.00, 2022: 11600.00, 2023: 12330.00,
        2024: 13691.00, 2025: 14140.00, 2026: 14250.00,
    },
}


def _canon_metric(
    line_code: str | None, parent_code: str | None = None,
) -> str | None:
    """Map raw line_code to canonical metric. Returns None for unknown
    codes. Pack 7.54: falls back to parent_code for custom-mapped fields."""
    if line_code:
        direct = _PORTFOLIO_METRIC_ALIASES.get(line_code)
        if direct:
            return direct
        stripped = _PORTFOLIO_METRIC_ALIASES.get(line_code.strip())
        if stripped:
            return stripped
    if parent_code:
        direct = _PORTFOLIO_METRIC_ALIASES.get(parent_code)
        if direct:
            return direct
        return _PORTFOLIO_METRIC_ALIASES.get(parent_code.strip())
    return None


@dataclass
class FinancialsPortfolioService:
    async def summary(
        self,
        db: AsyncSession,
        user: User,
        *,
        standard: str,
        years: str,
        currency: str,
    ) -> dict:
        std = standard.upper()
        if std not in ("IFRS", "NSBU"):
            raise HTTPException(400, "standard must be IFRS or NSBU")
        cur = currency.upper()
        if cur not in ("UZS", "USD", "EUR"):
            raise HTTPException(400, "currency must be UZS, USD or EUR")
        try:
            year_list = sorted({
                int(y.strip()) for y in years.split(",") if y.strip()
            })
        except ValueError:
            raise HTTPException(400, "years must be comma-separated integers")
        if not year_list:
            raise HTTPException(400, "at least one year required")
        if len(year_list) > 12:
            raise HTTPException(400, "max 12 years per request")

        repo = FinancialsRepository(db)
        allowed_set = await allowed_company_ids(db, user)

        # Three-tier currency match: exact → case-insensitive → no filter
        rows = await repo.query_portfolio_rows(
            standard=std, year_list=year_list, currency=cur,
            allowed_company_ids=allowed_set,
        )
        currency_filter_relaxed: str | None = None
        if not rows:
            rows = await repo.query_portfolio_rows(
                standard=std, year_list=year_list,
                currency=f"upper:{cur}",
                allowed_company_ids=allowed_set,
            )
            if rows:
                currency_filter_relaxed = "case-insensitive"
        if not rows:
            log.warning(
                "[portfolio_summary] No reports matched currency=%s for "
                "standard=%s years=%s — falling back to no-currency filter",
                cur, std, year_list,
            )
            rows = await repo.query_portfolio_rows(
                standard=std, year_list=year_list, currency=None,
                allowed_company_ids=allowed_set,
            )
            if rows:
                currency_filter_relaxed = "removed"

        sec_map = await repo.list_sectors_map()
        rates_by_year = await repo.list_year_registry_rates()

        def _rate_for(year_v: int, currency_v: str) -> float:
            if currency_v == "UZS":
                return 1.0
            registry = rates_by_year.get(year_v, {})
            v = registry.get(currency_v, 0.0)
            if v and v > 0:
                return v
            fb = _RATE_FALLBACK.get(currency_v, {})
            if year_v in fb:
                return fb[year_v]
            if fb:
                nearest = min(fb.keys(), key=lambda y: abs(y - year_v))
                return fb[nearest]
            return 0.0

        # Aggregate
        by_co: dict[str, dict] = {}
        for r in rows:
            if r.val is None:
                continue
            canon = _canon_metric(r.code, getattr(r, "parent_code", None))
            if not canon:
                continue
            try:
                value_raw = float(r.val) * 1_000_000_000.0
            except (TypeError, ValueError):
                continue

            row_currency = (r.rcurrency or "UZS").upper()
            row_year = int(r.year)
            if row_currency != "UZS":
                inverse_rate = _rate_for(row_year, row_currency)
                if inverse_rate > 0:
                    value_raw = value_raw * inverse_rate
                else:
                    continue
            if cur != "UZS":
                target_rate = _rate_for(row_year, cur)
                if target_rate > 0:
                    value_raw = value_raw / target_rate
                else:
                    continue

            co_key = r.co_code
            co = by_co.get(co_key)
            if co is None:
                co = {
                    "company_id": str(r.co_id),
                    "company_code": co_key,
                    "company_name": r.co_name,
                    "company_name_short": r.co_short,
                    "sector_code": (sec_map.get(r.sector_id) or "other"),
                    "by_year": {},
                }
                by_co[co_key] = co
            ydict = co["by_year"].setdefault(int(r.year), {})
            existing = ydict.get(canon)
            if existing is None or abs(value_raw) > abs(float(existing)):
                ydict[canon] = value_raw

        items = list(by_co.values())
        items.sort(key=lambda x: x["company_code"] or "")

        total_companies = await repo.count_companies(
            allowed_company_ids=allowed_set,
        )

        totals_by_year: dict[int, dict[str, float]] = {}
        for it in items:
            for y, metrics in it["by_year"].items():
                t = totals_by_year.setdefault(y, {})
                for m, v in metrics.items():
                    if v is None:
                        continue
                    t[m] = t.get(m, 0.0) + float(v)

        coverage: dict[str, int] = {
            "companies_total": total_companies,
            "with_revenue_any_year": sum(
                1 for it in items
                if any("revenue" in y for y in it["by_year"].values())
            ),
        }
        for y in year_list:
            coverage[f"with_data_{y}"] = sum(
                1 for it in items if y in it["by_year"]
            )

        return {
            "standard": std,
            "currency": cur,
            "years": year_list,
            "items": items,
            "portfolio_totals_by_year": totals_by_year,
            "coverage": coverage,
            "currency_filter_relaxed": currency_filter_relaxed,
        }
