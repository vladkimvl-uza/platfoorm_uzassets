"""AI configuration, access list, conversation history, telemetry."""
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class AIConfig(Base, UUIDMixin, TimestampMixin):
    """Global AI configuration. Mirrors `_db.aiConfig`."""

    __tablename__ = "ai_config"

    key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class AIAccess(Base, UUIDMixin, TimestampMixin):
    """Per-user AI access flags. Mirrors `_db.aiAccess`."""

    __tablename__ = "ai_access"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    monthly_token_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_used_this_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AIHistory(Base, UUIDMixin, TimestampMixin):
    """A single AI conversation message. Mirrors `ai_history/{uid}`."""

    __tablename__ = "ai_history"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)

    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)

    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class TelemetryLog(Base, UUIDMixin, TimestampMixin):
    """Anonymized telemetry / usage events. Mirrors `telemetry_log`."""

    __tablename__ = "telemetry_log"

    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)


Index("ix_ai_history_user_conv", AIHistory.user_id, AIHistory.conversation_id)
Index("ix_telemetry_event_time", TelemetryLog.event_name, TelemetryLog.created_at)
