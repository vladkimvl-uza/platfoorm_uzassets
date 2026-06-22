"""Executive Overview (министерский обзор) — иерархия сектор→компания→проект.

Один лёгкий агрегат для министра: по каждому сектору его компании и их ТЕКУЩИЕ
проекты с дедлайнами, направлением и кратким описанием. Без тяжёлых метрик.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

DeadlineState = Literal["overdue", "month", "quarter", "later", "none"]


class ExecOverviewProject(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    direction: Optional[str] = None
    direction_id: Optional[UUID] = None
    status: str
    progress_percent: int = 0
    due_date: Optional[date] = None
    deadline_state: str = "none"
    # «Ход проекта» — последний нарративный апдейт (status_update)
    last_update: Optional[str] = None
    last_update_at: Optional[date] = None
    last_update_health: Optional[str] = None
    last_update_author: Optional[str] = None


class ExecOverviewDirection(BaseModel):
    """Каталог стратегических направлений платформы (для дорожной карты)."""
    id: UUID
    code: str
    name: str


class ExecOverviewTask(BaseModel):
    """Задача проекта (для разворота по клику)."""
    id: UUID
    title: str
    status: str
    assignee_name: Optional[str] = None
    progress_percent: int = 0
    due_date: Optional[date] = None
    deadline_state: str = "none"


class ExecOverviewCompany(BaseModel):
    id: UUID
    code: str
    name: str
    total: int = 0
    overdue: int = 0
    # Финпоказатели (последний доступный год; абс. UZS) — оставлены для совместимости
    revenue: Optional[float] = None
    profit: Optional[float] = None
    fin_year: Optional[int] = None
    # Ключевые результаты бизнес-плана за Q1 (план/факт, абс. UZS) — gated bp.view
    q1_revenue_plan: Optional[float] = None
    q1_revenue_fact: Optional[float] = None
    q1_profit_plan: Optional[float] = None
    q1_profit_fact: Optional[float] = None
    projects: list[ExecOverviewProject] = Field(default_factory=list)


class ExecOverviewSector(BaseModel):
    id: Optional[UUID] = None
    code: Optional[str] = None
    name: str
    color: Optional[str] = None
    short_badge: Optional[str] = None
    total: int = 0
    overdue: int = 0
    company_count: int = 0
    companies: list[ExecOverviewCompany] = Field(default_factory=list)


class ExecOverviewResponse(BaseModel):
    year: Optional[int] = None
    as_of: date
    total: int = 0
    overdue: int = 0
    due_this_month: int = 0
    sector_count: int = 0
    company_count: int = 0
    sectors: list[ExecOverviewSector] = Field(default_factory=list)
    directions: list[ExecOverviewDirection] = Field(default_factory=list)
