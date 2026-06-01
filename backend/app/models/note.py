"""Notes -- Smart Journal архитектура B+C.

Замена прежней простой Note модели. Сохраняет обратную совместимость
по существующим колонкам (user_id, entity_type, entity_id, title, body,
color, is_pinned), добавляет:
- company_id -- главный scope для company workspace (FK companies)
- author_id  -- кто создал (FK users; user_id legacy остаётся)
- kind       -- event/decision/task/risk/observation
- tags       -- TEXT[] (GIN индекс)
- event_date -- когда это произошло
- due_date   -- дедлайн (kind=task)
- is_resolved + resolved_at
- links      -- relationship на NoteLink (polymorphic ссылки)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# Whitelist допустимых kind. Дублируется в schemas/notes.py и frontend.
NOTE_KINDS = ("event", "decision", "task", "risk", "observation")

# Whitelist допустимых entity_type для note_links.
NOTE_LINK_ENTITY_TYPES = (
    "project",
    "task",
    "kpi_indicator",
    "kpi_manager",
    "esg_issue",
    "esg_metric",
    "board_member",
    "loan",
    "consultant",
    "bp_metric",
    "financial_line",
    "procurement_contract",
    "rating",
)


class Note(Base, UUIDMixin, TimestampMixin):
    """Smart Journal note. Расширяет _db.notes из монолита.

    Scope-ключи (для filter'ов):
      company_id: главный scope для tab `Заметки` в Company Workspace
      user_id   : legacy private notes (без company_id)
      entity_type/entity_id: вторичная привязка к конкретной сущности
                             (для polymorphic see also note_links)

    Семантика kind:
      event       -- что произошло (заседание, подписание контракта)
      decision    -- что решено (utverzhdeno на совете директоров)
      task        -- что нужно сделать (с due_date)
      risk        -- угроза, ещё не материализованная
      observation -- контекст / наблюдение
    """

    __tablename__ = "notes"

    # === Scope ===
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
    )
    author_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # === Polymorphic legacy ===
    entity_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    entity_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )

    # === Content ===
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="observation",
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
        default=list,
    )

    # === Display ===
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # === Dates ===
    event_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # === Resolution ===
    is_resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # === Relationships ===
    links: Mapped[list[NoteLink]] = relationship(
        "NoteLink",
        back_populates="note",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('event','decision','task','risk','observation')",
            name="ck_notes_kind",
        ),
    )


# Composite индекс для основного фильтра (company_id, event_date DESC).
# В Postgres NULL по дефолту в конец при DESC, но для чёткости -- NULLS LAST.
Index(
    "ix_notes_company",
    Note.company_id,
    Note.event_date.desc().nulls_last(),
)
Index("ix_notes_kind", Note.kind)
Index("ix_notes_author_id", Note.author_id)
Index("ix_notes_due_date", Note.due_date)
# GIN на tags задан в миграции напрямую (postgresql_using='gin')

# Сохраняем legacy индекс
Index("ix_notes_user_entity", Note.user_id, Note.entity_type, Note.entity_id)


class NoteLink(Base, UUIDMixin):
    """Polymorphic ссылка с заметки на сущность платформы.

    Одна заметка может быть привязана к нескольким сущностям через note_links.
    Для UUID-сущностей (project/task/kpi_indicator/etc) используется entity_id.
    Для строковых ключей (bp_metric="revenue") -- entity_key.
    entity_label кешируется для отображения без JOIN.
    """

    __tablename__ = "note_links"

    note_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    entity_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    entity_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    note: Mapped[Note] = relationship("Note", back_populates="links")

    __table_args__ = (
        CheckConstraint(
            "entity_id IS NOT NULL OR entity_key IS NOT NULL",
            name="ck_note_links_entity_ref",
        ),
    )


Index("ix_note_links_entity", NoteLink.entity_type, NoteLink.entity_id)
Index("ix_note_links_entity_key", NoteLink.entity_type, NoteLink.entity_key)
