"""External agency ratings (credit + ESG) — separate from the composite Rating model.

The legacy ProjectsFlow / UzAssets monolith stores per-agency public ratings
in `/pf/ratings`. Each entry is `{boardId, agency, rating, outlook, date,
score, url}`. This module models that data shape.

ESG_AGENCIES is the discriminator: agencies in this set produce ESG ratings;
all others produce credit ratings.
"""
from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# Discriminator: agencies that produce ESG ratings (vs credit ratings).
# Mirrors `ESG_AGENCIES` in the monolith.
ESG_AGENCIES = frozenset([
    "Sustainable Fitch",
    "S&P ESG",
    "CDP",
    "Sustainalytics",
    "MSCI",
])


def is_esg_agency(agency: str) -> bool:
    """Returns True if `agency` is an ESG-rating agency."""
    return (agency or "").strip() in ESG_AGENCIES


class AgencyRating(Base, UUIDMixin, TimestampMixin):
    """A single rating from one agency for one company.

    For a given company, only ONE rating per agency exists at a time — when
    a new rating is published, it overwrites the old one (history is kept
    via the audit log, not via duplicate rows).
    """

    __tablename__ = "agency_ratings"
    __table_args__ = (
        UniqueConstraint("company_id", "agency", name="ux_agency_ratings_co_agency"),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Agency name as published (e.g. "Fitch", "S&P", "Moody's", "Sustainable Fitch")
    agency: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Discriminator — set at insert/update based on agency name
    is_esg: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # The rating itself — text grade (BB+, A-, AAA, 3 for Sustainable Fitch numeric)
    rating: Mapped[Optional[str]]  = mapped_column(String(16), nullable=True)
    outlook: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    score: Mapped[Optional[str]]   = mapped_column(String(16), nullable=True)

    # Date as published — free-form text ("июл 2025", "ноя 2024", "2025")
    rating_date_text: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Parsed date for sorting (best-effort — None when text can't be parsed)
    rating_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    report_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Legacy ID = "{board_id}::{agency}" so re-import is idempotent
    legacy_id:       Mapped[Optional[str]] = mapped_column(String(96), unique=True, nullable=True)
    legacy_board_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
