"""Report wizard config — сохранённый «Мастер отчёта» по компании+году.

Хранит JSONB-конфиг листов отчёта (направления, ключевые проекты/задачи,
«Текущий статус», «Предложения по шагам», статус-матрицы) + аудит.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class ReportWizardConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_wizard_configs"

    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    updated_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "year", name="uq_report_wizard_company_year"),
    )
