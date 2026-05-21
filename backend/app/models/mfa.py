"""MFA and Telegram models (Pack 13.0).

NB: Base class is auto-discovered вЂ” adjust the import below if your project
uses a different module path (`app.db.base`, `app.database.base_class`, etc).
The deploy script also handles this via sed-fixup.
"""
import enum
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary,
    String, Text, Time,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# в”Ђв”Ђ Enums (string-valued for clean DB representation) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

class MfaMethod(str, enum.Enum):
    NONE = "none"
    TELEGRAM = "telegram"
    TOTP = "totp"
    BOTH = "both"


class OutboxType(str, enum.Enum):
    MFA_CODE = "mfa_code"
    LINK_CONFIRMATION = "link_confirmation"
    NOTIFICATION = "notification"
    TEST = "test"


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DISCARDED = "discarded"


# в”Ђв”Ђ One-shot login codes (6 digits, TTL 5 min, single use) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

class MfaLoginChallenge(Base):
    __tablename__ = "mfa_login_challenge"

    id:           Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:      Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hashed:  Mapped[str]        = mapped_column(String(128), nullable=False)
    created_at:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at:      Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts:     Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    ip_address:   Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent:   Mapped[str | None] = mapped_column(String(256), nullable=True)


# в”Ђв”Ђ Outbound message queue в†’ consumed by uza-tg-bot worker в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

class TelegramOutbox(Base):
    __tablename__ = "telegram_outbox"

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:        Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type:           Mapped[OutboxType]   = mapped_column(
        SAEnum(OutboxType, name="telegram_outbox_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status:         Mapped[OutboxStatus] = mapped_column(
        SAEnum(OutboxStatus, name="telegram_outbox_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=OutboxStatus.PENDING, index=True,
    )
    payload:        Mapped[dict]         = mapped_column(JSONB, nullable=False)
    inline_buttons: Mapped[list | None]  = mapped_column(JSONB, nullable=True)
    created_at:     Mapped[datetime]     = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    attempted_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts:       Mapped[int]          = mapped_column(Integer, nullable=False, default=0)
    last_error:     Mapped[str | None]   = mapped_column(Text, nullable=True)
    tg_message_id:  Mapped[int | None]   = mapped_column(BigInteger, nullable=True)


# в”Ђв”Ђ Per-user notification routing prefs в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

class UserTelegramPref(Base):
    __tablename__ = "user_telegram_pref"

    user_id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled:             Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    type_assignments:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    type_mentions:       Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    type_deadlines:      Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    type_moderation:     Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    type_broadcasts:     Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    type_system:         Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiet_hours_start:   Mapped[time] = mapped_column(Time, nullable=False, default=time(22, 0))
    quiet_hours_end:     Mapped[time] = mapped_column(Time, nullable=False, default=time(7, 0))
    timezone:            Mapped[str]  = mapped_column(String(64), nullable=False, default="Asia/Tashkent")
    updated_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
