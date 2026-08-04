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
    # Дебиторская / кредиторская задолженность (НСБУ ввод пользователя)
    "accountsReceivable": "accountsReceivable",
    "accounts_receivable": "accountsReceivable",
    "accountsPayable": "accountsPayable",
    "accounts_payable": "accountsPayable",
    # Cash Flow — аудит P2: МСФО-редактор ПИШЕТ эти коды в financial_lines,
    # но алиасов не было → вкладка CF жила только на HLF-инъекции. Теперь
    # канон читается первым, HLF остаётся фолбэком (инъекция не перетирает).
    "cfo": "cfo",
    "cfi": "cfi",
    "cff": "cff",
    "dividendsPaid": "dividendsPaid",
    "dividends_paid": "dividendsPaid",
    "freeCashFlow": "freeCashFlow",
    "free_cash_flow": "freeCashFlow",
    "cfi_capex": "cfi_capex",
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


# HLF cash-flow row matchers (lowercased substring → canonical metric).
# Cash-flow metrics live in `company.extra["hlf"]`, NOT in financial_lines,
# so the portfolio aggregation above never picks them up. We extract them
# here. The cashflow section totals carry `type == "subtotal"` (e.g.
# "Operating Cash Flow"); we prefer those, falling back to any matching
# "line". Order within each list = priority. NB the real DB labels are
# "Operating/Investing/Financing Cash Flow" — the frontend `extractHlfCash`
# only matched "cash from investing/financing" and so MISSED CFI/CFF.
_HLF_CASH_MATCHERS: dict[str, list[str]] = {
    "cfo": [
        "operating cash flow", "net cash from operating",
        "cash from operating", "cash generated from operating",
        "cash flows from operating", "поток от операц", "операционн",
    ],
    "cfi": [
        "investing cash flow", "net cash used in investing",
        "cash from investing", "cash flows from investing",
        "поток от инвест", "инвестиционн",
    ],
    "cff": [
        "financing cash flow", "net cash from financing",
        "cash from financing", "cash flows from financing",
        "поток от фин", "финансиров",
    ],
    "dividendsPaid": [
        "dividends paid", "тўланган дивиденд",
        "дивиденды выпл", "дивиденды упл", "дивиденд",
    ],
}

_HLF_SKIP_ROW_TYPES = {"section_header", "subheader"}


def _extract_hlf_cash(hlf: dict | None) -> dict[int, dict[str, float]]:
    """Pull CFO / CFI / CFF / dividends paid out of stored HLF JSON.

    Returns ``{year: {"cfo":.., "cfi":.., "cff":.., "dividendsPaid":..}}``
    in the HLF's own units (bln UZS — see service comment) with None values
    skipped. Index ``i`` of a row's ``values`` maps to the *section's own*
    ``years`` array (the top-level ``hlf["years"]`` is a union across all
    sections and can be longer than a given section's value vectors, so it
    must NOT be used for alignment).

    For each metric we prefer the first matching ``subtotal`` row (the
    section total) and fall back to the first matching ``line`` row.
    """
    out: dict[int, dict[str, float]] = {}
    if not isinstance(hlf, dict):
        return out
    sections = hlf.get("sections")
    if not isinstance(sections, list):
        return out
    top_years = hlf.get("years")

    for metric, needles in _HLF_CASH_MATCHERS.items():
        chosen_row: dict | None = None
        chosen_years: list | None = None
        best_priority = -1  # higher needle index = lower priority
        best_is_subtotal = False

        for sec in sections:
            if not isinstance(sec, dict):
                continue
            rows = sec.get("rows")
            if not isinstance(rows, list):
                continue
            sec_years = sec.get("years")
            if not isinstance(sec_years, list) or not sec_years:
                sec_years = top_years if isinstance(top_years, list) else None
            for row in rows:
                if not isinstance(row, dict):
                    continue
                rtype = str(row.get("type") or "")
                if rtype in _HLF_SKIP_ROW_TYPES:
                    continue
                label = str(row.get("label") or "").lower()
                mapping = str(row.get("mapping") or "").lower()
                for prio, needle in enumerate(needles):
                    if needle in label or needle in mapping:
                        is_subtotal = rtype == "subtotal"
                        # Prefer subtotal over line; among equal kinds prefer
                        # the earlier (higher-priority) needle. Keep the first
                        # acceptable match (don't override once chosen).
                        better = False
                        if chosen_row is None:
                            better = True
                        elif is_subtotal and not best_is_subtotal:
                            better = True
                        if better:
                            chosen_row = row
                            chosen_years = sec_years
                            best_priority = prio
                            best_is_subtotal = is_subtotal
                        break
            # stop scanning sections once we have a subtotal match
            if chosen_row is not None and best_is_subtotal:
                break

        if chosen_row is None or not isinstance(chosen_years, list):
            continue
        values = chosen_row.get("values")
        if not isinstance(values, list):
            continue
        for idx, yr in enumerate(chosen_years):
            if idx >= len(values):
                break
            raw = values[idx]
            if raw is None:
                continue
            try:
                fv = float(raw)
                yi = int(yr)
            except (TypeError, ValueError):
                continue
            out.setdefault(yi, {})[metric] = fv

    return out


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
                # Аудит P1: масштаб — из unit_scale отчёта (канон 1e9 = млрд),
                # а не хардкод ×1e9: будущие отличные масштабы не соврут.
                value_raw = float(r.val) * float(getattr(r, "scale", None) or 1_000_000_000)
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

        # ─── Единственный источник — канонический срез редактора ───────
        # Раньше здесь CFO/CFI/CFF/дивиденды добирались из company.extra.hlf,
        # когда их не было в financial_lines. После импорта HLF v5 канон полон
        # (сверка: в блобах 271 значение, вне канона — только нули и три
        # значения, перенесённые отдельно), поэтому фолбэк снят: цифра на
        # экране не должна зависеть от того, какой из двух источников успел.
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
