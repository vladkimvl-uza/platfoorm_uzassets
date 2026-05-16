"""Users, roles, permissions, sessions.
Authentication is local (username/password + bcrypt + JWT) вЂ” no external IdP."""
from typing import List, Optional
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    Column,
    func,
    LargeBinary,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


# --- Association tables ---
user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_group = Table(
    "user_group",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base, UUIDMixin, TimestampMixin):
    """A platform user. Authenticates locally via username/password (bcrypt)."""

    __tablename__ = "users"

    # Either email or username can be used as the login identifier
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Bcrypt hash; salt is embedded in the hash by bcrypt itself
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Last N bcrypt hashes to enforce no-reuse policy (default 5)
    password_history: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # MFA / TOTP вЂ” enabled in Part 2
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    mfa_recovery_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # в”Ђв”Ђв”Ђ Pack 11.0: External / moderation flags в”Ђв”Ђв”Ђ
    # External user (from a portfolio company or contractor) вЂ” set manually at creation.
    # All write actions go through moderation_submission queue.
    is_external:          Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Even an internal user can be flagged as requires_moderation for sensitive roles.
    requires_moderation:  Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Trusted roles get bypass; owner always bypasses regardless of this flag.
    bypass_moderation:    Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # External org name (informational, e.g. "РђРћ РќР“РњРљ" or "Deloitte audit team")
    external_org_name:    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Failed-login lockout
    failed_login_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Organization context вЂ” ROLE_ORGANIZATION users are tied to a specific company
    organization_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Department context вЂ” most workflow roles (worker/head/director, plan/purchase) are department-scoped
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Sector access scope (optional — narrows what sectors the user can see).
    # NOTE: per-company access has moved from User.allowed_companies (dropped
    # in migration 9aD) to UserGroupRole — see Group(company_id=...).
    allowed_sectors: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Approval-chain helper: who is this user's reviewer / supervisor?
    supervisor_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    # в”Ђв”Ђв”Ђ Pack 12.0: service account в”Ђв”Ђв”Ђ
    is_service_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    service_account_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service_account_owner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # в”Ђв”Ђв”Ђ Pack 12.4: integration partner link (meaningful mainly for service accounts) в”Ђв”Ђв”Ђ
    partner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_partner.id", ondelete="SET NULL"), nullable=True
    )

    # --- Relationships ---

    # ───── Pack 13.0: MFA + Telegram (Telegram chat_id is Fernet-encrypted) ─────
    mfa_method:                     Mapped[str]   = mapped_column(SAEnum("none", "telegram", "totp", "both", name="mfa_method_enum"), nullable=False, server_default="none", default="none")
    mfa_recovery_codes_hashed:      Mapped[list | None]  = mapped_column(ARRAY(String), nullable=True)
    telegram_chat_id_encrypted:     Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    telegram_username:              Mapped[str | None]   = mapped_column(String(64), nullable=True)
    telegram_linked_at:             Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_link_token_hashed:     Mapped[str | None]   = mapped_column(String(128), nullable=True)
    telegram_link_token_expires_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)

    # Pack 13.3: MFA onboarding skip - first-login wizard defer
    mfa_onboarding_skipped_until:   Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[List["Role"]] = relationship(secondary=user_role, back_populates="users", lazy="selectin")
    groups: Mapped[List["Group"]] = relationship(secondary=user_group, back_populates="users", lazy="selectin")
    sessions: Mapped[List["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Role(Base, UUIDMixin, TimestampMixin):
    """A named role from the 22-role taxonomy.
    `code` values match the platform's `ROLE_*` constants exactly."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    name_uz: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name_en: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    description_ru: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    description_uz: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    description_en: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Functional category вЂ” used for grouping in admin UI
    # admin | organization | finance | procurement | treasury | workflow | audit | strategic
    category: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)

    # Approval level for hierarchical workflows (worker=1, head=2, director=3, committee=4)
    approval_level: Mapped[Optional[int]] = mapped_column(default=None, nullable=True)

    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    users: Mapped[List["User"]] = relationship(secondary=user_role, back_populates="roles")
    permissions: Mapped[List["Permission"]] = relationship(
        secondary=role_permission, back_populates="roles", lazy="selectin"
    )


class Permission(Base, UUIDMixin, TimestampMixin):
    """A single capability code (e.g. `procurement.contract.approve`,
    `treasury.payment.approve`, `kpi.edit`)."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # action: view | create | edit | delete | approve | export | admin
    action: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)

    roles: Mapped[List["Role"]] = relationship(secondary=role_permission, back_populates="permissions")


class Group(Base, UUIDMixin, TimestampMixin):
    """A user group.

    Pack 147 — каждая компания имеет 1:1 группу (company_id). Free-form
    группы (audit team, проектная и т.п.) — company_id NULL. Логика
    per-company доступа = membership в группе с company_id != NULL.
    """

    __tablename__ = "groups"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Pack 147: 1:1 group↔company (NULL → free-form group, не привязана).
    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        unique=True, nullable=True, index=True,
    )

    organization_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    users: Mapped[List["User"]] = relationship(secondary=user_group, back_populates="groups")


class UserGroupRole(Base):
    """Role assignment of a user inside a specific group (Pack 147).

    PK (user_id, group_id) — у юзера в каждой группе ровно одна роль.
    """
    __tablename__ = "user_group_role"

    user_id:  Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id",  ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id:  Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id",  ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class RoleByEmail(Base, UUIDMixin, TimestampMixin):
    """Pre-assigned roles for an email вЂ” admin can provision before signup."""

    __tablename__ = "role_by_email"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    role_codes: Mapped[list] = mapped_column(JSONB, nullable=False)
    organization_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    allowed_sectors: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    allowed_companies: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class UserSession(Base, UUIDMixin, TimestampMixin):
    """JWT refresh token record. Access tokens are stateless;
    refresh tokens are tracked here so they can be revoked server-side."""

    __tablename__ = "user_sessions"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


# Indexes
Index("ix_users_email_lower", func.lower(User.email))
Index("ix_users_username_lower", func.lower(User.username))
Index("ix_users_org_dept", User.organization_id, User.department)
Index("ix_user_sessions_active", UserSession.user_id, UserSession.expires_at)
