"""Macro scenarios and per-year overrides (Pack 7.40 + 7.40.2 hotfix).

Two tables that live under /admin/system-config — Сценарии и прогнозы tab.

  macro_scenarios               — named scenario (Base / Optimistic / Pessimistic / custom)
  macro_scenario_overrides      — per-year macro overrides for each scenario

Override semantics:
  • If a field is NULL → fall back to year_registry value for that year
  • If a field is set → use this value instead of the registry value

Scope: scenarios are ISOLATED to the admin tab. They do NOT affect the
global Financials / Tax / EE / BP / Dashboard blocks (those continue to
show fact). Only future /forecast endpoint (Pack 7.43) will consume them.

Write access: admin only (is_owner OR has 'admin.users' permission).
Read access: any authenticated user.

7.40.2 hotfix: switched from forward-reference Mapped["UUID"] to real
PyUUID / PG_UUID imports — SQLAlchemy 2.0 cannot resolve a forward-ref
in `Mapped[...]` at runtime when only TYPE_CHECKING-imported, causing
the model module to fail to import → the router was silently skipped
by main.py's try/except, producing the visible "Not Found" 404.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID as PyUUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class MacroScenario(Base, UUIDMixin, TimestampMixin):
    """Named macro scenario.

    Seeded with 3 defaults: base / optimistic / pessimistic.
    Admins can create unlimited custom scenarios.
    """

    __tablename__ = "macro_scenarios"
    __table_args__ = (
        UniqueConstraint("code", name="uq_macro_scenarios_code"),
    )

    code: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    name_ru: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color_hex: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_seeded: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    overrides: Mapped[list[MacroScenarioOverride]] = relationship(
        "MacroScenarioOverride",
        back_populates="scenario",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MacroScenarioOverride(Base, TimestampMixin):
    """Per-year override of macro indicators for a single scenario.

    Composite PK (scenario_id, year). Any NULL field means «use base».
    """

    __tablename__ = "macro_scenario_overrides"

    scenario_id: Mapped[PyUUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("macro_scenarios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)

    inflation_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    cb_rate_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    gdp_growth_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    usd_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    eur_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    uz_budget_trln: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scenario: Mapped[MacroScenario] = relationship(
        "MacroScenario", back_populates="overrides"
    )
