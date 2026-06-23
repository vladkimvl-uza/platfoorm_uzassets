"""IFRS report history — даты публикации МСФО-отчётности по компаниям (с 2022).

По (company_id, year) хранится дата публикации отчётности + аудит (кто/когда
вносил последнее изменение). Inline-редактирование в /financials под МСФО.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class IfrsReportHistory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ifrs_report_history"

    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    published_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    updated_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "year", name="uq_ifrs_history_company_year"),
    )
