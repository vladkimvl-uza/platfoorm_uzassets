"""Platform-wide announcements / notifications."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Announcement(Base, UUIDMixin, TimestampMixin):
    """A platform announcement shown to users on dashboard / sidebar."""

    __tablename__ = "announcements"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    # info | warning | success | danger

    author_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    publish_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    target_audience: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # e.g. {"sectors": ["energy"], "roles": ["admin"]}

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


Index("ix_announcements_pub_window", Announcement.publish_at, Announcement.expires_at)
