"""Audit log of all platform actions (Pack 9.0).

Append-only. HMAC chain for tamper-evidence (prev_hash → entry_hash).
Every meaningful request emits one row via AuditLoggerMiddleware.
"""
import uuid
from typing import Optional

from sqlalchemy import (
    Boolean,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# ВАЖНО: у audit_log НЕТ внешних ключей на users/api_key.
#
# Раньше `actor_id` ссылался на `users.id` с ON DELETE SET NULL, а `actor_id`
# входит в тело HMAC. Жёсткое удаление пользователя обнуляло его во ВСЕХ
# исторических строках — содержимое строки менялось после подписи, и цепочка
# рвалась. На проде так сломались 837 строк из 77 639 (1.08%) с 23.06.2026:
# у всех actor_id = NULL, а первая принадлежала уже удалённому аккаунту.
#
# Журнал аудита append-only: операции над другими таблицами не имеют права его
# править. Связь оставлена логической — id хранится, даже если аккаунт удалён.


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """A single audit log entry. Append-only."""

    __tablename__ = "audit_log"

    # ─── Who ─────────────────────────────────────
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True, index=True,
    )
    actor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role:  Mapped[Optional[str]] = mapped_column(String(64),  nullable=True)

    # ─── What ────────────────────────────────────
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # VIEW | CREATE | UPDATE | DELETE | LOGIN | FAILED_LOGIN | LOGOUT | EXPORT | IMPORT

    module: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # kpi | bp | governance | esg | financials | procurement | admin | audit

    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    entity_id:   Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    entity_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # human-readable: "НГМК 2026 · Q3 Выручка"

    # ─── HTTP ────────────────────────────────────
    http_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    http_path:   Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ─── Diff / extras ───────────────────────────
    diff:    Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    meta:    Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes:   Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    # ─── Context ─────────────────────────────────
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ─── HMAC chain (tamper-evidence) ────────────
    prev_hash:  Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    entry_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)

    # ─── link to API key if call was authenticated via API key ───
    api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )


# Composite indexes for common queries
Index("ix_audit_actor_action_time",  AuditLog.actor_id, AuditLog.action, AuditLog.created_at)
Index("ix_audit_entity_time",        AuditLog.entity_type, AuditLog.entity_id, AuditLog.created_at)
Index("ix_audit_module_time",        AuditLog.module, AuditLog.created_at)
Index("ix_audit_action_time",        AuditLog.action, AuditLog.created_at)
Index("ix_audit_critical_time",      AuditLog.created_at, postgresql_where=AuditLog.is_critical.is_(True))
