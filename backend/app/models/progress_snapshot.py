"""Progress snapshots — фиксация среза прогресса портфеля на момент времени.

Каждый снимок = точка отсчёта: текущие totals (задачи/проекты выполнено/всего,
просрочка) + per-company breakdown в JSONB. Сравнение двух снимков даёт
реальную динамику «было → стало» во времени (а не только по дедлайнам).

Таблица создаётся self-heal-миграцией (`_patch_progress_snapshots`) —
alembic не используется для рантайм-схемы.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID as PyUUID

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDMixin


class ProgressSnapshot(Base, UUIDMixin):
    __tablename__ = "progress_snapshots"

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    captured_by: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="portfolio")

    tasks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    projects_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    projects_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # [{company_id, code, name, tasks_done, tasks_total, projects_done, projects_total}]
    companies: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
