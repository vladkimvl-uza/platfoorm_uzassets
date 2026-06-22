"""Tasks: the original ProjectsFlow Kanban entity."""
from datetime import date
from typing import Optional

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Task(Base, UUIDMixin, TimestampMixin):
    """A unit of work — typically a project, KPI initiative, or follow-up."""

    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Manual hierarchical numbering ("1", "1.2", "1.2.3" — used in legacy)
    num: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Status: legacy uses init/new/active/review/done. New rows default 'new'.
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False, index=True)

    # Priority: high | medium | low (matches legacy _PRIO_LBL)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False, index=True)

    # Direct board assignment (legacy uses boardId on the task itself)
    board_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("boards.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Year-tag for portfolio filtering (UI year filter is visual-only, but data still has year)
    portfolio_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Parent project (None for standalone tasks). When a project is split into
    # subtasks, those tasks point back to the project here.
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Soft link to another task (legacy: linkedTaskId)
    linked_task_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    # Phase 13: 'перенесена на год X' — target year for the deferred link
    linked_year: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )


    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    direction_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("directions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    assignee_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Denormalized assignee info — legacy assignees may not have a User row in this table.
    assignee_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    assignee_name:  Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    creator_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    completed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Binary "результат": NULL = no result, datetime = when accepted.
    # Alert in UI when status='done' AND result_at IS NULL.
    result_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ─── PMO P1: расписание / базовый план / вес / трудозатраты ───────────
    # Базовый план (снимок) — для расчёта слипа: фактический сдвиг vs baseline.
    baseline_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    baseline_due:   Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Вес задачи для взвешенного роллапа прогресса (по умолчанию 1).
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Оценка/факт трудозатрат (часы) — для загрузки людей и EVM (P3).
    estimated_hours: Mapped[Optional[float]] = mapped_column(Numeric(10, 1), nullable=True)
    actual_hours:    Mapped[Optional[float]] = mapped_column(Numeric(10, 1), nullable=True)
    # Веха — нулевая длительность (ромб на Гантте).
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ─── PMO P3: Agile — спринт + story points (спринт группирует задачи) ──
    sprint_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pmo_sprints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    story_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Ручной порядок в списке (drag-reorder в CompanyBoardList). 0 = по-умолчанию,
    # сортируется как вторичный ключ после num. Persisted через обычный PATCH.
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)

    # Tags / labels
    tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Original legacy id (for migration)
    legacy_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)

    # Catch-all for legacy fields
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    comments: Mapped[list["TaskComment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["TaskAttachment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    history: Mapped[list["TaskHistory"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskComment(Base, UUIDMixin, TimestampMixin):
    """A comment on a task."""

    __tablename__ = "task_comments"

    task_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    task: Mapped["Task"] = relationship(back_populates="comments")


class TaskAttachment(Base, UUIDMixin, TimestampMixin):
    """A file attached to a task."""

    __tablename__ = "task_attachments"

    task_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    uploader_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    task: Mapped["Task"] = relationship(back_populates="attachments")


class TaskHistory(Base, UUIDMixin, TimestampMixin):
    """Append-only audit trail of changes to a task."""

    __tablename__ = "task_history"

    task_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # created | updated | status_changed | ...
    field_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diff: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    task: Mapped["Task"] = relationship(back_populates="history")


class TaskDependency(Base, UUIDMixin, TimestampMixin):
    """PMO P1: зависимость предшественник → преемник.

    dep_type: FS (finish-to-start, по умолчанию) | SS | FF | SF.
    lag_days: задержка в днях. Используется для сетевого графика,
    критического пути и «мягкой» блокировки карточки на доске."""

    __tablename__ = "task_dependencies"

    predecessor_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    successor_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dep_type: Mapped[str] = mapped_column(String(2), default="FS", nullable=False)
    lag_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("predecessor_id", "successor_id", name="uq_task_dep_pair"),
    )


Index("ix_tasks_status_due", Task.status, Task.due_date)
Index("ix_tasks_company_status", Task.company_id, Task.status)
