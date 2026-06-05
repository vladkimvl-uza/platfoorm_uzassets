"""Status updates — нарративный «Текущий статус проекта» с историей.

Append-only журнал: каждое обновление — новая строка. «Текущий статус» =
последняя по created_at. Месячный трекер группирует записи по месяцу.
Полиморфно для project/task (как Comment): entity_type + entity_id.
"""
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class StatusUpdate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "status_update"

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id:   Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    body:        Mapped[str] = mapped_column(Text, nullable=False)
    # Светофор хода: on_track / at_risk / delayed / blocked / None
    health:      Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    author_id:   Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_status_update_entity", "entity_type", "entity_id", "created_at"),
    )
