"""Consultant import — staging table for batch imports from external consultants.
Mirrors `_db.consultantImport` in the monolith.

Phase 11 additions:
  - Consultant: master list of consultancy firms (PwC, EY, McKinsey, etc.)
  - ConsultantAssignment: M:N link between tasks and consultants
"""
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class ConsultantImport(Base, UUIDMixin, TimestampMixin):
    """A batch of consultant-imported data, awaiting review/merge."""

    __tablename__ = "consultant_imports"

    consultant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # ratings | financials | esg | governance | kpi | ...

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    # pending | reviewed | applied | rejected

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    submitted_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    applied_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


# =====================================================================
# Phase 11: Consultant master + assignments
# =====================================================================

class Consultant(Base, UUIDMixin, TimestampMixin):
    """A consultancy firm (PwC, McKinsey, KPMG, …).

    Mirrors monolith CONSULTANTS array (17 firms, 4 of which are Big4).
    Editable via /consultants admin endpoint.
    """

    __tablename__ = "consultants"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # 'pwc', 'ey', 'mckinsey', 'kpmg', 'deloitte', 'bcg', 'rothschild', ...
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    abbr: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    color_hex: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    is_big4: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    assignments: Mapped[list["ConsultantAssignment"]] = relationship(
        back_populates="consultant", cascade="all, delete-orphan"
    )


class ConsultantAssignment(Base, UUIDMixin):
    """M:N link between tasks and consultants.

    A task can have 1+ consultants; a consultant can be on many tasks.
    `source` tracks where the link came from:
      - 'task'   — derived from task.consultant string/array field (legacy)
      - 'lookup' — added via CONSULTANT_LOOKUP (board::num key, year=2025 only)
      - 'manual' — added/edited by user in Vue UI
    """

    __tablename__ = "consultant_assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "consultant_id", name="uq_consultant_assignment_pair"),
    )

    task_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    consultant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), default="task", nullable=False)

    # Note: TimestampMixin not used here — only created_at via DDL default.
    # If updated_at tracking needed later, switch to TimestampMixin.

    consultant: Mapped["Consultant"] = relationship(back_populates="assignments")
