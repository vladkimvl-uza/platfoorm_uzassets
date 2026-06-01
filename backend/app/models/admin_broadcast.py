"""Admin Broadcast models (Pack 11.2)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminBroadcastTemplate(Base):
    """Recurring or one-shot admin broadcast definition."""
    __tablename__ = "admin_broadcast_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Content
    type:     Mapped[str]            = mapped_column(String(32), nullable=False, default="announcement")
    priority: Mapped[str]            = mapped_column(String(16), nullable=False, default="normal")
    title:    Mapped[str]            = mapped_column(String(255), nullable=False)
    body:     Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    link_url: Mapped[Optional[str]]  = mapped_column(String(512), nullable=True)
    attachments: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    icon:     Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    color:    Mapped[Optional[str]]  = mapped_column(String(16), nullable=True)

    # Targeting
    target_user_ids:    Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    target_group_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    target_role_codes:  Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    target_company_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    target_sector_ids:  Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    target_all:         Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)
    target_filter_expr: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Acknowledgement
    ack_mode:                 Mapped[str]            = mapped_column(String(16), nullable=False, default="none")
    ack_question:             Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    ack_options:              Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    is_sticky:                Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)
    ack_deadline_hours:       Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    auto_resend_hours:        Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    escalate_to_manager:      Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)
    show_site_banner_on_overdue: Mapped[bool]        = mapped_column(Boolean, nullable=False, default=False)

    # Schedule
    schedule_mode:    Mapped[str]            = mapped_column(String(16), nullable=False, default="oneshot")
    schedule_config:  Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    schedule_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_end_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Stats
    total_dispatches:          Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_recipients_lifetime: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_acks_lifetime:       Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AdminBroadcastDispatch(Base):
    """One execution of a broadcast template (or manual send)."""
    __tablename__ = "admin_broadcast_dispatch"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_broadcast_template.id", ondelete="CASCADE"), nullable=False,
    )
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    recipients_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_count:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    read_count:       Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acked_count:      Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dispatched_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="schedule")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AdminBroadcastAck(Base):
    """A user's acknowledgement of a sticky/ack-required notification."""
    __tablename__ = "admin_broadcast_ack"
    __table_args__ = (UniqueConstraint("notification_id", name="uq_brack_notif"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification.id", ondelete="CASCADE"), nullable=False,
    )
    dispatch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_broadcast_dispatch.id", ondelete="SET NULL"), nullable=True,
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_broadcast_template.id", ondelete="SET NULL"), nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    response_text:  Mapped[Optional[str]]  = mapped_column(Text,           nullable=True)
    response_value: Mapped[Optional[str]]  = mapped_column(String(255),    nullable=True)
    response_file:  Mapped[Optional[dict]] = mapped_column(JSONB,          nullable=True)


# ─── Catalogs for UI ──────────────────────────────────────────

BROADCAST_TYPES = [
    {"code": "announcement", "label": "Объявление",  "icon": "speakerphone"},
    {"code": "policy",       "label": "Политика",    "icon": "file-text"},
    {"code": "training",     "label": "Обучение",    "icon": "school"},
    {"code": "survey",       "label": "Опрос",       "icon": "chart-bar"},
    {"code": "reminder",     "label": "Напоминание", "icon": "bell"},
]

BROADCAST_PRIORITIES = ["low", "normal", "high", "critical"]

ACK_MODES = [
    {"code": "none",   "label": "Не требуется"},
    {"code": "click",  "label": "Подтверждение одной кнопкой"},
    {"code": "text",   "label": "Текстовый ответ"},
    {"code": "select", "label": "Выбор из списка"},
    {"code": "yesno",  "label": "Да / Нет"},
    {"code": "file",   "label": "Загрузка файла"},
]

SCHEDULE_MODES = [
    {"code": "oneshot",  "label": "Однократно"},
    {"code": "interval", "label": "Повторяющееся"},
    {"code": "cron",     "label": "Cron-выражение"},
]
