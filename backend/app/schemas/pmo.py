"""PMO schemas — P1: расписание / Гантт / зависимости.

Schedule = плоский список баров (проекты + их задачи) с базовым планом,
слипом, флагом критического пути и списком предшественников. Фронт рендерит
таймлайн из этого DTO; критический путь и слип считаются на бэкенде.
"""
from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ScheduleBar(BaseModel):
    """Один бар на таймлайне — проект или задача."""
    id: UUID
    kind: Literal["project", "task"]
    project_id: Optional[UUID] = None     # для задач — родитель (группировка строк)
    title: str
    status: str
    progress_percent: int = 0

    start: Optional[date] = None
    due: Optional[date] = None
    baseline_start: Optional[date] = None
    baseline_due: Optional[date] = None

    is_milestone: bool = False
    assignee_name: Optional[str] = None
    direction: Optional[str] = None

    # Расчётные (бэкенд):
    slip_days: int = 0                    # due − baseline_due (>0 = опоздание)
    on_critical_path: bool = False
    predecessor_ids: list[UUID] = Field(default_factory=list)
    blocked: bool = False                 # есть незавершённый предшественник


class ScheduleResponse(BaseModel):
    company_code: str
    year: Optional[int] = None
    as_of: date
    bars: list[ScheduleBar] = Field(default_factory=list)
    # Сводка портфеля:
    portfolio_slip_days: int = 0          # макс. слип по критическому пути
    forecast_finish: Optional[date] = None
    baseline_finish: Optional[date] = None
    critical_path_ids: list[UUID] = Field(default_factory=list)
    overdue_count: int = 0
    blocked_count: int = 0


# ─── Dependencies ──────────────────────────────────────────────────────

DepType = Literal["FS", "SS", "FF", "SF"]


class DependencyCreate(BaseModel):
    predecessor_id: UUID
    successor_id: UUID
    dep_type: DepType = "FS"
    lag_days: int = 0


class DependencyRead(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    predecessor_id: UUID
    successor_id: UUID
    dep_type: str
    lag_days: int
