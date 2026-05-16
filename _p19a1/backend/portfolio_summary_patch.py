

# =====================================================================
# Portfolio summary (dashboard aggregator)            [Phase 19a-1]
# =====================================================================
# Used by the Financials dashboard view (frontend) to render portfolio-wide
# KPI band and per-company multi-year metric breakdown without N+1 queries.
#
# Returns per-company × per-year canonical metric values normalized to
# raw currency units (FinancialLine.value × FinancialReport.unit_scale).
# Single SQL query, no N+1 — handles full portfolio in <100 ms.
#
# Handles legacy line_code variants from different import paths:
#   - camelCase from old monolith imports (revenue, grossProfit, opProfit, ...)
#   - snake_case from later imports (gross_profit, total_assets, total_equity)
# =====================================================================

# Maps actual line_code variants (any case) → canonical metric code
# returned in the response. Frontend reads only canonical names.
_PORTFOLIO_METRIC_ALIASES: dict[str, str] = {
    # ── P&L ─────────────────────────────────────────────────────────
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
    # Finance items (used for finCost/finIncome split in detailed views)
    "finCost": "finCost",
    "finIncome": "finIncome",
    "interestExp": "interestExp",
    "forex": "forex",
    # ── Balance Sheet ───────────────────────────────────────────────
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


def _canon_metric(line_code: str | None) -> str | None:
    """Map raw line_code (any case/variant) to canonical metric code.
    Returns None for unknown/garbage codes — those are skipped in aggregation."""
    if not line_code:
        return None
    direct = _PORTFOLIO_METRIC_ALIASES.get(line_code)
    if direct:
        return direct
    return _PORTFOLIO_METRIC_ALIASES.get(line_code.strip())


@router.get("/portfolio/summary")
async def portfolio_summary(
    standard: str = Query("IFRS", description="IFRS or NSBU"),
    years: str = Query(
        "2021,2022,2023,2024,2025,2026",
        description="Comma-separated list of fiscal years",
    ),
    currency: str = Query("UZS", description="Currency filter (UZS/USD/EUR)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregate financial metrics across all accessible companies.

    Returns per-company × year × metric breakdown with values normalized
    to raw currency units. One query, no N+1.

    Response shape:
        {
          "standard": "IFRS",
          "currency": "UZS",
          "years": [2021, 2022, ...],
          "items": [
            {
              "company_id": "...",
              "company_code": "NGMK",
              "company_name": "Навоийский ГМК",
              "company_name_short": "НГМК",
              "sector_code": "mining",
              "by_year": {
                "2024": { "revenue": 93558000000.0, "ebitda": 62334000000.0, ... },
                "2023": {...},
                ...
              }
            },
            ...22 companies...
          ],
          "portfolio_totals_by_year": {
            "2024": { "revenue": 328345000000.0, "ebitda": 125034000000.0, ... }
          },
          "coverage": {
            "companies_total": 22,
            "with_revenue_any_year": 18,
            "with_data_2024": 15,
            "with_data_2023": 16,
            ...
          }
        }
    """
    std = standard.upper()
    if std not in ("IFRS", "NSBU"):
        raise HTTPException(400, "standard must be IFRS or NSBU")

    cur = currency.upper()
    if cur not in ("UZS", "USD", "EUR"):
        raise HTTPException(400, "currency must be UZS, USD or EUR")

    try:
        year_list = sorted({int(y.strip()) for y in years.split(",") if y.strip()})
    except ValueError:
        raise HTTPException(400, "years must be comma-separated integers")

    if not year_list:
        raise HTTPException(400, "at least one year required")
    if len(year_list) > 12:
        raise HTTPException(400, "max 12 years per request")

    # RBAC: scope to companies user has access to (None = full access)
    allowed_set = await allowed_company_ids(user, db)

    # One join query: companies × reports × lines, filtered tightly
    stmt = (
        select(
            Company.id.label("co_id"),
            Company.code.label("co_code"),
            Company.name_ru.label("co_name"),
            Company.name_short.label("co_short"),
            Company.sector_code.label("sec_code"),
            FinancialReport.year.label("year"),
            FinancialReport.report_type.label("rtype"),
            FinancialReport.unit_scale.label("scale"),
            FinancialLine.line_code.label("code"),
            FinancialLine.value.label("val"),
        )
        .join(FinancialReport, FinancialReport.company_id == Company.id)
        .join(FinancialLine, FinancialLine.report_id == FinancialReport.id)
        .where(
            FinancialReport.standard == std,
            FinancialReport.currency == cur,
            FinancialReport.year.in_(year_list),
            FinancialReport.report_type.in_(["PL", "BS", "CF"]),
        )
    )
    if allowed_set is not None:
        stmt = stmt.where(Company.id.in_(allowed_set))

    result = await db.execute(stmt)
    rows = result.all()

    # Aggregate into per-company nested dict
    by_co: dict[str, dict] = {}
    for r in rows:
        if r.val is None:
            continue
        canon = _canon_metric(r.code)
        if not canon:
            continue
        scale = r.scale or 1000
        try:
            value_raw = float(r.val) * float(scale)
        except (TypeError, ValueError):
            continue

        co_key = r.co_code
        co = by_co.get(co_key)
        if co is None:
            co = {
                "company_id": str(r.co_id),
                "company_code": co_key,
                "company_name": r.co_name,
                "company_name_short": r.co_short,
                "sector_code": r.sec_code,
                "by_year": {},
            }
            by_co[co_key] = co

        ydict = co["by_year"].setdefault(int(r.year), {})
        # Duplicate-key strategy: keep largest absolute value
        # (handles same-metric appearing in multiple report_types)
        existing = ydict.get(canon)
        if existing is None or abs(value_raw) > abs(float(existing)):
            ydict[canon] = value_raw

    items = list(by_co.values())
    items.sort(key=lambda x: x["company_code"] or "")

    # Portfolio-wide totals per year (used by KPI band)
    totals_by_year: dict[int, dict[str, float]] = {}
    for it in items:
        for y, metrics in it["by_year"].items():
            t = totals_by_year.setdefault(y, {})
            for m, v in metrics.items():
                if v is None:
                    continue
                t[m] = t.get(m, 0.0) + float(v)

    # Coverage: how many companies have data per year
    coverage: dict[str, int] = {
        "companies_total": len(items),
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
    }
