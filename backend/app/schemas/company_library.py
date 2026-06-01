"""Company Library (MDM) — Phase 1 Pydantic v2 schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Field definitions ──────────────────────────────────────────────────

FieldType = Literal["number", "text", "date", "enum", "formula", "boolean"]
ScopeType = Literal["all", "sector", "companies"]
Layout    = Literal["one_col", "two_col", "grid"]


class FieldDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name_ru: str
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    field_type: FieldType
    unit: Optional[str] = None
    format_pattern: Optional[str] = None
    enum_values: Optional[Any] = None
    formula: Optional[str] = None
    scope_type: ScopeType
    scope_value: Optional[Any] = None
    source_module: Optional[str] = None
    source_path: Optional[str] = None
    permission_view: Optional[str] = None
    permission_edit: Optional[str] = None
    is_system: bool
    sort_order: int
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class FieldDefinitionCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    name_ru: str = Field(..., min_length=1, max_length=255)
    name_uz: Optional[str] = Field(None, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    field_type: FieldType
    unit: Optional[str] = Field(None, max_length=32)
    format_pattern: Optional[str] = Field(None, max_length=64)
    enum_values: Optional[list[str]] = None
    formula: Optional[str] = None
    scope_type: ScopeType = "all"
    scope_value: Optional[Any] = None
    source_module: Optional[str] = Field(None, max_length=64)
    source_path: Optional[str] = Field(None, max_length=255)
    permission_view: Optional[str] = Field(None, max_length=128)
    permission_edit: Optional[str] = Field(None, max_length=128)
    sort_order: int = 100


class FieldDefinitionUpdate(BaseModel):
    name_ru: Optional[str] = Field(None, min_length=1, max_length=255)
    name_uz: Optional[str] = Field(None, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    unit: Optional[str] = Field(None, max_length=32)
    format_pattern: Optional[str] = Field(None, max_length=64)
    enum_values: Optional[list[str]] = None
    formula: Optional[str] = None
    scope_type: Optional[ScopeType] = None
    scope_value: Optional[Any] = None
    permission_view: Optional[str] = Field(None, max_length=128)
    permission_edit: Optional[str] = Field(None, max_length=128)
    sort_order: Optional[int] = None


# ── Library views (per-user column prefs) ──────────────────────────────

class LibraryViewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    is_default: bool
    visible_columns: list[str]
    filters: dict[str, Any]
    sort_by: Optional[str] = None
    sort_dir: str
    created_at: datetime
    updated_at: datetime


class LibraryViewCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    is_default: bool = False
    visible_columns: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    sort_by: Optional[str] = Field(None, max_length=64)
    sort_dir: Literal["asc", "desc"] = "desc"


class LibraryViewUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    is_default: Optional[bool] = None
    visible_columns: Optional[list[str]] = None
    filters: Optional[dict[str, Any]] = None
    sort_by: Optional[str] = Field(None, max_length=64)
    sort_dir: Optional[Literal["asc", "desc"]] = None


# ── Library tabs ───────────────────────────────────────────────────────

class LibraryTabRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name_ru: str
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    field_codes: list[str]
    layout: Layout
    is_system: bool
    sort_order: int
    scope_type: ScopeType
    scope_value: Optional[Any] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class LibraryTabCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    name_ru: str = Field(..., min_length=1, max_length=255)
    name_uz: Optional[str] = Field(None, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    field_codes: list[str] = Field(default_factory=list)
    layout: Layout = "two_col"
    sort_order: int = 100
    scope_type: ScopeType = "all"
    scope_value: Optional[Any] = None


class LibraryTabUpdate(BaseModel):
    name_ru: Optional[str] = Field(None, min_length=1, max_length=255)
    name_uz: Optional[str] = Field(None, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    field_codes: Optional[list[str]] = None
    layout: Optional[Layout] = None
    sort_order: Optional[int] = None
    scope_type: Optional[ScopeType] = None
    scope_value: Optional[Any] = None


# ── Library list/detail responses ──────────────────────────────────────

class LibraryCompanyRow(BaseModel):
    """Row in the library index. `fields` is a flat dict keyed by field code."""
    id: UUID
    code: Optional[str] = None
    name_ru: str
    name_short: Optional[str] = None
    sector_id: Optional[UUID] = None
    sector_name: Optional[str] = None
    fields: dict[str, Any] = Field(default_factory=dict)


class LibraryListResponse(BaseModel):
    items: list[LibraryCompanyRow]
    total: int
    columns: list[FieldDefinitionRead]
    available_views: list[LibraryViewRead] = Field(default_factory=list)
    active_view_id: Optional[UUID] = None


class LibraryFieldValue(BaseModel):
    """One field's value on a detail-view, with provenance."""
    code: str
    value: Any = None
    source_module: Optional[str] = None
    source_updated_at: Optional[datetime] = None
    source_actor: Optional[str] = None


class LibraryActivityEntry(BaseModel):
    ts: datetime
    actor_email: Optional[str] = None
    module: Optional[str] = None
    action: str
    field_code: Optional[str] = None
    diff: Optional[dict[str, Any]] = None


class LibraryCompanyDetail(BaseModel):
    company_id: UUID
    company_code: Optional[str] = None
    company_name: str
    sector_id: Optional[UUID] = None
    sector_name: Optional[str] = None
    fields: list[LibraryFieldValue]
    tabs: list[LibraryTabRead]
    activity: list[LibraryActivityEntry] = Field(default_factory=list)


# ── Field-write payload ────────────────────────────────────────────────

class FieldWriteRequest(BaseModel):
    value: Any = None
    reason: Optional[str] = None


class FieldWriteResponse(BaseModel):
    code: str
    value: Any = None
    source_module: Optional[str] = None
    updated_at: datetime
    routed_to: Optional[str] = None  # textual hint where the write went
