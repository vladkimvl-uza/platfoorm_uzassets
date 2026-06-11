"""Projects: long-running initiatives split out from the legacy ProjectsFlow tasks.

In the legacy, projects and tasks shared the `_db.tasks` array, distinguished
only by `_isProject` boolean. The new platform separates them into two physical
tables for cleaner queries and clearer permission boundaries.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Project(Base, UUIDMixin, TimestampMixin):
    """A long-running strategic initiative."""

    __tablename__ = "projects"

    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    num: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Status: init/new/active/review/done — same values as tasks (legacy _STATUS_LBL)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False, index=True)

    board_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("boards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    direction_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("directions.id", ondelete="SET NULL"), nullable=True
    )

    assignee_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assignee_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    assignee_name:  Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    creator_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date:   Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Binary "результат": NULL = no result, datetime = when accepted.
    # Alert in UI when status='done' AND result_at IS NULL.
    result_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Ручной порядок групп в списке (drag-reorder). Вторичный ключ после num.
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    portfolio_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # Phase 13: 'перенесён на год X'
    linked_year: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )

    # Project Editor (added in 20260508-112329 revision)
    ground_type: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )
    project_type: Mapped[Optional[str]] = mapped_column(
        String(32), default="onetime", nullable=True, index=True
    )
    linked_project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    legacy_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)

    # Reverse: child tasks
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        primaryjoin="Project.id == Task.project_id",
        viewonly=True,
    )


class ProjectComment(Base, UUIDMixin, TimestampMixin):
    """A comment on a project (analog of TaskComment)."""

    __tablename__ = "project_comments"

    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
