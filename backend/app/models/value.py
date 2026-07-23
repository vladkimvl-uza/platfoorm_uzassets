"""Value Opportunities registry — реестр возможностей ценности.

Каждая запись — выявленная возможность создать ценность для компании: экономия
(перерасход/переплата), рост (uplift) или предотвращённый риск. Источник —
детектор (unit_cost / procurement / business_plan / kpi) или ручной ввод.
Реестр закрывает цикл «выявлено → в работе → реализовано» с суммами и трекингом,
превращая надзор в измеримую ценность для компаний портфеля.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class ValueOpportunity(Base, UUIDMixin, TimestampMixin):
    """A single identified value-creation opportunity for a portfolio company."""

    __tablename__ = "value_opportunities"

    # company_id nullable — возможность может быть кросс-компанийной/портфельной.
    company_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    year: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)

    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")  # unit_cost|procurement|business_plan|kpi|manual
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="economy")   # economy|uplift|risk
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="identified", index=True)  # identified|in_progress|realized|dismissed

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Суммы в млрд сум (конвенция БП/финансов).
    value_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 3), nullable=True)
    realized_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 3), nullable=True)

    owner: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # ответственный
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    realized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Отпечаток для дедупа авто-сгенерированных возможностей (из детекторов).
    fingerprint: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


Index("ix_value_opportunities_company_status", ValueOpportunity.company_id, ValueOpportunity.status)
