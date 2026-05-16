"""IntegrationPartner model (Pack 12.4)."""
from datetime import date, datetime
from typing import Optional
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


PARTNER_KINDS = ["gov_ministry", "portfolio_company", "saas_vendor", "bank", "integrator", "other"]
PARTNER_STATUSES = ["active", "suspended", "terminated"]
PARTNER_TIERS = ["platinum", "gold", "silver", "standard"]


class IntegrationPartner(Base):
    __tablename__ = "integration_partner"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    slug:       Mapped[str]            = mapped_column(String(96), unique=True, nullable=False, index=True)
    name:       Mapped[str]            = mapped_column(String(255), nullable=False)
    legal_name: Mapped[Optional[str]]  = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    kind:   Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str]           = mapped_column(String(16), nullable=False, default="active")
    tier:   Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    contacts: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    tags:     Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    contract_ref:   Mapped[Optional[str]]  = mapped_column(String(128), nullable=True)
    contract_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    contract_end:   Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    owner_id:      Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    owner      = relationship("User", foreign_keys=[owner_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
