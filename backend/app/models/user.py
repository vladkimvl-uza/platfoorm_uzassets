"""Users, roles, permissions, sessions.
Authentication is local (username/password + bcrypt + JWT) вЂ” no external IdP."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    # 2026-05-26: JWT access tokens issued before this timestamp are rejected.
    # Bumped on logout, password change, MFA force-disable, role change, deactivate.
    # NULL = no revocation (default).
    tokens_invalid_before: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Last N bcrypt hashes to enforce no-reuse policy (default 5).
    # Legacy plaintext-JSONB form, read-only fallback for users not yet migrated.
    password_history: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Fernet-encrypted JSON-list form , P2-3) — preferred read path,
    # always used on write. Migration 9aS adds the column; lazy backfill on
    # next password change.
    password_history_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # MFA / TOTP вЂ” enabled in Part 2
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    mfa_recovery_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # в”Ђв”Ђв”Ђ External / moderation flags в”Ђв”Ђв”Ђ
    # External user (from a portfolio company or contractor) вЂ” set manually at creation.
    # All write actions go through moderation_submission queue.
    is_external:          Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Trusted users get bypass; owner always bypasses regardless of this flag.
    # followup: requires_moderation column dropped — was dead.)
    bypass_moderation:    Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # External org name (informational, e.g. "РђРћ РќР“РњРљ" or "Deloitte audit team")
    external_org_name:    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Failed-login lockout
    failed_login_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # forgot-password flow via Telegram-code.
    # reset_token = opaque ID returned to client to scope subsequent /verify call.
    # reset_code  = 6-digit one-time code delivered via Telegram, stored as bcrypt.
    password_reset_token_hashed: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    password_reset_code_hashed:  Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    password_reset_expires_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_attempts:     Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Presence — обновляется heartbeat-ом фронта (POST /presence/heartbeat).
    # online/away/offline вычисляется из давности last_seen_at на клиенте.
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Персональный токен для iCal-подписки на дедлайны (read-only фид).
    ical_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Organization context вЂ” ROLE_ORGANIZATION users are tied to a specific company
    organization_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Department context вЂ” most workflow roles (worker/head/director, plan/purchase) are department-scoped
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Фото профиля — resized data-URL (data:image/...;base64,...). Хранится в
    # строке пользователя (без S3); фронт ужимает до ~128px перед отправкой.
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Соцссылки профиля (публичные, показываются в карточке/профиле)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    website_url:  Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Язык интерфейса (ru | uz-latn | uz-cyr | en) — синхронизируется с
    # переключателем фронта; офлайн-каналы (email/Telegram/дайджесты) берут
    # язык отсюда, онлайн-ответы — из заголовка X-UI-Locale (app.core.i18n).
    ui_locale: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'ru'"),
    )

    # Sector access scope (optional — narrows what sectors the user can see).
    # NOTE: per-company access has moved from User.allowed_companies (dropped
    # in migration 9aD) to UserGroupRole — see Group(company_id=...).
    allowed_sectors: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # ─── Маршрутизация модерации ───
    # Кого назначили согласующими лично этому пользователю (список id).
    # Пусто → работает маршрут по сектору, затем общий фолбэк.
    moderator_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Для внутреннего пользователя: какие секторы он ведёт как согласующий.
    # Заявки авторов из компаний этих секторов приходят ему.
    moderated_sector_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Approval-chain helper: who is this user's reviewer / supervisor?
    supervisor_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    # в”Ђв”Ђв”Ђ service account в”Ђв”Ђв”Ђ
    is_service_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    service_account_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service_account_owner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # в”Ђв”Ђв”Ђ integration partner link (meaningful mainly for service accounts) в”Ђв”Ђв”Ђ
    partner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_partner.id", ondelete="SET NULL"), nullable=True
    )

    # --- Relationships ---

    # ───── MFA + Telegram (Telegram chat_id is Fernet-encrypted) ─────
    mfa_method:                     Mapped[str]   = mapped_column(SAEnum("none", "telegram", "totp", "both", name="mfa_method_enum"), nullable=False, server_default="none", default="none")
    # Legacy plaintext-array column (bcrypt hashes). Read-only fallback.
    mfa_recovery_codes_hashed:      Mapped[list | None]  = mapped_column(ARRAY(String), nullable=True)
    # Fernet-encrypted JSON-list form , P2-4) — preferred on read,
    # always written on regenerate.
    mfa_recovery_codes_enc:         Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    telegram_chat_id_encrypted:     Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    telegram_username:              Mapped[str | None]   = mapped_column(String(64), nullable=True)
    telegram_linked_at:             Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_link_token_hashed:     Mapped[str | None]   = mapped_column(String(128), nullable=True)
    telegram_link_token_expires_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)

    # MFA onboarding skip - first-login wizard defer
    mfa_onboarding_skipped_until:   Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)

    # First-login welcome / profile-completion modal — shown once until dismissed.
    welcome_seen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")

    # Первичная настройка профиля (компания/сектор) завершена. Юзер задаёт эти
    # поля сам ОДИН раз (при первой настройке); далее меняет только admin/owner.
    org_profile_set: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")

    # Step-up: время последней «сильной» аутентификации (пароль/MFA/re-auth) —
    # для повторной проверки перед чувствительными операциями (841 п.5.2.4).
    last_strong_auth_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)

    # ЕСИ / One ID (Единая система идентификации) — привязка к нац. SSO.
    # oneid_sub — стабильный субъект из userinfo; pinfl — ПИНФЛ заявителя.
    oneid_sub:       Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    pinfl:           Mapped[Optional[str]] = mapped_column(String(14), index=True, nullable=True)
    oneid_linked_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list["Role"]] = relationship(secondary=user_role, back_populates="users", lazy="selectin")
    groups: Mapped[list["Group"]] = relationship(secondary=user_group, back_populates="users", lazy="selectin")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


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

    users: Mapped[list["User"]] = relationship(secondary=user_role, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
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

    roles: Mapped[list["Role"]] = relationship(secondary=role_permission, back_populates="permissions")


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

    # 1:1 group↔company (NULL → free-form group, не привязана).
    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        unique=True, nullable=True, index=True,
    )

    organization_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    users: Mapped[list["User"]] = relationship(secondary=user_group, back_populates="groups")


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
    # Стабильная метка старта «цепочки» сессии (переносится через ротации
    # refresh) — для абсолютного таймаута. created_at = время последней ротации
    # (для idle-таймаута).
    session_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


# Indexes
Index("ix_users_email_lower", func.lower(User.email))
Index("ix_users_username_lower", func.lower(User.username))
Index("ix_users_org_dept", User.organization_id, User.department)
Index("ix_user_sessions_active", UserSession.user_id, UserSession.expires_at)
