"""Company catalog: 22 Uzbek SOEs across mining, oil/gas, energy, transport."""
from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Sector(Base, UUIDMixin, TimestampMixin):
    """Industry sector: mining, oil_gas, energy, transport, telecom, finance, etc."""

    __tablename__ = "sectors"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    name_uz: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name_en: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    color_hex: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ─── Pack 9.2: Advanced customization ───
    color_secondary: Mapped[Optional[str]]  = mapped_column(String(9),  nullable=True)
    icon_name:       Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)  # tabler icon code
    short_badge:     Mapped[Optional[str]]  = mapped_column(String(8),  nullable=True)  # e.g. MINE
    aliases:         Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    companies: Mapped[List["Company"]] = relationship(back_populates="sector", foreign_keys="[Company.sector_id]")


class Direction(Base, UUIDMixin, TimestampMixin):
    """Strategic direction / transformation pillar
    (e.g. operational efficiency, ESG, digitalization)."""

    __tablename__ = "directions"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    name_uz: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name_en: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    companies: Mapped[List["CompanyDirection"]] = relationship(back_populates="direction")


class Company(Base, UUIDMixin, TimestampMixin):
    """A portfolio company (АО Navoiyazot, АО Узкимёсаноат, etc.)."""

    __tablename__ = "companies"

    # Code matches the legacy `_db.companies` keys for migration compat
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    name_short: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    name_uz: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name_en: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    legal_form: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    inn: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)

    sector_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sectors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ceo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    employees_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ─── Pack 9.2: Advanced customization ───
    primary_color:    Mapped[Optional[str]] = mapped_column(String(9),  nullable=True)  # override sector
    secondary_color:  Mapped[Optional[str]] = mapped_column(String(9),  nullable=True)  # for gradient
    badges:           Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # badges: [{text, color, position?}]  — up to 3
    status:           Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="active")
    # status: active | pilot | under_audit | divested | restructuring | m_a | ipo_imminent

    is_pinned:           Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    include_in_rollups:  Mapped[bool] = mapped_column(Boolean, default=True,  nullable=False)
    module_flags:        Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # module_flags: {kpi: bool, esg: bool, procurement: bool, financials: bool, governance: bool}

    parent_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    portfolio_start_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    primary_currency: Mapped[str] = mapped_column(String(3),  default="UZS", nullable=False)
    fy_start_month:   Mapped[int] = mapped_column(Integer,    default=1,     nullable=False)
    track_inflation:  Mapped[bool] = mapped_column(Boolean,   default=True,  nullable=False)

    bloomberg_ticker: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    isin:             Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    lei:              Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    tags:    Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    aliases: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Catch-all for legacy / extra fields
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    sector: Mapped[Optional["Sector"]] = relationship(back_populates="companies", foreign_keys=[sector_id])
    directions: Mapped[List["CompanyDirection"]] = relationship(
        back_populates="company", cascade="all, delete-orphan",
    )
    year_overrides: Mapped[List["CompanyYearOverride"]] = relationship(
        back_populates="company", cascade="all, delete-orphan",
        foreign_keys="[CompanyYearOverride.company_id]",
    )


class CompanyDirection(Base, UUIDMixin, TimestampMixin):
    """Many-to-many link company ↔ strategic direction with weighting."""

    __tablename__ = "company_directions"
    __table_args__ = (
        UniqueConstraint("company_id", "direction_id", name="uq_company_direction"),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    direction_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("directions.id", ondelete="CASCADE"), index=True
    )
    weight: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="directions")
    direction: Mapped["Direction"] = relationship(back_populates="companies")


class CompanyYearOverride(Base, UUIDMixin, TimestampMixin):
    """Per-year override for a company: hide, rename, change sector."""

    __tablename__ = "company_year_override"
    __table_args__ = (
        UniqueConstraint("company_id", "year", name="uq_company_year_override"),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True,
    )
    year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    name_override:      Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    sector_override_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sectors.id", ondelete="SET NULL"), nullable=True,
    )
    exclusion_reason:   Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # reason: restructuring | m_a | divestment | not_in_portfolio | audit | other
    notes:              Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="year_overrides", foreign_keys=[company_id])
    sector_override: Mapped[Optional["Sector"]] = relationship(foreign_keys=[sector_override_id])


Index("ix_companies_sector_active", Company.sector_id, Company.is_active)
