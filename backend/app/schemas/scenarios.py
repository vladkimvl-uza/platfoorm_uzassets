"""Pydantic schemas for macro scenarios (Pack 7.40).

Maps between API requests/responses and the ORM models.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────
# Overrides (per-year)
# ─────────────────────────────────────────────────────────────────────

class ScenarioOverrideBase(BaseModel):
    """Read/write shape for one year's override values.

    All fields are optional. NULL/missing means «use year_registry base».
    """

    model_config = ConfigDict(from_attributes=True)

    year: int = Field(..., ge=2000, le=2100)
    inflation_pct: Optional[Decimal] = None
    cb_rate_pct: Optional[Decimal] = None
    gdp_growth_pct: Optional[Decimal] = None
    usd_rate: Optional[Decimal] = None
    eur_rate: Optional[Decimal] = None
    uz_budget_trln: Optional[Decimal] = None
    notes: Optional[str] = None


class ScenarioOverride(ScenarioOverrideBase):
    """API response shape (same as base — no extra fields)."""

    pass


class ScenarioOverrideUpsert(ScenarioOverrideBase):
    """PATCH payload for a single year's override.

    Use NULL to clear the override (fall back to base for that field).
    Omitting a field leaves it unchanged on the server.
    """

    pass


# ─────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────

class ScenarioBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., min_length=1, max_length=64)
    name_ru: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = None
    color_hex: Optional[str] = Field(None, max_length=9)
    sort_order: int = 0


class ScenarioCreate(ScenarioBase):
    """POST payload to create a new custom scenario."""

    pass


class ScenarioUpdate(BaseModel):
    """PATCH payload — all fields optional, only provided fields are written."""

    model_config = ConfigDict(from_attributes=True)

    name_ru: Optional[str] = Field(None, min_length=1, max_length=160)
    description: Optional[str] = None
    color_hex: Optional[str] = Field(None, max_length=9)
    sort_order: Optional[int] = None


class Scenario(ScenarioBase):
    """Full scenario read shape — includes id, is_seeded flag and overrides."""

    id: UUID
    is_seeded: bool
    overrides: List[ScenarioOverride] = Field(default_factory=list)
