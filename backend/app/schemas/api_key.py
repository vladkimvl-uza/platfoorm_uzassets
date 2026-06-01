"""Pydantic schemas for API keys + service accounts (Pack 12.0)."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Environment = Literal["production", "sandbox"]


# ─── Service Account ──────────────────────────────────────────

class ServiceAccountCreate(BaseModel):
    email: EmailStr
    full_name: str
    description: Optional[str] = None
    owner_id: Optional[UUID] = None  # which human user manages this SA; defaults to caller


class ServiceAccountUpdate(BaseModel):
    full_name: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class ServiceAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    full_name: Optional[str] = None
    description: Optional[str] = Field(default=None, alias="service_account_description")
    owner_id: Optional[UUID] = Field(default=None, alias="service_account_owner_id")
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    keys_count: Optional[int] = None  # populated by service layer


class ServiceAccountListResponse(BaseModel):
    items: list[ServiceAccountRead]
    total: int


# ─── API Key ──────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    service_account_id: UUID
    name: str
    description: Optional[str] = None
    scopes: list[str] = Field(default_factory=list, description="List of permission codes")
    environment: Environment = "sandbox"
    rate_limit_per_minute: int = Field(default=600, ge=10, le=60000)
    ip_allowlist: Optional[list[str]] = None  # CIDR strings
    expires_at: Optional[datetime] = None


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scopes: Optional[list[str]] = None
    rate_limit_per_minute: Optional[int] = Field(default=None, ge=10, le=60000)
    ip_allowlist: Optional[list[str]] = None
    expires_at: Optional[datetime] = None


class ApiKeyRevoke(BaseModel):
    reason: Optional[str] = None


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    service_account_id: UUID
    created_by_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    prefix: str                # e.g. "uza_pk_live_4f8a"; the part visible in lists
    scopes: list[str]
    environment: Environment
    rate_limit_per_minute: int
    ip_allowlist: Optional[list[str]] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by_id: Optional[UUID] = None
    revoke_reason: Optional[str] = None
    last_used_at: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    total_calls: int
    failed_calls: int
    created_at: datetime
    updated_at: datetime


class ApiKeyCreated(ApiKeyRead):
    """Returned ONLY at creation time — includes the plaintext token.

    The token is unrecoverable after this response. Show ONCE in UI.
    """
    plaintext_token: str


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyRead]
    total: int


# ─── Catalog (enriched OpenAPI) ───────────────────────────────

class CatalogEndpoint(BaseModel):
    path: str
    method: str         # GET | POST | PATCH | DELETE | WEBSOCKET
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    module: Optional[str] = None
    required_permission: Optional[str] = None
    request_schema_ref: Optional[str] = None
    response_schema_ref: Optional[str] = None
    deprecated: bool = False


class CatalogModule(BaseModel):
    name: str
    group: Optional[str] = None  # e.g. "Финансы"
    description: Optional[str] = None
    endpoints_count: int = 0


class CatalogSummary(BaseModel):
    title: str
    version: str
    total_endpoints: int
    modules: list[CatalogModule]
    endpoints: list[CatalogEndpoint]


class ScopeItem(BaseModel):
    code: str
    name: str
    module: Optional[str] = None
    description: Optional[str] = None


# ─── API UI Phase 5.1 — per-company catalog + try-it-out ──────

AccessLevel = Literal["public", "authed", "admin"]


class CatalogEndpointWithSubstitution(CatalogEndpoint):
    """Endpoint with placeholder substitution applied (e.g. {id} → '<uuid>')."""
    display_path: str
    substitutions: dict[str, str] = Field(default_factory=dict)
    access_level: AccessLevel = "authed"


class CompanyCatalogResponse(BaseModel):
    company_id: UUID
    company_name: str
    endpoints: list[CatalogEndpointWithSubstitution]
    tabs: list[str] = Field(default_factory=list)
    access_level: AccessLevel = "authed"


class TryRequest(BaseModel):
    method: Literal["GET", "POST", "PATCH", "PUT", "DELETE"] = "GET"
    path: str = Field(..., description="Absolute path beginning with / (will be prefixed with backend base)")
    headers: dict[str, str] = Field(default_factory=dict)
    body: Optional[dict] = None
    confirm_destructive: bool = False


class TryResponse(BaseModel):
    status_code: int
    headers: dict[str, str]
    body: Optional[str] = None
    duration_ms: int
    truncated: bool = False


class ScopeListResponse(BaseModel):
    items: list[ScopeItem]
    grouped_by_module: dict[str, list[ScopeItem]]


# ─── Audit ────────────────────────────────────────────────────

class ApiKeyAuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    api_key_id: Optional[UUID] = None
    actor_id: Optional[UUID] = None
    http_method: Optional[str] = None
    http_path: Optional[str] = None
    http_status: Optional[int] = None
    duration_ms: Optional[int] = None
    ip_address: Optional[str] = None


class ApiKeyAuditResponse(BaseModel):
    items: list[ApiKeyAuditEntry]
    total: int
