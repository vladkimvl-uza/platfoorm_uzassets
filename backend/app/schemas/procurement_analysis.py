"""Procurement Analysis schemas — types for the BETA tab «Анализ закупочной деятельности».

Mirrors the legacy `paCompute()` aggregation 1:1.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 2026-05-26: MoneyDecimal сериализует Decimal как float в JSON, чтобы
# frontend получал числа а не строки (см. _types.py rationale).
from app.schemas._types import MoneyDecimal

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
    unit_price: MoneyDecimal
    market_avg: MoneyDecimal                    # benchmark median for the cluster
    volume: MoneyDecimal

    deviation_pct: float                        # (unit_price - market_avg) / market_avg * 100
    deviation_abs: Optional[MoneyDecimal] = None  # absolute UZS overpayment

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
    sum_dev: MoneyDecimal                            # absolute overpayment in UZS
    sum_ref: MoneyDecimal                            # benchmark spend
    deviation_pct: float                        # weighted-avg deviation
    closure_count: int


# =====================================================================
# Company rating row
# =====================================================================

class CompanyRatingRow(BaseModel):
    """One company's row in the rating table.

    Mirrors legacy `co` object in `paCompute().rating[]`.
    """
    company_id: UUID
    company_code: Optional[str] = None
    company_name: str
    company_color: Optional[str] = None
    company_sector: Optional[str] = None

    company_deviation: float                    # weighted-avg deviation %
    sum_dev: MoneyDecimal                             # net overpayment (can be negative for savings)
    sum_ref: MoneyDecimal                             # benchmark spend
    above_count: int                             # red closures count (dev ≥ +10%)
    cat_count: int                               # # categories with data
    cat_dev: list[CategoryDeviation] = Field(default_factory=list)

    best_cats: list[CategoryDeviation] = Field(default_factory=list)   # top-3 negative dev
    worst_cats: list[CategoryDeviation] = Field(default_factory=list)  # top-3 positive dev

    # legacy-compat fields (PaRatingPanel + PaLeaders ожидают эти)
    sum_overpay: MoneyDecimal = Decimal(0)       # Σ(positive deviations) — for sort
    sum_savings: MoneyDecimal = Decimal(0)       # Σ(negative deviations as positive)
    red_pct: float = 0.0                          # % closures with dev ≥ +10%
    yellow_pct: float = 0.0                       # % closures with dev 0..+10%
    green_pct: float = 0.0                        # % closures with dev < 0
    problem_cats: int = 0                         # # categories where avg dev > 10%
    total_count: int = 0                          # total non-dirty closures count

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
    unit: str = "ед"                            # default unit


# =====================================================================
# Product-level aggregation (contracts mode — used by PaCategoryGrid
# and PaPainPoints. Mirrors legacy data.productsByCode + cat.allProducts.)
# =====================================================================

class ProductAgg(BaseModel):
    code: str                                   # productCode (KTRU)
    root_code: str                              # KTRU root before "-XXXXX"
    name: str
    unit: str
    category_id: Optional[str] = None
    avg_price: float                            # median of unit_price across all buyers
    min_price: float
    max_price: float
    spread_pct: float                           # (max-min) / min * 100
    total_spend: float                          # Σ unit_price * volume
    unique_buyers: int                          # unique company_id count
    contract_count: int
    max_deviation_pct: float                    # max |unit_price - market_avg| / market_avg * 100
    quality_band: str = "clean"                 # 'clean' | 'wide' | 'dirty'
    cluster_index: int = 0
    total_clusters: int = 1
    cluster_label: str = ""


class CategoryAggregate(BaseModel):
    """Per-category aggregation (extends CategoryMeta with computed fields)."""
    id: int
    name: str
    short: str
    unit: str = "ед"
    all_products: list[ProductAgg] = Field(default_factory=list)
    clean_count: int = 0
    benchmark_product_count: int = 0
    clean_spread_min: Optional[float] = None
    clean_spread_max: Optional[float] = None


class ProcurementMeta(BaseModel):
    source: str                                 # 'procurementContracts' | 'priceListLegacy'


# =====================================================================
# Aggregate response (the BETA tab payload)
# =====================================================================

class ProcurementKpis(BaseModel):
    total_companies: int
    clean_companies: int                         # companies with at least 1 clean closure
    total_closures: int
    clean_closures: int                          # closures excluding `is_dirty`
    total_overpay_uzs: MoneyDecimal              # sum of positive deviations
    above_market_pct: float                      # % companies with avg deviation > 0
    median_deviation_pct: float                  # portfolio-wide median


class ProcurementAggregate(BaseModel):
    """Top-level response of /procurement/aggregate.

    Mirrors legacy `paCompute()` output 1:1.
    """
    year: Optional[int] = None
    sector_code: Optional[str] = None

    kpis: ProcurementKpis
    categories: list[CategoryMeta] = Field(default_factory=list)
    category_aggregates: list[CategoryAggregate] = Field(default_factory=list)
    products_by_code: dict[str, ProductAgg] = Field(default_factory=dict)
    rating: list[CompanyRatingRow] = Field(default_factory=list)
    purchases: list[ClosureRow] = Field(default_factory=list)

    available_years: list[int] = Field(default_factory=list)
    sectors: list[dict[str, str]] = Field(default_factory=list)   # [{code, label}]
    meta: ProcurementMeta = Field(default_factory=lambda: ProcurementMeta(source="procurementContracts"))
    generated_at: datetime
