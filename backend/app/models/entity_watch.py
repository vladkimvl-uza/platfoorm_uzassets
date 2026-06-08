"""Entity watch — подписка пользователя на проект/задачу («отслеживание»).

Полиморфно (entity_type + entity_id), как status_update/comment_read.
source: 'manual' (явная кнопка) | 'auto' (вовлечённость: создал/назначен/
прокомментировал). Уведомления watcher'ам идут через notifications_service.
"""
from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class EntityWatch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "entity_watch"

    user_id:     Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id:   Mapped[str] = mapped_column(String(128), nullable=False)
    source:      Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # manual | auto

    __table_args__ = (
        Index("uq_entity_watch", "user_id", "entity_type", "entity_id", unique=True),
        Index("ix_entity_watch_entity", "entity_type", "entity_id"),
    )
