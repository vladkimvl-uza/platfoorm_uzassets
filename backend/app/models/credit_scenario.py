"""
Credit-portfolio scenarios — Pack 7.41.

Three tables for the credit scenarios admin section:

  credit_portfolio_scenarios  — one row per macro scenario (base/optimistic/pessimistic/custom)
                                with credit-specific assumptions (forgiveness, refinance,
                                default rate, acceleration) + risk formula.

  credit_portfolio_loan_scenarios  — per-loan overrides INSIDE a scenario
                                (forgiveness/rate/term/default-probability/notes).
                                Unique on (scenario_id, loan_id).

  credit_custom_indicators  — type-C custom indicators (full typization).

Decoupled from macro_scenarios via STRING key `macro_scenario_key` — works
whether or not macro_scenarios table exists. Pack 7.40 used keys like
"base", "optimistic", "pessimistic"; we mirror those plus allow custom.
"""
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID as PyUUID

from sqlalchemy import (
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# Allowed input types for custom indicators
CUSTOM_INDICATOR_INPUT_TYPES = ("number", "percentage", "currency", "text")
CUSTOM_INDICATOR_AGGREGATIONS = (
    "sum",
    "avg",
    "weighted_avg",
    "min",
    "max",
    "count",
)


# ============================================================================
# 1. CreditPortfolioScenario — main scenario row
# ============================================================================
class CreditPortfolioScenario(Base, UUIDMixin, TimestampMixin):
    """Credit assumptions for one macro scenario.

    Pairs with a macro_scenario via string key (loosely coupled). The 4 base
    assumptions + risk formula apply portfolio-wide. Per-loan overrides go
    in CreditPortfolioLoanScenario.
    """

    __tablename__ = "credit_portfolio_scenarios"

    # Free-form key linking to macro_scenarios.key (e.g. "base", "optimistic",
    # "pessimistic", "stress_2027"). Unique so each macro scenario has
    # exactly one credit profile.
    macro_scenario_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # Display name (for custom scenarios that don't have a macro twin)
    name_ru: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 4 base assumptions (all as decimal fractions or percentage-points)
    # Forgiveness: fraction of state-loan principal written off (0.15 = 15%)
    state_forgiveness_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    # Refinance rate delta in percentage points (negative = rate goes down)
    refinance_rate_delta_pp: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    # Expected default rate, fraction (0.02 = 2%)
    default_rate_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    # Payment acceleration, fraction (0.10 = pay 10% earlier than schedule)
    repayment_acceleration_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True
    )

    # Custom Basel-style or other formula. Empty = use default formula.
    risk_formula_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Recovery rate by lender type. JSONB shape:
    #   {"state": 0.75, "local": 0.50, "foreign": 0.35, "bond": 0.40,
    #    "guaranteed_override": 0.85}
    risk_rr_by_lender: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # Catch-all for future extensions
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Auditing
    created_by_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


# ============================================================================
# 2. CreditPortfolioLoanScenario — per-loan override inside a scenario
# ============================================================================
class CreditPortfolioLoanScenario(Base, UUIDMixin, TimestampMixin):
    """Override for one specific loan inside one specific scenario.

    All fields nullable — only set what differs from the portfolio-wide
    assumption. NULL means "inherit from scenario".
    """

    __tablename__ = "credit_portfolio_loan_scenarios"

    scenario_id: Mapped[PyUUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credit_portfolio_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    loan_id: Mapped[PyUUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cp_loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Per-loan overrides (all nullable)
    forgiveness_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    rate_override: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    rescheduled_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    default_probability: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    partial_repayment_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True
    )

    # Custom params as JSONB (e.g. "moratorium", "default 50%", "junior note")
    custom_params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("scenario_id", "loan_id", name="uq_loan_scenario"),
    )


# ============================================================================
# 3. CreditCustomIndicator — type-C custom indicator config
# ============================================================================
class CreditCustomIndicator(Base, UUIDMixin, TimestampMixin):
    """Type-C fully-typed custom indicator config.

    Stored globally (not per-scenario) — the indicator definition is shared,
    only its `current_value` may vary if admin manually sets it. Auto-computed
    indicators get value via formula_text + source_metric.
    """

    __tablename__ = "credit_custom_indicators"

    # Programmatic key — use snake_case, English (e.g. "yuan_refinance_pct")
    key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # Display name in Russian
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)

    # number / percentage / currency / text
    input_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # Bounds for input validation
    min_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 6), nullable=True
    )
    max_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 6), nullable=True
    )

    # Manual or auto-computed value (one of two; both may be set)
    current_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 6), nullable=True
    )

    # Optional auto-compute formula. If set, current_value is computed at
    # read time; if blank, current_value is admin-entered.
    formula_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Aggregation when applying the formula across rows (sum/avg/weighted_avg/...)
    aggregation: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Free-form description of WHERE the metric comes from (e.g.
    # "cp_loans.debt_usd WHERE currency='CNY'")
    source_metric: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Simple-language explanation for users
    tooltip_ru: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Auditing
    created_by_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
