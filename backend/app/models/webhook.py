"""Webhook models (Pack 12.1)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Delivery states
WD_PENDING   = "pending"
WD_SUCCEEDED = "succeeded"
WD_FAILED    = "failed"      # final attempt failed but more retries left → re-scheduled
WD_EXHAUSTED = "exhausted"   # max_attempts reached
WD_CANCELLED = "cancelled"


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscription"

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

    target_url:  Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_hint: Mapped[str] = mapped_column(String(16),  nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_plain: Mapped[str] = mapped_column(Text, nullable=False)
    verify_ssl:  Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    custom_headers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    events: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    is_active:       Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    disabled_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    max_attempts:    Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_deliveries:     Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_failures:       Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # link to integration partner
    partner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_partner.id", ondelete="SET NULL"), nullable=True,
    )

    service_account = relationship("User", foreign_keys=[service_account_id])
    created_by      = relationship("User", foreign_keys=[created_by_id])


class WebhookDelivery(Base):
    __tablename__ = "webhook_delivery"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_subscription.id", ondelete="CASCADE"), nullable=False,
    )
    event_code:    Mapped[str]  = mapped_column(String(128), nullable=False)
    event_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    status:         Mapped[str] = mapped_column(String(16), nullable=False, default=WD_PENDING)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempted_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at:  Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    signature:      Mapped[Optional[str]]  = mapped_column(String(128), nullable=True)
    timestamp_sent: Mapped[Optional[int]]  = mapped_column(BigInteger,  nullable=True)

    http_status:           Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    response_body_snippet: Mapped[Optional[str]]  = mapped_column(Text,    nullable=True)
    response_headers_snippet: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message:         Mapped[Optional[str]]  = mapped_column(Text,    nullable=True)
    duration_ms:           Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)

    is_replay:    Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    replay_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_delivery.id", ondelete="SET NULL"), nullable=True,
    )
