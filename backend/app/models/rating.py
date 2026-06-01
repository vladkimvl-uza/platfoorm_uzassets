"""Company ratings: composite scores from multiple metrics."""
from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Rating(Base, UUIDMixin, TimestampMixin):
    """A composite rating for a company in a given period."""

    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "quarter", name="uq_rating_co_year_qtr"),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Composite score (e.g. 0–100)
    overall_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    overall_grade: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # A+, A, B, etc.

    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Per-dimension scores stored as JSON
    dimension_scores: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    metrics: Mapped[list["RatingMetric"]] = relationship(
        back_populates="rating", cascade="all, delete-orphan"
    )
    history: Mapped[list["RatingHistory"]] = relationship(
        back_populates="rating", cascade="all, delete-orphan"
    )


class RatingMetric(Base, UUIDMixin, TimestampMixin):
    """A single metric contributing to a rating."""

    __tablename__ = "rating_metrics"

    rating_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ratings.id", ondelete="CASCADE"), index=True
    )
    metric_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    benchmark: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    rating: Mapped["Rating"] = relationship(back_populates="metrics")


class RatingHistory(Base, UUIDMixin, TimestampMixin):
    """Audit log: rating changes."""

    __tablename__ = "rating_history"

    rating_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ratings.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    diff: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    rating: Mapped["Rating"] = relationship(back_populates="history")


Index("ix_ratings_year_score", Rating.year, Rating.overall_score.desc())
