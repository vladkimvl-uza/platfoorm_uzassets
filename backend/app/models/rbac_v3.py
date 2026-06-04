"""RBAC v3 models — содержит только реально используемую сущность.

Direct user grants, module visibility, templates и change_log из старой v2
удалены вместе с таблицами (см. alembic-миграцию 9aC_drop_rbac_v2_unused).
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class GroupPermissionGrant(Base, UUIDMixin, TimestampMixin):
    """Permission grant on group level. All members of the group inherit.

    `grant_type='grant'` — добавляет право, `grant_type='deny'` — отзывает
    (override роли, см. core/security.has_effective_permission).
    """
    __tablename__ = "group_permission_grant"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    permission_code: Mapped[str] = mapped_column(String(128), nullable=False)
    grant_type:      Mapped[str] = mapped_column(String(16), nullable=False, default="grant")

    scope_companies: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    scope_sectors:   Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    scope_years:     Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    expires_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    granted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    __table_args__ = (UniqueConstraint("group_id", "permission_code", name="uq_group_perm_grant"),)


class UserPermissionGrant(Base, UUIDMixin, TimestampMixin):
    """Прямой per-user грант права (overlay поверх ролей/групп).

    `grant_type='grant'` — добавляет право конкретному пользователю,
    `grant_type='deny'` — отзывает (override роли). Учитывается в
    core/security.has_effective_permission и effective_permission_codes.
    Редактируется OWNER/ADMIN через сетку «Доступ к модулям».
    """
    __tablename__ = "user_permission_grant"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    permission_code: Mapped[str] = mapped_column(String(128), nullable=False)
    grant_type:      Mapped[str] = mapped_column(String(16), nullable=False, default="grant")
    expires_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    granted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    __table_args__ = (UniqueConstraint("user_id", "permission_code", name="uq_user_perm_grant"),)
