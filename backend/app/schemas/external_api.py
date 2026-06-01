"""External API schemas (Pack 12.2)."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Status = Literal["active", "sandbox", "deprecated", "disabled"]
AuthKind = Literal["oauth2", "api_key", "basic", "mtls", "jwt", "none"]
EnvKind = Literal["production", "sandbox", "on-prem"]


class ContactDef(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role:  Optional[str] = None


class ExternalApiCreate(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_-]{1,94}$")
    name: str
    description: Optional[str] = None
    base_url: HttpUrl
    documentation_url: Optional[HttpUrl] = None
    health_check_url:  Optional[HttpUrl] = None
    status: Status = "active"
    owner_id: Optional[UUID] = None
    contacts: Optional[list[ContactDef]] = None
    tags: Optional[list[str]] = None
    environment_kind: Optional[EnvKind] = None
    auth_kind: Optional[AuthKind] = "none"
    auth_details: Optional[dict] = None
    notes: Optional[str] = None


class ExternalApiUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[HttpUrl] = None
    documentation_url: Optional[HttpUrl] = None
    health_check_url:  Optional[HttpUrl] = None
    status: Optional[Status] = None
    owner_id: Optional[UUID] = None
    contacts: Optional[list[ContactDef]] = None
    tags: Optional[list[str]] = None
    environment_kind: Optional[EnvKind] = None
    auth_kind: Optional[AuthKind] = None
    auth_details: Optional[dict] = None
    notes: Optional[str] = None


class ExternalApiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    base_url: str
    documentation_url: Optional[str] = None
    health_check_url: Optional[str] = None
    status: Status
    owner_id: Optional[UUID] = None
    created_by_id: Optional[UUID] = None
    contacts: Optional[list[ContactDef]] = None
    tags: Optional[list[str]] = None
    environment_kind: Optional[EnvKind] = None
    auth_kind: Optional[AuthKind] = None
    auth_details: Optional[dict] = None
    openapi_spec_version: Optional[str] = None
    openapi_uploaded_at: Optional[datetime] = None
    openapi_uploaded_by_id: Optional[UUID] = None
    has_openapi_spec: bool = False
    notes: Optional[str] = None
    endpoint_count: int
    created_at: datetime
    updated_at: datetime


class ExternalApiListResponse(BaseModel):
    items: list[ExternalApiRead]
    total: int


# ─── OpenAPI spec handling ─────────────────────────────────────

class OpenApiUploadRequest(BaseModel):
    """Upload an OpenAPI 3.x spec as raw JSON (parsed and validated server-side)."""
    spec: dict  # the full OpenAPI document


class OpenApiUploadResponse(BaseModel):
    version: str
    endpoint_count: int
    title: Optional[str] = None
    uploaded_at: datetime


# ─── Endpoint summary (extracted from spec) ────────────────────

class ExtEndpoint(BaseModel):
    path: str
    method: str
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    deprecated: bool = False


class ExtCatalogSummary(BaseModel):
    api_id: UUID
    title: str
    version: str
    description: Optional[str] = None
    servers: list[dict] = Field(default_factory=list)
    total_endpoints: int
    endpoints: list[ExtEndpoint]
