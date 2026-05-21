"""FinModel v2 ORM models — Phase 1.3.

7 tables per finmodel-v2-handoff Phase 1.1:
  - FinModelTemplateRow      (static NSBU template lookup)
  - FinModelCellValue        (primary data, per company/year/code)
  - FinModelMacroGlobal      (global macro fallback)
  - FinModelMacroCompany     (per-company override)
  - FinModelYearLock         (draft/review/approved/locked)
  - FinModelScenario         (named snapshot)
  - FinModelCellComment      (optional cell-level comment)
  - FinModelAuditLog         (cell-level write trail)

No FKs to KPI/Credit/Library/ESG/Governance/Procurement — module is
deliberately isolated per Decision 1 of handoff.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FinModelTemplateRow(Base):
    __tablename__ = "finmodel_template_rows"

    code:            Mapped[str]            = mapped_column(String(16), primary_key=True)
    section:         Mapped[str]            = mapped_column(String(8), nullable=False)
    order_idx:       Mapped[int]            = mapped_column(Integer, nullable=False)
    parent_code:     Mapped[Optional[str]]  = mapped_column(String(16), nullable=True)
    row_type:        Mapped[str]            = mapped_column(String(16), nullable=False)
    name_ru:         Mapped[str]            = mapped_column(String(255), nullable=False)
    name_uz:         Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    name_uz_cyr:     Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    name_en:         Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    formula:         Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    ifrs_category:   Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    sign_convention: Mapped[Optional[str]]  = mapped_column(String(8), nullable=True)
    is_indent:       Mapped[int]            = mapped_column(Integer, default=0)
    legacy_note:     Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)


class FinModelCellValue(Base):
    __tablename__ = "finmodel_cell_values"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "row_code", name="uq_finmodel_cell"),
    )

    id:            Mapped[UUID]            = mapped_column(PG_UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    company_id:    Mapped[UUID]            = mapped_column(PG_UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year:          Mapped[int]             = mapped_column(Integer, nullable=False)
    row_code:      Mapped[str]             = mapped_column(String(16), ForeignKey("finmodel_template_rows.code", ondelete="RESTRICT"), nullable=False)
    value:         Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    is_calculated: Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    updated_by:    Mapped[Optional[UUID]]  = mapped_column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at:    Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FinModelMacroGlobal(Base):
    __tablename__ = "finmodel_macro_global"

    id:               Mapped[UUID]               = mapped_column(PG_UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    year:             Mapped[int]                = mapped_column(Integer, unique=True, nullable=False)
    uz_inflation:     Mapped[Optional[Decimal]]  = mapped_column(Numeric(6, 4), nullable=True)
    us_inflation:     Mapped[Optional[Decimal]]  = mapped_column(Numeric(6, 4), nullable=True)
    uzs_usd_avg_rate: Mapped[Optional[Decimal]]  = mapped_column(Numeric(12, 2), nullable=True)
    uzs_eur_avg_rate: Mapped[Optional[Decimal]]  = mapped_column(Numeric(12, 2), nullable=True)
    uzs_rub_avg_rate: Mapped[Optional[Decimal]]  = mapped_column(Numeric(12, 4), nullable=True)
    uzs_cny_avg_rate: Mapped[Optional[Decimal]]  = mapped_column(Numeric(12, 4), nullable=True)
    updated_by:       Mapped[Optional[UUID]]     = mapped_column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at:       Mapped[datetime]           = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FinModelMacroCompany(Base):
    __tablename__ = "finmodel_macro_company"
    __table_args__ = (UniqueConstraint("company_id", "year", name="uq_finmodel_macro_co"),)

    id:                    Mapped[UUID]               = mapped_column(PG_UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    company_id:            Mapped[UUID]               = mapped_column(PG_UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year:                  Mapped[int]                = mapped_column(Integer, nullable=False)
    uz_inflation:          Mapped[Optional[Decimal]]  = mapped_column(Numeric(6, 4), nullable=True)
    us_inflation:          Mapped[Optional[Decimal]]  = mapped_column(Numeric(6, 4), nullable=True)
    uzs_usd_avg_rate:      Mapped[Optional[Decimal]]  = mapped_column(Numeric(12, 2), nullable=True)
    forecast_method:       Mapped[str]                = mapped_column(String(32), default="uz_inflation")
    manual_growth_pct:     Mapped[Optional[Decimal]]  = mapped_column(Numeric(6, 4), nullable=True)
    dividend_payout_ratio: Mapped[Optional[Decimal]]  = mapped_column(Numeric(4, 3), default=Decimal("0.500"))
    updated_by:            Mapped[Optional[UUID]]     = mapped_column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at:            Mapped[datetime]           = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FinModelYearLock(Base):
    __tablename__ = "finmodel_year_lock"
    __table_args__ = (UniqueConstraint("company_id", "year", name="uq_finmodel_year_lock"),)

    id:            Mapped[UUID]                 = mapped_column(PG_UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    company_id:    Mapped[UUID]                 = mapped_column(PG_UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year:          Mapped[int]                  = mapped_column(Integer, nullable=False)
    status:        Mapped[str]                  = mapped_column(String(16), default="draft", nullable=False)
    locked_at:     Mapped[Optional[datetime]]   = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by:     Mapped[Optional[UUID]]       = mapped_column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approval_note: Mapped[Optional[str]]        = mapped_column(Text, nullable=True)


class FinModelScenario(Base):
    __tablename__ = "finmodel_scenarios"

    id:            Mapped[UUID]            = mapped_column(PG_UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    company_id:    Mapped[UUID]            = mapped_column(PG_UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name:          Mapped[str]             = mapped_column(String(128), nullable=False)
    description:   Mapped[Optional[str]]   = mapped_column(Text, nullable=True)
    is_active:     Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    snapshot_data: Mapped[dict]            = mapped_column(JSONB, nullable=False)
    created_by:    Mapped[Optional[UUID]]  = mapped_column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at:    Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinModelCellComment(Base):
    __tablename__ = "finmodel_cell_comments"

    id:           Mapped[UUID]            = mapped_column(PG_UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    company_id:   Mapped[UUID]            = mapped_column(PG_UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year:         Mapped[int]             = mapped_column(Integer, nullable=False)
    row_code:     Mapped[str]             = mapped_column(String(16), nullable=False)
    comment_text: Mapped[str]             = mapped_column(Text, nullable=False)
    source_ref:   Mapped[Optional[str]]   = mapped_column(String(255), nullable=True)
    author_id:    Mapped[Optional[UUID]]  = mapped_column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at:   Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:   Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FinModelAuditLog(Base):
    __tablename__ = "finmodel_audit_log"

    id:            Mapped[UUID]               = mapped_column(PG_UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    company_id:    Mapped[UUID]               = mapped_column(PG_UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year:          Mapped[int]                = mapped_column(Integer, nullable=False)
    row_code:      Mapped[str]                = mapped_column(String(16), nullable=False)
    value_before:  Mapped[Optional[Decimal]]  = mapped_column(Numeric(20, 2), nullable=True)
    value_after:   Mapped[Optional[Decimal]]  = mapped_column(Numeric(20, 2), nullable=True)
    actor_id:      Mapped[Optional[UUID]]     = mapped_column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source:        Mapped[str]                = mapped_column(String(32), nullable=False)
    ts:            Mapped[datetime]           = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
