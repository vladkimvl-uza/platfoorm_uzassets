"""Integration partner schemas (Pack 12.4)."""
from datetime import date, datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


PartnerKind   = Literal["gov_ministry", "portfolio_company", "saas_vendor", "bank", "integrator", "other"]
PartnerStatus = Literal["active", "suspended", "terminated"]
PartnerTier   = Literal["platinum", "gold", "silver", "standard"]


class PartnerContact(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role:  Optional[str] = None


class IntegrationPartnerCreate(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_-]{1,94}$")
    name: str
    legal_name: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[PartnerKind] = None
    status: PartnerStatus = "active"
    tier:   Optional[PartnerTier] = None
    contacts: Optional[List[PartnerContact]] = None
    tags: Optional[List[str]] = None
    contract_ref: Optional[str] = None
    contract_start: Optional[date] = None
    contract_end:   Optional[date] = None
    owner_id: Optional[UUID] = None
    notes: Optional[str] = None


class IntegrationPartnerUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[PartnerKind] = None
    status: Optional[PartnerStatus] = None
    tier:   Optional[PartnerTier] = None
    contacts: Optional[List[PartnerContact]] = None
    tags: Optional[List[str]] = None
    contract_ref: Optional[str] = None
    contract_start: Optional[date] = None
    contract_end:   Optional[date] = None
    owner_id: Optional[UUID] = None
    notes: Optional[str] = None


class IntegrationPartnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    slug: str
    name: str
    legal_name: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[PartnerKind] = None
    status: PartnerStatus
    tier:   Optional[PartnerTier] = None
    contacts: Optional[List[PartnerContact]] = None
    tags: Optional[List[str]] = None
    contract_ref: Optional[str] = None
    contract_start: Optional[date] = None
    contract_end:   Optional[date] = None
    owner_id: Optional[UUID] = None
    created_by_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Computed counts (populated by service layer)
    service_accounts_count: int = 0
    api_keys_count: int = 0
    webhooks_count: int = 0
    external_apis_count: int = 0


class IntegrationPartnerListResponse(BaseModel):
    items: List[IntegrationPartnerRead]
    total: int


# ─── Linked resources (one partner → many resources) ─────────

class PartnerLinkedResource(BaseModel):
    """A resource attached to a partner. Polymorphic."""
    resource_type: Literal["service_account", "external_api", "webhook"]
    resource_id: UUID
    label: str
    extra: Optional[dict] = None


class PartnerResourcesResponse(BaseModel):
    partner_id: UUID
    service_accounts: List[PartnerLinkedResource]
    external_apis:    List[PartnerLinkedResource]
    webhooks:         List[PartnerLinkedResource]


class PartnerLinkPayload(BaseModel):
    """Attach/detach a resource to a partner."""
    resource_type: Literal["service_account", "external_api", "webhook"]
    resource_id: UUID
