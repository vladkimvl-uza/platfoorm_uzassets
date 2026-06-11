"""
Per-user AI configuration model.

One row per user. Stores the user's preferred:
  • role: 'analyst' | 'assistant' | 'expert' | 'universal' | 'financial'
  • style: 'laconic' | 'detailed' | 'structured' | 'adaptive'
  • temperature: 0.0..1.0
  • custom_instructions: free-form text appended to system prompt
  • max_tokens: per-request budget
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, DateTime, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

# Multi-path Base import (to support different project layouts)
try:
    from app.database import Base  # type: ignore
except ImportError:
    try:
        from app.core.database import Base  # type: ignore
    except ImportError:
        from app.db.base_class import Base  # type: ignore[import]


class AiUserConfig(Base):
    __tablename__ = "ai_user_config"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[str] = mapped_column(String(32), default="analyst", nullable=False)
    style: Mapped[str] = mapped_column(String(32), default="structured", nullable=False)
    model: Mapped[str] = mapped_column(
        String(64),
        default="ai-balanced",
        server_default="ai-balanced",
        nullable=False,
    )
    temperature: Mapped[float] = mapped_column(Float, default=0.25, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=16000, nullable=False)
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
