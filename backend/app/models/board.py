"""Kanban boards: containers for grouped tasks."""
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Board(Base, UUIDMixin, TimestampMixin):
    """A Kanban board (typically per-company or per-project)."""

    __tablename__ = "boards"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Visual + filter metadata (mirrors monolith board.color and board.sector)
    color_hex:   Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    sector_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    legacy_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    columns: Mapped[list["BoardColumn"]] = relationship(
        back_populates="board", cascade="all, delete-orphan", order_by="BoardColumn.sort_order"
    )


class BoardColumn(Base, UUIDMixin, TimestampMixin):
    """A column on a board (Backlog, In Progress, Review, Done)."""

    __tablename__ = "board_columns"

    board_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("boards.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color_hex: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wip_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    board: Mapped["Board"] = relationship(back_populates="columns")
    cards: Mapped[list["BoardCard"]] = relationship(
        back_populates="column", cascade="all, delete-orphan", order_by="BoardCard.sort_order"
    )


class BoardCard(Base, UUIDMixin, TimestampMixin):
    """A card on a board column. Optionally links to a Task."""

    __tablename__ = "board_cards"

    column_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("board_columns.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    color_hex: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    column: Mapped["BoardColumn"] = relationship(back_populates="cards")


Index("ix_board_cards_column_order", BoardCard.column_id, BoardCard.sort_order)
