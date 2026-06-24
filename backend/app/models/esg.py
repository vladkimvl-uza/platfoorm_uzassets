"""ESG metrics, issues, and notes."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class ESGMetric(Base, UUIDMixin, TimestampMixin):
    """An E/S/G metric value for a company in a given year."""

    __tablename__ = "esg_metrics"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "metric_code", name="uq_esg_co_year_metric"),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # E | S | G
    pillar: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    metric_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)

    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    benchmark: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ESGIssue(Base, UUIDMixin, TimestampMixin):
    """A material ESG issue / risk for a company."""

    __tablename__ = "esg_issues"

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    pillar: Mapped[str] = mapped_column(String(8), nullable=False)  # E | S | G
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # low | med | high | critical
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ESGNote(Base, UUIDMixin, TimestampMixin):
    """A free-text ESG note tied to a company / year / metric."""

    __tablename__ = "esg_notes"

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metric_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    author_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)


class ESGYearTracked(Base, UUIDMixin, TimestampMixin):
    """Per-company list of years where ESG data is tracked
    (mirrors `_db.esgYearsTracked` in the legacy)."""

    __tablename__ = "esg_years_tracked"
    __table_args__ = (
        UniqueConstraint("company_id", "year", name="uq_esg_year_tracked"),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class ESGMaturityCell(Base, UUIDMixin, TimestampMixin):
    """Единая ячейка трекера ESG-зрелости: компания × год × измерение × под-ключ.

    6 измерений (dimension): D1 ISO · D2 отчётность · D3 рейтинги ·
    D4 климат · D5 риски · D6 KPI менеджмента. Нормализованная `stage` (0..4)
    нужна для прямого расчёта ESG Maturity Score без парсинга текста;
    `status_text`/`extra` хранят сырьё («в процессе закупки», языки отчёта, флаги).
    """

    __tablename__ = "esg_maturity_cells"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "year", "dimension", "sub_key",
            name="uq_esg_maturity_cell",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dimension: Mapped[str] = mapped_column(String(8), nullable=False)   # D1..D6
    sub_key: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0..4
    status_text: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    evidence_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    owner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


Index("ix_esg_metrics_pillar_year", ESGMetric.pillar, ESGMetric.year)
Index("ix_esg_maturity_co_year", ESGMaturityCell.company_id, ESGMaturityCell.year)
