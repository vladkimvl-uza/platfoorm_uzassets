"""Subsidies registry — субсидии по компаниям портфеля (реестр).

Каждая запись — отдельная субсидия (сумма + назначение + источник + вид +
статус + дата). Метрика «Субсидии» в модуле финансы агрегирует суммы по
компании/году; клик открывает реестр с фильтрами по секторам/компаниям.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Subsidy(Base, UUIDMixin, TimestampMixin):
    """A single subsidy record for a portfolio company."""

    __tablename__ = "subsidies"

    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    year: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)

    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 2), nullable=True)

    program: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)   # назначение/программа
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)    # источник (бюджет/фонд)
    kind: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)      # вид субсидии
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)     # статус
    allocation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


Index("ix_subsidies_company_year", Subsidy.company_id, Subsidy.year)
