"""Метамодель ERP (Фаза 0) — «схема как данные».

mm_entities  — типы объектов (блюпринты): «Карьерная техника», «Скважина»…
mm_fields    — поля сущности (14 типов; в Фазе 0 поддержаны основные)
mm_records   — экземпляры (данные в JSONB, scoped по company_id)

Кросс-cutting (аудит/модерация/RBAC/AI/уведомления) подключается на уровне
роутера — переиспользует уже готовую машинерию платформы. FK между записями
и определениями НЕ используем (ссылка по entity_code) — меньше хрупкости при
эволюции схемы.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID as PyUUID

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# Типы полей (Фаза 0). Остальные (geo/file/formula/richtext/multiselect) —
# следующие фазы; рендерер и валидатор расширяемы по этому списку.
FIELD_TYPES = ("text", "textarea", "number", "money", "date", "datetime",
               "select", "bool", "ref", "user")


class MMEntity(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "mm_entities"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    name_plural: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    module: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)   # EAM, Production…
    pack: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)     # отраслевой пак
    is_company_scoped: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    title_field: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # какое поле = заголовок записи
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MMField(Base, UUIDMixin):
    __tablename__ = "mm_fields"

    entity_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(String(24), nullable=False, default="text")
    grp: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)       # секция формы
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unique_scoped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    options: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)        # [{value,label,color}]
    ref_entity_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    validation: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)     # {min,max,regex}
    default_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # {v: ...}
    help: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    show_in_list: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MMRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "mm_records"

    entity_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    company_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), index=True, nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    state: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    created_by: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
