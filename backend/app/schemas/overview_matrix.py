"""Overview matrix config schemas — настройка квартальной матрицы Сводного обзора."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MatrixOverride(BaseModel):
    """Переопределение отображения реального проекта (всё опционально)."""
    title: Optional[str] = Field(None, max_length=512)
    due_date: Optional[str] = None      # ISO-дата 'YYYY-MM-DD' или null
    quarter: Optional[int] = Field(None, ge=0, le=3)  # 0..3 или null = по дате
    hidden: Optional[bool] = None        # на случай хранения скрытия в overrides


class MatrixCustomItem(BaseModel):
    """Произвольный пункт (которого нет в системе)."""
    id: str
    direction_id: Optional[str] = None
    direction_name: Optional[str] = Field(None, max_length=255)
    title: str = Field(..., max_length=512)
    due_date: Optional[str] = None
    quarter: Optional[int] = Field(None, ge=0, le=3)


class MatrixConfig(BaseModel):
    """Полный конфиг матрицы для (company, year)."""
    model_config = ConfigDict(extra="ignore")

    hidden: list[str] = Field(default_factory=list)            # скрытые project_id
    overrides: dict[str, MatrixOverride] = Field(default_factory=dict)
    custom: list[MatrixCustomItem] = Field(default_factory=list)


class MatrixConfigResponse(BaseModel):
    company_id: UUID
    year: int
    config: MatrixConfig
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None
