"""PMO P2 models — RAID-реестр и статус-отчёты.

RaidItem — реестр рисков/допущений/проблем/зависимостей (R/A/I/D).
StatusReport — снимок здоровья портфеля/проекта (RAG + метрики + резюме).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class RaidItem(Base, UUIDMixin, TimestampMixin):
    """RAID — Risk / Assumption / Issue / Dependency."""

    __tablename__ = "raid_items"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # risk | assumption | issue | dependency
    kind: Mapped[str] = mapped_column(String(16), default="risk", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    owner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    owner_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False, index=True)
    probability: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1..5
    impact: Mapped[int] = mapped_column(Integer, default=3, nullable=False)        # 1..5
    score: Mapped[int] = mapped_column(Integer, default=9, nullable=False, index=True)  # prob*impact

    # open | mitigating | closed
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    mitigation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class StatusReport(Base, UUIDMixin, TimestampMixin):
    """Снимок статуса портфеля/проекта (RAG + метрики + резюме)."""

    __tablename__ = "status_reports"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    period: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    # green | amber | red
    rag: Mapped[str] = mapped_column(String(8), default="green", nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
