"""Notification models (Pack 11.0)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# ─── Notification type catalog (string codes, validated at app level) ────

NOTIFICATION_TYPES = {
    # Moderation will create these)
    "moderation.pending":          {"priority": "high",     "label": "Новое предложение на модерацию"},
    # Автору: его правка не сохранена сразу, а ушла на согласование. Без этого
    # модерируемый пользователь видел только тост и терял нить — что с правкой.
    "moderation.submitted":        {"priority": "normal",   "label": "Ваше изменение отправлено на согласование"},
    "moderation.approved":         {"priority": "normal",   "label": "Ваше предложение одобрено"},
    "moderation.rejected":         {"priority": "high",     "label": "Ваше предложение отклонено"},
    "moderation.review_requested": {"priority": "high",     "label": "Запрошено дополнительное рассмотрение"},
    "moderation.escalated":        {"priority": "high",     "label": "Предложение эскалировано"},
    "moderation.expired":          {"priority": "normal",   "label": "Предложение истекло"},
    # Interactions
    "mention":           {"priority": "high",     "label": "Вас упомянули"},
    "assignment":        {"priority": "high",     "label": "Задача назначена на вас"},
    "comment.replied":   {"priority": "normal",   "label": "Ответ на ваш комментарий"},
    # Deadlines
    "deadline.approaching": {"priority": "normal", "label": "Приближается дедлайн"},
    "deadline.missed":      {"priority": "critical", "label": "Дедлайн пропущен"},
    # KPI
    "kpi.target.missed":    {"priority": "high",   "label": "KPI ниже плана"},
    "kpi.achieved":         {"priority": "low",    "label": "KPI достигнут"},
    # Audit / security
    "audit.security_flag":  {"priority": "critical", "label": "Подозрительная активность"},
    "rbac.changed":         {"priority": "normal",   "label": "Изменены ваши права"},
    # System
    "system.announcement":  {"priority": "normal", "label": "Объявление"},
    "data.imported":        {"priority": "low",    "label": "Импорт завершён"},
    "report.ready":         {"priority": "low",    "label": "Отчёт готов"},
    # Owner activity feed — every change across all companies (in-app only).
    "owner.activity":       {"priority": "low",    "label": "Изменение в компании"},
    # Watch/Follow — изменения в отслеживаемых проектах/задачах
    "watch.status":         {"priority": "normal", "label": "Статус отслеживаемого"},
    "watch.progress":       {"priority": "normal", "label": "Ход отслеживаемого"},
    "watch.comment":        {"priority": "normal", "label": "Комментарий/файл в отслеживаемом"},
    "watch.deadline":       {"priority": "high",   "label": "Дедлайн отслеживаемого"},
    "watch.result":         {"priority": "normal", "label": "Результат отслеживаемого"},
}


class Notification(Base):
    """A single in-app notification for a user."""

    __tablename__ = "notification"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )

    type:     Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    # low | normal | high | critical

    title:   Mapped[str]            = mapped_column(String(255), nullable=False)
    body:    Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    link_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    source_module:    Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Привязка к компании портфеля (для per-company бейджей в сайдбаре). Nullable —
    # не все уведомления относятся к компании. Резолвится эмиттером (owner.activity
    # резолвит из пути, deadline — из задачи/проекта).
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    source_user_id:   Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    is_read:     Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    delivered_channels: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ─── admin broadcasts + ack ──────────────────────
    broadcast_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_broadcast_template.id", ondelete="SET NULL"), nullable=True,
    )
    broadcast_dispatch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_broadcast_dispatch.id", ondelete="SET NULL"), nullable=True,
    )
    requires_ack:    Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)
    ack_mode:        Mapped[Optional[str]]  = mapped_column(String(16), nullable=True)
    ack_question:    Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    ack_options:     Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    is_sticky:       Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)
    ack_deadline:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ack_response:    Mapped[Optional[dict]]  = mapped_column(JSONB, nullable=True)
    show_site_banner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class NotificationPreference(Base, UUIDMixin, TimestampMixin):
    """Per-user preferences for a single notification type."""

    __tablename__ = "notification_preference"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)

    channels: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"in_app": True})

    is_muted:   Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mute_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    digest_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    # none | daily | weekly

    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_notif_pref"),
    )
