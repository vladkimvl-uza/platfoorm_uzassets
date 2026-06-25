"""Agency rating history — снимок состояния рейтинга при каждом изменении.

Записывается на ОБОИХ путях записи рейтинга:
  - прямой (routes/ratings → RatingsService)
  - через модерацию (moderation_apply/ratings.apply)
Таймлайн строится по (company_id, agency) → включает create/update/delete.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class AgencyRatingHistory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agency_rating_history"

    # NULL при delete (рейтинга уже нет) и при ON DELETE SET NULL.
    rating_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agency_ratings.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    agency: Mapped[str] = mapped_column(String(64), nullable=False)
    is_esg: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # снимок значений рейтинга на момент изменения
    rating: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    outlook: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    score: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    rating_date_text: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rating_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    action: Mapped[str] = mapped_column(String(16), nullable=False, default="snapshot")  # create|update|delete|snapshot
    changed_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    changed_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
