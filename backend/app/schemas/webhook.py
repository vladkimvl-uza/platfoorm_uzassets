"""Webhook schemas (Pack 12.1)."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebhookEventDef(BaseModel):
    code: str
    module: str
    label: str
    description: str
    payload_keys: list[str]


class WebhookEventCatalogResponse(BaseModel):
    events: list[WebhookEventDef]
    grouped_by_module: dict[str, list[WebhookEventDef]]


class WebhookSubscriptionCreate(BaseModel):
    service_account_id: UUID
    name: str
    description: Optional[str] = None
    target_url: HttpUrl
    events: list[str] = Field(default_factory=list)   # event codes or wildcards
    verify_ssl: bool = True
    custom_headers: Optional[dict[str, str]] = None
    max_attempts: int = Field(default=5, ge=1, le=12)
    timeout_seconds: int = Field(default=10, ge=2, le=60)


class WebhookSubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_url: Optional[HttpUrl] = None
    events: Optional[list[str]] = None
    verify_ssl: Optional[bool] = None
    custom_headers: Optional[dict[str, str]] = None
    max_attempts: Optional[int] = Field(default=None, ge=1, le=12)
    timeout_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    is_active: Optional[bool] = None


class WebhookSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    service_account_id: UUID
    created_by_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    target_url: str
    secret_hint: str        # "…ab12" — last 4 chars only
    verify_ssl: bool
    custom_headers: Optional[dict] = None
    events: list[str]
    is_active: bool
    disabled_at: Optional[datetime] = None
    disabled_reason: Optional[str] = None
    max_attempts: int
    timeout_seconds: int
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    total_deliveries: int
    total_failures: int
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionCreated(WebhookSubscriptionRead):
    """One-time response that includes the plaintext signing secret."""
    plaintext_secret: str


class WebhookSubscriptionListResponse(BaseModel):
    items: list[WebhookSubscriptionRead]
    total: int


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    subscription_id: UUID
    event_code: str
    event_payload: Any  # JSONB
    correlation_id: Optional[UUID] = None
    status: str
    attempt_number: int
    scheduled_at: datetime
    attempted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    signature: Optional[str] = None
    timestamp_sent: Optional[int] = None
    http_status: Optional[int] = None
    response_body_snippet: Optional[str] = None
    response_headers_snippet: Optional[dict] = None
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    is_replay: bool
    replay_of_id: Optional[UUID] = None
    created_at: datetime


class WebhookDeliveryListResponse(BaseModel):
    items: list[WebhookDeliveryRead]
    total: int


class WebhookTestRequest(BaseModel):
    """Synthetic event to verify endpoint connectivity."""
    payload: Optional[dict] = None  # caller-defined payload; defaults to a tiny object


class WebhookDeliveryReplayRequest(BaseModel):
    """Replay an existing delivery — re-sends the same payload."""
    pass
