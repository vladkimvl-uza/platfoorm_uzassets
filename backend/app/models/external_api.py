"""ExternalApi model (Pack 12.2)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Allowed status values
EXT_STATUSES = ["active", "sandbox", "deprecated", "disabled"]
AUTH_KINDS   = ["oauth2", "api_key", "basic", "mtls", "jwt", "none"]
ENV_KINDS    = ["production", "sandbox", "on-prem"]


class ExternalApi(Base):
    __tablename__ = "external_api"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    slug: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    base_url:         Mapped[str]            = mapped_column(String(1024), nullable=False)
    documentation_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    health_check_url: Mapped[Optional[str]]  = mapped_column(String(1024), nullable=True)
    status:           Mapped[str]            = mapped_column(String(16), nullable=False, default="active")

    owner_id:      Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contacts:      Mapped[Optional[list]]      = mapped_column(JSONB, nullable=True)
    tags:          Mapped[Optional[list]]      = mapped_column(JSONB, nullable=True)
    environment_kind: Mapped[Optional[str]]    = mapped_column(String(32), nullable=True)

    auth_kind:    Mapped[Optional[str]]  = mapped_column(String(32),  nullable=True)
    auth_details: Mapped[Optional[dict]] = mapped_column(JSONB,       nullable=True)

    openapi_spec:           Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    openapi_spec_version:   Mapped[Optional[str]]  = mapped_column(String(32), nullable=True)
    openapi_uploaded_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    openapi_uploaded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    notes:          Mapped[Optional[str]] = mapped_column(Text,    nullable=True)
    endpoint_count: Mapped[int]           = mapped_column(Integer, nullable=False, default=0)

    # link to integration partner
    partner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_partner.id", ondelete="SET NULL"), nullable=True,
    )

    owner               = relationship("User", foreign_keys=[owner_id])
    created_by          = relationship("User", foreign_keys=[created_by_id])
    openapi_uploaded_by = relationship("User", foreign_keys=[openapi_uploaded_by_id])
