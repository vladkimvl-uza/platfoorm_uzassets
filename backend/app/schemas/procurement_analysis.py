"""Procurement Analysis schemas — types for the BETA tab «Анализ закупочной деятельности».

Mirrors the monolith `paCompute()` aggregation 1:1.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# Closure (purchase / contract)
# =====================================================================

class ClosureRow(BaseModel):
    """A single procurement closure (контракт / закупка) row."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    company_name: Optional[str] = None
    company_color: Optional[str] = None
    company_sector: Optional[str] = None

    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_unit: Optional[str] = None        # ед. измерения

    product_code: Optional[str] = None         # KTRU code
    sub_product_code: Optional[str] = None     # cluster code (after price clustering)
    product_name: Optional[str] = None

    supplier: Optional[str] = None
    unit_price: Decimal
    market_avg: Decimal                         # benchmark median for the cluster
    volume: Decimal

    deviation_pct: float                        # (unit_price - market_avg) / market_avg * 100
    deviation_abs: Optional[Decimal] = None     # absolute UZS overpayment

    spread_pct: Optional[float] = None          # cluster spread for QC
    is_dirty: bool = False                      # excluded from KPI aggregates

    contract_date: Optional[date] = None
    year: Optional[int] = None


# =====================================================================
# Per-category deviation (within a company)
# =====================================================================

class CategoryDeviation(BaseModel):
    """A single category's deviation within a company's procurement."""
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_short: Optional[str] = None
    sum_dev: Decimal                            # absolute overpayment in UZS
    sum_ref: Decimal                            # benchmark spend
    deviation_pct: float                        # weighted-avg deviation
    closure_count: int


# =====================================================================
# Company rating row
# =====================================================================

class CompanyRatingRow(BaseModel):
    """One company's row in the rating table.

    Mirrors monolith `co` object in `paCompute().rating[]`.
    """
    company_id: UUID
    company_code: Optional[str] = None
    company_name: str
    company_color: Optional[str] = None
    company_sector: Optional[str] = None

    company_deviation: float                    # weighted-avg deviation %
    sum_dev: Decimal                             # net overpayment (can be negative for savings)
    sum_ref: Decimal                             # benchmark spend
    above_count: int                             # # categories where deviation > 0
    cat_count: int                               # # categories with data
    cat_dev: List[CategoryDeviation] = Field(default_factory=list)

    best_cats: List[CategoryDeviation] = Field(default_factory=list)   # top-3 negative dev
    worst_cats: List[CategoryDeviation] = Field(default_factory=list)  # top-3 positive dev

    rank: int = 0


# =====================================================================
# Category metadata (the 15 fixed categories)
# =====================================================================

class CategoryMeta(BaseModel):
    """One of the 15 procurement categories (fixed list)."""
    id: int
    name: str
    short: str
    icon: Optional[str] = None


# =====================================================================
# Aggregate response (the BETA tab payload)
# =====================================================================

class ProcurementKpis(BaseModel):
    total_companies: int
    clean_companies: int                         # companies with at least 1 clean closure
    total_closures: int
    clean_closures: int                          # closures excluding `is_dirty`
    total_overpay_uzs: Decimal                   # sum of positive deviations
    above_market_pct: float                      # % companies with avg deviation > 0
    median_deviation_pct: float                  # portfolio-wide median


class ProcurementAggregate(BaseModel):
    """Top-level response of /procurement/aggregate.

    Mirrors monolith `paCompute()` output 1:1.
    """
    year: Optional[int] = None
    sector_code: Optional[str] = None

    kpis: ProcurementKpis
    categories: List[CategoryMeta] = Field(default_factory=list)
    rating: List[CompanyRatingRow] = Field(default_factory=list)
    purchases: List[ClosureRow] = Field(default_factory=list)

    available_years: List[int] = Field(default_factory=list)
    sectors: List[Dict[str, str]] = Field(default_factory=list)   # [{code, label}]
    generated_at: datetime
