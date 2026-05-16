"""ApiKey model (Pack 12.0).

A token issued to a service account. The plaintext token is shown ONCE at
creation; only the HMAC-SHA256 hash is stored. Verification matches by prefix
lookup + constant-time HMAC comparison.
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApiKey(Base):
    """Issued API token for a service account."""
    __tablename__ = "api_key"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    service_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    name:        Mapped[str]            = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    # Token: `prefix` is uza_pk_{env}_{8-char nonce}. Full token = prefix + "_" + 36-char body.
    prefix:    Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    hash_hmac: Mapped[str] = mapped_column(String(128), nullable=False)

    scopes:        Mapped[list]          = mapped_column(JSONB, nullable=False, default=list)
    environment:   Mapped[str]           = mapped_column(String(16), nullable=False, default="sandbox")
    rate_limit_per_minute: Mapped[int]   = mapped_column(Integer, nullable=False, default=600)
    ip_allowlist:  Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    expires_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    revoke_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[Optional[str]]      = mapped_column(INET, nullable=True)
    total_calls:  Mapped[int]                = mapped_column(Integer, nullable=False, default=0)
    failed_calls: Mapped[int]                = mapped_column(Integer, nullable=False, default=0)

    service_account = relationship("User", foreign_keys=[service_account_id])
    created_by      = relationship("User", foreign_keys=[created_by_id])

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    def is_usable(self, now: datetime) -> bool:
        return not self.is_revoked and not self.is_expired(now)


# Helper constants
KEY_PREFIX_LIVE    = "uza_pk_live_"
KEY_PREFIX_SANDBOX = "uza_pk_test_"

KEY_ENVIRONMENTS = [
    {"code": "production", "label": "Production", "prefix": KEY_PREFIX_LIVE,    "color": "#1D9E75"},
    {"code": "sandbox",    "label": "Sandbox",    "prefix": KEY_PREFIX_SANDBOX, "color": "#EF9F27"},
]
