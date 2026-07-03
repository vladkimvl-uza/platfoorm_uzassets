"""Pydantic schemas for Companies & Sectors admin v2 (Pack 9.2)."""
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ─── Badges ──────────────────────────────────────────────────

class Badge(BaseModel):
    text: str = Field(min_length=1, max_length=8)
    color: str = Field(min_length=4, max_length=9)        # hex with optional alpha
    bg_color: Optional[str] = None                         # auto-derived if None
    position: Optional[str] = "right"                      # 'right' | 'corner'


# ─── Company (full read for admin) ───────────────────────────

class CompanyAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name_ru: str
    name_short: Optional[str] = None
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    legal_form: Optional[str] = None
    ownership_entity: Optional[str] = None
    inn: Optional[str] = None

    sector_id: Optional[UUID] = None
    sector_code: Optional[str] = None
    sector_name: Optional[str] = None

    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    ceo_name: Optional[str] = None
    employees_count: Optional[int] = None
    founded_year: Optional[int] = None

    is_active: bool = True
    is_custom: bool = False
    sort_order: int = 0

    # Advanced fields
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    badges: Optional[list[Badge]] = None
    status: Optional[str] = "active"

    is_pinned: bool = False
    include_in_rollups: bool = True
    module_flags: Optional[dict[str, bool]] = None

    parent_id: Optional[UUID] = None
    parent_code: Optional[str] = None
    portfolio_start_year: Optional[int] = None

    primary_currency: str = "UZS"
    fy_start_month: int = 1
    track_inflation: bool = True

    bloomberg_ticker: Optional[str] = None
    isin: Optional[str] = None
    lei: Optional[str] = None

    tags: Optional[list[str]] = None
    aliases: Optional[list[str]] = None

    children_count: int = 0
    year_overrides_count: int = 0


class CompanyAdminUpdate(BaseModel):
    """Partial update — all fields optional."""
    name_ru: Optional[str] = None
    name_short: Optional[str] = None
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    legal_form: Optional[str] = None
    ownership_entity: Optional[str] = None
    inn: Optional[str] = None
    sector_code: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    ceo_name: Optional[str] = None
    employees_count: Optional[int] = None
    founded_year: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    badges: Optional[list[Badge]] = None
    status: Optional[str] = None

    is_pinned: Optional[bool] = None
    include_in_rollups: Optional[bool] = None
    module_flags: Optional[dict[str, bool]] = None

    parent_code: Optional[str] = None  # use code to avoid UUID coupling
    portfolio_start_year: Optional[int] = None

    primary_currency: Optional[str] = None
    fy_start_month: Optional[int] = None
    track_inflation: Optional[bool] = None

    bloomberg_ticker: Optional[str] = None
    isin: Optional[str] = None
    lei: Optional[str] = None

    tags: Optional[list[str]] = None
    aliases: Optional[list[str]] = None


class CompanyAdminCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name_ru: str = Field(min_length=1, max_length=255)
    name_short: Optional[str] = None
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    sector_code: Optional[str] = None
    legal_form: Optional[str] = None
    ownership_entity: Optional[str] = None
    inn: Optional[str] = None
    founded_year: Optional[int] = None
    parent_code: Optional[str] = None
    portfolio_start_year: Optional[int] = None
    status: Optional[str] = "active"


# ─── Year overrides ──────────────────────────────────────────

ExclusionReason = Literal[
    "restructuring", "m_a", "divestment", "not_in_portfolio", "audit", "other"
]


class CompanyYearOverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    year: int
    is_hidden: bool
    name_override: Optional[str] = None
    sector_override_id: Optional[UUID] = None
    sector_override_code: Optional[str] = None
    exclusion_reason: Optional[str] = None
    notes: Optional[str] = None


class CompanyYearOverrideUpsert(BaseModel):
    year: int
    is_hidden: bool = False
    name_override: Optional[str] = None
    sector_override_code: Optional[str] = None
    exclusion_reason: Optional[ExclusionReason] = None
    notes: Optional[str] = None


class CompanyYearOverridesBulk(BaseModel):
    """Replace all year overrides for one company atomically."""
    overrides: list[CompanyYearOverrideUpsert] = Field(default_factory=list)


# ─── Sector ──────────────────────────────────────────────────

class SectorAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name_ru: str
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    color_hex: Optional[str] = None
    color_secondary: Optional[str] = None
    icon_name: Optional[str] = None
    short_badge: Optional[str] = None
    sort_order: int = 0
    aliases: Optional[list[str]] = None
    companies_count: int = 0


class SectorAdminUpdate(BaseModel):
    name_ru: Optional[str] = None
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    color_hex: Optional[str] = None
    color_secondary: Optional[str] = None
    icon_name: Optional[str] = None
    short_badge: Optional[str] = None
    sort_order: Optional[int] = None
    aliases: Optional[list[str]] = None


class SectorAdminCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name_ru: str = Field(min_length=1, max_length=255)
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    color_hex: Optional[str] = "#7F77DD"
    color_secondary: Optional[str] = None
    icon_name: Optional[str] = None
    short_badge: Optional[str] = None
    sort_order: int = 0


# ─── Hierarchy tree ──────────────────────────────────────────

class CompanyTreeNode(BaseModel):
    id: UUID
    code: str
    name_short: Optional[str]
    name_ru: str
    sector_code: Optional[str] = None
    primary_color: Optional[str] = None
    badges: Optional[list[Badge]] = None
    status: Optional[str] = None
    children: list["CompanyTreeNode"] = Field(default_factory=list)


CompanyTreeNode.model_rebuild()


# ─── Bulk operations ─────────────────────────────────────────

class TranslateRequest(BaseModel):
    """AI-translate company names from RU → UZ/EN."""
    name_ru: str
    target_langs: list[Literal["uz", "en"]] = Field(default_factory=lambda: ["uz", "en"])


class TranslateResponse(BaseModel):
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
