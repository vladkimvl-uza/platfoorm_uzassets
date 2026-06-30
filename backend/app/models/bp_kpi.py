"""SQLAlchemy models for Business Plan and KPI dashboards.

Mirrors the legacy _db.businessPlan and _db.kpi structures (lines 35357–42700
of index.html) into normalized PG tables. See migration 0020_bp_kpi for schema.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.company import Company


# ─── Constants (mirror legacy BP_FIELDS, BP_PERIODS) ────────────

BP_METRICS: list[dict] = [
    {"key": "revenue",     "label": "Чистая выручка от реализации",                   "group": "opRevenue",   "auto": False},
    {"key": "cogs",        "label": "Себестоимость реализованной продукции",          "group": "opRevenue",   "auto": False, "positive": True},
    {"key": "grossProfit", "label": "Валовая прибыль",                                 "group": "opRevenue",   "auto": True,  "formula": "revenue - cogs"},
    {"key": "opExpenses",  "label": "Расходы периода",                                 "group": "opExpenses",  "auto": False, "positive": True},
    {"key": "sellExp",     "label": "— расходы на реализацию",                         "group": "opExpenses",  "auto": False, "positive": True, "sub": True},
    {"key": "adminExp",    "label": "— административные расходы",                      "group": "opExpenses",  "auto": False, "positive": True, "sub": True},
    {"key": "otherOpExp",  "label": "— прочие операционные расходы",                   "group": "opExpenses",  "auto": False, "positive": True, "sub": True},
    {"key": "otherOpInc",  "label": "Прочие доходы от основной деятельности",          "group": "opResult",    "auto": False},
    {"key": "opProfit",    "label": "Операционная прибыль",                            "group": "opResult",    "auto": True,  "formula": "grossProfit - opExpenses + otherOpInc"},
    {"key": "finIncome",   "label": "Финансовые доходы",                               "group": "finActivity", "auto": False},
    {"key": "divIncome",   "label": "— доходы в виде дивидендов",                      "group": "finActivity", "auto": False, "sub": True},
    {"key": "intIncome",   "label": "— доходы в виде процентов",                       "group": "finActivity", "auto": False, "sub": True},
    {"key": "fxIncome",    "label": "— доходы от курсовых разниц",                     "group": "finActivity", "auto": False, "sub": True},
    {"key": "otherFinInc", "label": "— прочие фин. доходы",                            "group": "finActivity", "auto": False, "sub": True},
    {"key": "finCost",     "label": "Финансовые расходы",                              "group": "finActivity", "auto": False, "positive": True},
    {"key": "intExp",      "label": "— расходы в виде процентов",                      "group": "finActivity", "auto": False, "positive": True, "sub": True},
    {"key": "fxLoss",      "label": "— убытки от курсовых разниц",                     "group": "finActivity", "auto": False, "positive": True, "sub": True},
    {"key": "otherFinExp", "label": "— прочие фин. расходы",                           "group": "finActivity", "auto": False, "positive": True, "sub": True},
    {"key": "hhProfit",    "label": "Прибыль от общехоз. деятельности",                "group": "final",       "auto": True,  "formula": "opProfit + finIncome - finCost"},
    {"key": "pbt",         "label": "Прибыль до налогообложения",                      "group": "final",       "auto": True,  "formula": "hhProfit"},
    {"key": "tax",         "label": "Налог на прибыль",                                "group": "final",       "auto": False, "positive": True},
    {"key": "profit",      "label": "Чистая прибыль (убыток) периода",                 "group": "final",       "auto": True,  "formula": "pbt - tax"},
]

BP_METRIC_KEYS = [m["key"] for m in BP_METRICS]
BP_PERIODS = ["annual", "q1", "q2", "q3", "q4"]

# Каноническое направление метрики для KPI-связи: расходные/cost-метрики
# (positive=True: cogs/opExpenses/finCost/tax/…) — «меньше = лучше» (down),
# остальные (revenue/profit/…) — «больше = лучше» (up). Для связанного (bp_metric_key)
# KPI direction форсится отсюда, а не из ручного ind.direction.
BP_METRIC_DIRECTION: dict[str, str] = {
    m["key"]: ("down" if m.get("positive") else "up") for m in BP_METRICS
}

# Линкуемые «headline»-метрики (без sub-детализации) — опции выбора связи в
# KPI-редакторе. Связанный финансовый KPI зеркалит план/факт этой BP-метрики.
BP_HEADLINE_METRIC_KEYS = [m["key"] for m in BP_METRICS if not m.get("sub")]
BP_METRIC_LABELS: dict[str, str] = {m["key"]: m["label"] for m in BP_METRICS}


# ─── Business Plan ────────────────────────────────────────────────

class BpRecord(Base):
    """One BP cell — (company, year, period, metric) → (plan, expect, fact)."""

    __tablename__ = "bp_records"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "period", "metric", name="uq_bp_records_co_year_period_metric"),
        CheckConstraint("period IN ('annual','q1','q2','q3','q4')", name="ck_bp_records_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    plan: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    expect: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    fact: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    company: Mapped[Company] = relationship("Company", lazy="joined")


class BpComment(Base):
    """Free-text comment per BP scope (company, year, period)."""

    __tablename__ = "bp_comments"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "period", name="uq_bp_comments_co_year_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


# ─── KPI ──────────────────────────────────────────────────────────

class KpiManager(Base):
    """KPI manager (e.g. CEO, CFO) within a company-year scope."""

    __tablename__ = "kpi_managers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    short_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    company: Mapped[Company] = relationship("Company", lazy="joined")
    indicators: Mapped[list[KpiIndicator]] = relationship(
        "KpiIndicator",
        back_populates="manager",
        cascade="all, delete-orphan",
        order_by="KpiIndicator.sort_order",
        lazy="selectin",
    )


class KpiIndicator(Base):
    """Leaf KPI indicator under a manager."""

    __tablename__ = "kpi_indicators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kpi_managers.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Направление метрики: 'up' = больше=лучше (по умолч.), 'down' = меньше=лучше
    # (себестоимость, просрочка, аварийность). Влияет на формулу выполнения.
    direction: Mapped[str] = mapped_column(String(8), nullable=False, server_default="up")
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default="0")
    plan_year: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    fact_year: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)

    q1_weight: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default="0")
    q2_weight: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default="0")
    q3_weight: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default="0")
    q4_weight: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default="0")

    q1_plan: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    q1_fact: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    q2_plan: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    q2_fact: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    q3_plan: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    q3_fact: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    q4_plan: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)
    q4_fact: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 3), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Жёсткая ESG-пометка (KPI, добавленный из ESG-дашборда под любой должностью).
    is_esg: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Связь с канонической метрикой Бизнес-плана (∈ BP_METRIC_KEYS). NULL = свободный
    # операционный KPI (по умолчанию, поведение не меняется). Если задана — план/факт
    # зеркалятся из BP/НСБУ (read-through), direction форсится из BP_METRIC_DIRECTION;
    # собственные plan_year/fact_year связанной строки в расчёте не используются.
    bp_metric_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    manager: Mapped[KpiManager] = relationship("KpiManager", back_populates="indicators")


class KpiComment(Base):
    """Free-text comment per KPI scope (company, year, period)."""

    __tablename__ = "kpi_comments"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "period", name="uq_kpi_comments_co_year_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
