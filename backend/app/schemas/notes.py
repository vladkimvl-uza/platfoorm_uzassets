"""Pydantic schemas для Smart Journal (notes)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

NoteKind = Literal["event", "decision", "task", "risk", "observation"]

ALLOWED_LINK_TYPES = (
    "project",
    "task",
    "kpi_indicator",
    "kpi_manager",
    "esg_issue",
    "esg_metric",
    "board_member",
    "loan",
    "consultant",
    "bp_metric",
    "financial_line",
    "procurement_contract",
    "rating",
)


# === NoteLink ===
class NoteLinkBase(BaseModel):
    entity_type: str = Field(..., max_length=64)
    entity_id: Optional[UUID] = None
    entity_key: Optional[str] = Field(None, max_length=128)
    entity_label: Optional[str] = Field(None, max_length=255)

    @field_validator("entity_type")
    @classmethod
    def _validate_entity_type(cls, v: str) -> str:
        if v not in ALLOWED_LINK_TYPES:
            raise ValueError(
                f"entity_type must be one of {ALLOWED_LINK_TYPES}, got '{v}'"
            )
        return v


class NoteLinkCreate(NoteLinkBase):
    pass


class NoteLinkRead(NoteLinkBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    note_id: UUID
    created_at: datetime


# === Note ===
class NoteBase(BaseModel):
    company_id: Optional[UUID] = None
    entity_type: Optional[str] = Field(None, max_length=64)
    entity_id: Optional[str] = Field(None, max_length=128)

    kind: NoteKind = "observation"
    title: Optional[str] = Field(None, max_length=255)
    body: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)

    color: Optional[str] = Field(None, max_length=16)
    is_pinned: bool = False

    event_date: Optional[datetime] = None
    due_date: Optional[datetime] = None

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, v: list[str]) -> list[str]:
        if not v:
            return []
        # dedup + trim + lower
        cleaned = []
        seen: set[str] = set()
        for t in v:
            tt = (t or "").strip().lower()
            if tt and tt not in seen and len(tt) <= 64:
                seen.add(tt)
                cleaned.append(tt)
        return cleaned[:32]  # cap


class NoteCreate(NoteBase):
    links: list[NoteLinkCreate] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    """Все поля опциональны. Используется для PATCH."""

    company_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None

    kind: Optional[NoteKind] = None
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[list[str]] = None

    color: Optional[str] = None
    is_pinned: Optional[bool] = None

    event_date: Optional[datetime] = None
    due_date: Optional[datetime] = None

    is_resolved: Optional[bool] = None

    # Полная замена набора links (если передан non-None)
    links: Optional[list[NoteLinkCreate]] = None

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        cleaned = []
        seen: set[str] = set()
        for t in v:
            tt = (t or "").strip().lower()
            if tt and tt not in seen and len(tt) <= 64:
                seen.add(tt)
                cleaned.append(tt)
        return cleaned[:32]


class NoteRead(NoteBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: Optional[UUID] = None
    author_id: Optional[UUID] = None
    is_resolved: bool
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    links: list[NoteLinkRead] = Field(default_factory=list)


# === List response ===
class TagCount(BaseModel):
    tag: str
    count: int


class NoteListResponse(BaseModel):
    items: list[NoteRead]
    total: int
    tag_counts: list[TagCount] = Field(default_factory=list)
