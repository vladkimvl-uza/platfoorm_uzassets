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
    quarter: Optional[int] = Field(None, ge=0, le=3)      # старт-квартал; null = по дате
    quarter_end: Optional[int] = Field(None, ge=0, le=3)  # конец-квартал (Гант-растяжка); null = один квартал
    hidden: Optional[bool] = None        # на случай хранения скрытия в overrides


class MatrixCustomItem(BaseModel):
    """Произвольный пункт (которого нет в системе)."""
    id: str
    direction_id: Optional[str] = None
    direction_name: Optional[str] = Field(None, max_length=255)
    title: str = Field(..., max_length=512)
    due_date: Optional[str] = None
    quarter: Optional[int] = Field(None, ge=0, le=3)
    quarter_end: Optional[int] = Field(None, ge=0, le=3)


class MatrixManualProject(BaseModel):
    """Проект ручного отчёта: название (вписывают), квартал(ы), дата, детали для выноски."""
    id: str
    title: str = Field("", max_length=512)
    ref_project_id: Optional[str] = None                  # связанный системный проект (автоподстановка)
    quarter: Optional[int] = Field(None, ge=0, le=3)      # старт-квартал
    quarter_end: Optional[int] = Field(None, ge=0, le=3)  # конец-квартал (Гант-растяжка)
    due_date: Optional[str] = None
    details: Optional[str] = Field(None, max_length=4000)  # текст выноски (внизу отчёта)


class MatrixManualDirection(BaseModel):
    """Направление ручного отчёта (строка матрицы) — название вписывают вручную."""
    id: str
    name: str = Field("", max_length=255)
    projects: list[MatrixManualProject] = Field(default_factory=list)


class MatrixConfig(BaseModel):
    """Полный конфиг матрицы для (company, year)."""
    model_config = ConfigDict(extra="ignore")

    hidden: list[str] = Field(default_factory=list)            # скрытые project_id
    overrides: dict[str, MatrixOverride] = Field(default_factory=dict)
    custom: list[MatrixCustomItem] = Field(default_factory=list)
    # Ручной отчёт (новый режим): направления и проекты вписываются вручную,
    # детали проектов выносятся в сноску внизу отчёта. Если непусто — отчёт
    # рендерится из этого, а не из системных проектов.
    manual_directions: list[MatrixManualDirection] = Field(default_factory=list)


class MatrixConfigResponse(BaseModel):
    company_id: UUID
    year: int
    config: MatrixConfig
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None
