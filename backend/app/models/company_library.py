"""Company Library (MDM) — Phase 1 models.

- FieldDefinition: schema of available custom fields (system + user-created)
- CompanyLibraryView: per-user column presets for the index page
- CompanyLibraryTab:  system + custom tabs for the Detail view

These tables are paired with `companies.custom_data` JSONB column that stores
the actual values for non-system / sector-scoped / formula fields.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# ── Allowed string-enum value sets (validated at API layer) ────────────
FIELD_TYPES = ("number", "text", "date", "enum", "formula", "boolean")
SCOPE_TYPES = ("all", "sector", "companies")
LAYOUTS     = ("one_col", "two_col", "grid")


class FieldDefinition(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "field_definitions"

    code:           Mapped[str]            = mapped_column(String(128), unique=True, index=True, nullable=False)
    name_ru:        Mapped[str]            = mapped_column(String(255), nullable=False)
    name_uz:        Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    name_en:        Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)

    field_type:     Mapped[str]            = mapped_column(String(32), nullable=False)
    unit:           Mapped[Optional[str]]  = mapped_column(String(32), nullable=True)
    format_pattern: Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    enum_values:    Mapped[Optional[Any]]  = mapped_column(JSONB, nullable=True)
    formula:        Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    scope_type:     Mapped[str]            = mapped_column(String(32), nullable=False, default="all")
    scope_value:    Mapped[Optional[Any]]  = mapped_column(JSONB, nullable=True)

    source_module:  Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    source_path:    Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)

    permission_view: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    permission_edit: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    is_system:      Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
    sort_order:     Mapped[int]            = mapped_column(Integer, default=100, nullable=False)
    created_by:     Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )


class CompanyLibraryView(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "company_library_views"

    user_id:          Mapped[uuid.UUID]    = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name:             Mapped[str]          = mapped_column(String(128), nullable=False)
    is_default:       Mapped[bool]         = mapped_column(Boolean, default=False, nullable=False)
    visible_columns:  Mapped[list]         = mapped_column(JSONB, default=list, nullable=False)
    filters:          Mapped[dict]         = mapped_column(JSONB, default=dict, nullable=False)
    sort_by:          Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sort_dir:         Mapped[str]          = mapped_column(String(8), default="desc", nullable=False)


class CompanyLibraryTab(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "company_library_tabs"

    code:        Mapped[str]            = mapped_column(String(128), unique=True, index=True, nullable=False)
    name_ru:     Mapped[str]            = mapped_column(String(255), nullable=False)
    name_uz:     Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    name_en:     Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    field_codes: Mapped[list]           = mapped_column(JSONB, default=list, nullable=False)
    layout:      Mapped[str]            = mapped_column(String(32), default="two_col", nullable=False)
    is_system:   Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
    sort_order:  Mapped[int]            = mapped_column(Integer, default=100, nullable=False)
    scope_type:  Mapped[str]            = mapped_column(String(32), default="all", nullable=False)
    scope_value: Mapped[Optional[Any]]  = mapped_column(JSONB, nullable=True)
    created_by:  Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
