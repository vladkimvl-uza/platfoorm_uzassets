"""PMO P2 models — RAID-реестр и статус-отчёты.

RaidItem — реестр рисков/допущений/проблем/зависимостей (R/A/I/D).
StatusReport — снимок здоровья портфеля/проекта (RAG + метрики + резюме).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class RaidItem(Base, UUIDMixin, TimestampMixin):
    """RAID — Risk / Assumption / Issue / Dependency."""

    __tablename__ = "raid_items"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # risk | assumption | issue | dependency
    kind: Mapped[str] = mapped_column(String(16), default="risk", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    owner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    owner_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False, index=True)
    probability: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1..5
    impact: Mapped[int] = mapped_column(Integer, default=3, nullable=False)        # 1..5
    score: Mapped[int] = mapped_column(Integer, default=9, nullable=False, index=True)  # prob*impact

    # threat | opportunity (PMBOK 7 — угрозы И возможности)
    polarity: Mapped[str] = mapped_column(String(12), default="threat", nullable=False, index=True)
    # Стратегия реагирования: threat → avoid/transfer/mitigate/accept/escalate;
    # opportunity → exploit/share/enhance/accept/escalate.
    response_strategy: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # open | mitigating | closed
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    mitigation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PmoStakeholder(Base, UUIDMixin, TimestampMixin):
    """Реестр заинтересованных сторон (PMBOK 7 — Stakeholders).

    power/interest (1..5) → сетка вовлечения (manage closely / keep satisfied /
    keep informed / monitor). engagement_current/desired по шкале
    unaware → resistant → neutral → supportive → leading (gap → план действий)."""

    __tablename__ = "pmo_stakeholders"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    power: Mapped[int] = mapped_column(Integer, default=3, nullable=False)     # 1..5
    interest: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1..5
    # unaware | resistant | neutral | supportive | leading
    engagement_current: Mapped[str] = mapped_column(String(16), default="neutral", nullable=False)
    engagement_desired: Mapped[str] = mapped_column(String(16), default="supportive", nullable=False)

    strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PmoLesson(Base, UUIDMixin, TimestampMixin):
    """Извлечённый урок (PMBOK 7 — Project Work / управление знаниями)."""

    __tablename__ = "pmo_lessons"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # success (что сработало) | problem (что пошло не так) | recommendation
    kind: Mapped[str] = mapped_column(String(16), default="recommendation", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Ответственный/упомянутый пользователь (mention). Имя денормализовано.
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    owner_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PmoChange(Base, UUIDMixin, TimestampMixin):
    """Запрос на изменение (PMBOK 7 — контроль изменений / change control)."""

    __tablename__ = "pmo_changes"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # scope | schedule | cost | quality | other
    kind: Mapped[str] = mapped_column(String(16), default="scope", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # proposed | approved | rejected | implemented
    status: Mapped[str] = mapped_column(String(16), default="proposed", nullable=False, index=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PmoCharter(Base, UUIDMixin, TimestampMixin):
    """Устав проекта (PMBOK 7 — формальная инициация / authorization).

    Один устав на проект (project_id) либо на программу/портфель (project_id
    NULL). Фиксирует обоснование, цели, границы (in/out), критерии успеха,
    ключевые результаты и вехи, допущения/ограничения, спонсора и РП, бюджет
    и сроки. Утверждение (status=approved) штампует approver + дату."""

    __tablename__ = "pmo_charters"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Кэш названия проекта/программы — отображение без JOIN.
    project_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)          # обоснование/назначение
    objectives: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # цели
    scope_in: Mapped[Optional[str]] = mapped_column(Text, nullable=True)         # в границах
    scope_out: Mapped[Optional[str]] = mapped_column(Text, nullable=True)        # вне границ
    success_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deliverables: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # ключевые результаты
    milestones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # вехи
    assumptions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # допущения
    constraints: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # ограничения

    sponsor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    manager_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    budget_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    target_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # draft | approved
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PmoSprint(Base, UUIDMixin, TimestampMixin):
    """Спринт (PMBOK 7 / Scrum) — таймбокс, группирующий существующие задачи.

    Сами рабочие элементы — это обычные Task (tasks.sprint_id → этот спринт),
    что переиспользует исполнителей/комментарии/вложения/прогресс и автоматом
    связывает Agile с Ганттом/EVM/загрузкой. status: planned|active|done."""

    __tablename__ = "pmo_sprints"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # planned | active | done
    status: Mapped[str] = mapped_column(String(16), default="planned", nullable=False, index=True)
    capacity_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PmoRaci(Base, UUIDMixin, TimestampMixin):
    """Назначение ответственности RACI (PMBOK 7 — Team / распределение ролей).

    Одна запись = ячейка матрицы: для активности/результата (item_label) у
    человека (person) роль R/A/C/I. Матрица собирается на фронте пивотом по
    item_label × person. role: R=исполнитель, A=ответственный, C=консультант,
    I=информируемый."""

    __tablename__ = "pmo_raci"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_label: Mapped[str] = mapped_column(String(512), nullable=False)
    person_name: Mapped[str] = mapped_column(String(255), nullable=False)
    person_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # R | A | C | I
    role: Mapped[str] = mapped_column(String(1), nullable=False, default="R")
    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class StatusReport(Base, UUIDMixin, TimestampMixin):
    """Снимок статуса портфеля/проекта (RAG + метрики + резюме)."""

    __tablename__ = "status_reports"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    period: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    # green | amber | red
    rag: Mapped[str] = mapped_column(String(8), default="green", nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
