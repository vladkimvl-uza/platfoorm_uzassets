"""
Pack 7.43 — Elasticity coefficients + Project financial effects.

Two simple, flexible models:

1. ElasticityCoefficient
   How much does metric M change when macro factor F changes by 1%?
   Scoped by (scenario_id?, company_id?). NULL scenario_id = global default.
   NULL company_id = sector-wide default.

2. ProjectFinancialEffect
   Expected delta of a specific project on revenue/ebitda/capex/opex
   in a specific year. Multiple effects per project (one per metric × year).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ─── Allowed macro factors (frozen list, validated in schemas) ───
MACRO_FACTORS = (
    "inflation_pct",      # уровень инфляции
    "cb_rate_pct",        # ставка ЦБ
    "usd_rate",           # курс USD/UZS
    "eur_rate",           # курс EUR/UZS
    "gdp_growth_pct",     # рост ВВП
    "oil_price_brent",    # цена нефти Brent
)

# ─── Allowed target metrics ───
TARGET_METRICS = (
    "revenue",        # выручка
    "ebitda",         # EBITDA
    "opex",           # операционные затраты
    "capex",          # капитальные затраты
    "debt_service",   # обслуживание долга
    "net_income",     # чистая прибыль
)


class ElasticityCoefficient(Base):
    """β-коэффициент: на сколько % изменится `target_metric` при изменении
    `macro_factor` на 1%.

    Скоупинг (приоритет от specific к general):
      1. (scenario_id, company_id) — самое специфичное: для этого предприятия в этом сценарии
      2. (scenario_id, NULL) — для всех предприятий в этом сценарии
      3. (NULL, company_id) — глобально для этого предприятия
      4. (NULL, NULL) — глобальный дефолт (обычно от сидов по секторам)
    """
    __tablename__ = "elasticity_coefficients"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("macro_scenarios.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    company_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    macro_factor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_metric: Mapped[str] = mapped_column(String(64), nullable=False)
    beta: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual",
    )  # "manual" | "seed_sector_default" | "imported"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "company_id", "macro_factor", "target_metric",
            name="uq_elasticity_scope",
        ),
        Index("ix_elasticity_macro_target", "macro_factor", "target_metric"),
    )


class ProjectFinancialEffect(Base):
    """Expected financial effect of a transformation project on a specific
    metric in a specific year.

    A project can have multiple effects:
      Project "Modernize plant X" effects:
        2026 revenue +50 млрд сум (ramp-up: 30%)
        2027 revenue +120 млрд сум (ramp-up: 70%)
        2028 revenue +180 млрд сум (full: 100%)
        2026 capex -10% (cost reduction)
    """
    __tablename__ = "project_financial_effects"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    effective_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    target_metric: Mapped[str] = mapped_column(String(64), nullable=False)

    # One of these two should be set; backend treats abs as priority
    delta_value_uzs_mln: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 2), nullable=True,
    )  # абсолютное изменение в млн сум
    delta_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 4), nullable=True,
    )  # ИЛИ изменение в % к base

    probability_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("100.00"),
    )  # вероятность достижения 0..100
    confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium",
    )  # "low" | "medium" | "high"

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "effective_year", "target_metric",
            name="uq_project_effect_year_metric",
        ),
        Index("ix_project_effect_year", "effective_year"),
    )
