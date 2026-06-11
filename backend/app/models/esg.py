"""ESG metrics, issues, and notes."""
from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
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


Index("ix_esg_metrics_pillar_year", ESGMetric.pillar, ESGMetric.year)
