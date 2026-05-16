"""Procurement analytics: contracts, KTRU products, price clustering."""
from typing import Optional
from decimal import Decimal
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class ProcurementContract(Base, UUIDMixin, TimestampMixin):
    """A signed procurement contract (top-level header)."""

    __tablename__ = "procurement_contracts"

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    contract_no: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    contract_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    supplier_inn: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    procurement_method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # tender | direct | electronic | etc.

    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)

    year: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)

    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ProcurementData(Base, UUIDMixin, TimestampMixin):
    """A line item / closure of a procurement contract.
    The unit of analysis for price clustering and benchmarking."""

    __tablename__ = "procurement_data"

    contract_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procurement_contracts.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    # KTRU = Каталог товаров, работ, услуг
    product_code: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    product_name: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Sub-product after price-clustering (k-means buckets on log-scale)
    sub_product_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_clusters.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 2), nullable=True)

    closure_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)

    supplier_inn: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Quality flag — `is_dirty` excluded from KPI aggregates
    # (dirty = product_code aggregates physically different goods)
    is_dirty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    dirty_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ProductCluster(Base, UUIDMixin, TimestampMixin):
    """A sub-product cluster produced by the price-clustering algorithm
    (log-scale bucketing, bs=0.5, k_cap=7, no merge step,
     <200% spread guarantee → 314 clean sub-products in current dataset)."""

    __tablename__ = "product_clusters"

    product_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    cluster_index: Mapped[int] = mapped_column(Integer, nullable=False)
    cluster_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    min_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    max_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    median_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    mean_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Log-scale bucket parameters — the algorithm seed
    bucket_size: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.5"), nullable=False)
    k_cap: Mapped[int] = mapped_column(Integer, default=7, nullable=False)

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ProcurementBenchmark(Base, UUIDMixin, TimestampMixin):
    """Per-product benchmark: median is the correct anchor (NOT weighted mean —
    see lessons-learned: weighted mean as benchmark forces zero average deviation)."""

    __tablename__ = "procurement_benchmarks"

    product_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sub_product_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_clusters.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    year: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)

    median_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    p25_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    p75_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    computed_at: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)


class ProcurementClosure(Base, UUIDMixin, TimestampMixin):
    """A single closed procurement transaction — what /api/procurement/aggregate
    consumes for paCompute()-style analytics.

    Denormalized per row: stores the unit_price the company actually paid plus
    the market_avg benchmark + computed deviation_pct, so the endpoint can
    aggregate KPIs/rating/categories without re-running clustering on every
    request. is_clean / is_dirty mirror the monolith's dirty-product-code
    quality flag (excluded from KPI aggregates).
    """

    __tablename__ = "procurement_closures"

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    year: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    closure_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # KTRU classification
    category_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    product_code: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    product_name: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Prices
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    market_avg: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    deviation_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)

    # Volume
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 2), nullable=True)
    saved_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 2), nullable=True)

    # Supplier
    supplier_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    supplier_inn: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)

    # Source meta
    contract_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    lot_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    purchase_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)

    # Quality flags
    is_clean: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_dirty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    dirty_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


Index("ix_proc_data_year_dirty", ProcurementData.year, ProcurementData.is_dirty)
Index("ix_proc_data_supplier_year", ProcurementData.supplier_inn, ProcurementData.year)
Index("ix_proc_clusters_code_idx", ProductCluster.product_code, ProductCluster.cluster_index)
