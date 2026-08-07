"""Moderation models (Pack 11.1)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ───── Submission ─────────────────────────────────────────────

class ModerationSubmission(Base):
    """A pending change proposed by a (usually external) user."""

    __tablename__ = "moderation_submission"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    proposer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    proposer_is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    target_module:        Mapped[str]            = mapped_column(String(64),  nullable=False)
    target_entity_id:     Mapped[Optional[str]]  = mapped_column(String(128), nullable=True)
    target_entity_label:  Mapped[Optional[str]]  = mapped_column(String(255), nullable=True)
    target_field:         Mapped[Optional[str]]  = mapped_column(String(128), nullable=True)
    target_company_id:    Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True,
    )
    target_sector_id:     Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sectors.id", ondelete="SET NULL"), nullable=True,
    )

    action:          Mapped[str]             = mapped_column(String(32), nullable=False, default="edit")
    proposed_value:  Mapped[Optional[dict]]  = mapped_column(JSONB, nullable=True)
    original_value:  Mapped[Optional[dict]]  = mapped_column(JSONB, nullable=True)
    diff_summary:    Mapped[Optional[str]]   = mapped_column(Text, nullable=True)
    attachments:     Mapped[Optional[list]]  = mapped_column(JSONB, nullable=True)
    reason:          Mapped[Optional[str]]   = mapped_column(Text, nullable=True)

    status:          Mapped[str]             = mapped_column(String(24), nullable=False, default="pending")

    rule_id:                Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    assigned_moderator_id:  Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    coapprover_id:          Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    reviewer_ids:           Mapped[Optional[list]]   = mapped_column(JSONB, nullable=True)
    approval_mode:          Mapped[str]              = mapped_column(String(16), nullable=False, default="any")
    approvals_given:        Mapped[list]             = mapped_column(JSONB, nullable=False, default=list)

    resolved_at:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_id:   Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    resolution_note:  Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auto_resolved:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    expires_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    source_ip:         Mapped[Optional[str]] = mapped_column(String(45),  nullable=True)
    source_user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # followup B1: apply-dispatcher tracking. When approve() runs,
    # the registered handler for `target_module` writes the change to the
    # actual entity. Outcome is recorded here for UI surfacing + retry.
    #   apply_status: pending | applied | failed | skipped
    apply_status: Mapped[Optional[str]]    = mapped_column(String(16),  nullable=True)
    apply_error:  Mapped[Optional[str]]    = mapped_column(String(500), nullable=True)
    apply_result: Mapped[Optional[dict]]   = mapped_column(JSONB,       nullable=True)

    # Оптимистичный editor-token целевого scope (company, year), снятый в момент
    # ПОДАЧИ. Apply сверяет его с актуальным токеном ПЕРЕД delete-and-replace: если
    # данные раздела изменились после подачи, одобрение НЕ затирает их молча, а
    # падает с понятной ошибкой. NULL → проверки нет (legacy/не captured).
    editor_token: Mapped[Optional[str]]    = mapped_column(String(64),  nullable=True)


# ───── Comment ────────────────────────────────────────────────

class ModerationComment(Base):
    """A comment in the submission's discussion thread."""

    __tablename__ = "moderation_comment"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("moderation_submission.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    text:        Mapped[str]            = mapped_column(Text, nullable=False)
    attachments: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    is_internal: Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)


# ───── Rule ───────────────────────────────────────────────────

class ModerationRule(Base):
    """Flexible matcher: who/what/where/action/threshold → moderator chain + auto actions."""

    __tablename__ = "moderation_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    name:        Mapped[str]            = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    icon:        Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    is_active:   Mapped[bool]           = mapped_column(Boolean, nullable=False, default=True)
    sort_order:  Mapped[int]            = mapped_column(Integer, nullable=False, default=100)
    version:     Mapped[int]            = mapped_column(Integer, nullable=False, default=1)

    # WHO
    trigger_user_ids:     Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    trigger_group_codes:  Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    trigger_role_codes:   Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    trigger_is_external:  Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)

    # WHAT
    trigger_modules:      Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # WHERE
    trigger_company_ids:  Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    trigger_sector_ids:   Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    trigger_year_from:    Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    trigger_year_to:      Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)

    # ACTION
    trigger_actions:      Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # THRESHOLDS
    trigger_conditions:   Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Chain
    moderator_primary_id:      Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    moderator_coapprover_id:   Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    moderator_fallback_group_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approval_mode:             Mapped[str] = mapped_column(String(16), nullable=False, default="any")

    # Auto-actions
    escalate_after_hours:      Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_approve_after_hours:  Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expire_after_days:         Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # Notifications
    notify_proposer_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_proposer_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_coapprovers_cc:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_owner_on_reject:   Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    log_to_audit:             Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Stats
    last_matched_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_matches:     Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_approvals:   Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_rejections:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ───── Module catalog (for rule editor UI) ────────────────────

MODERATABLE_MODULES = [
    {"code": "kpi",           "label": "KPI",                 "icon": "chart-line"},
    {"code": "financials",    "label": "Финансы (P&L/SOFP)",  "icon": "cash"},
    {"code": "business_plan", "label": "Бизнес-план",          "icon": "chart-pie"},
    {"code": "esg",           "label": "ESG",                  "icon": "leaf"},
    {"code": "governance",    "label": "Корп. управление",     "icon": "building-bank"},
    {"code": "procurement",   "label": "Закупки",              "icon": "shopping-cart"},
    {"code": "ratings",       "label": "Рейтинги",             "icon": "award"},
    {"code": "tasks",         "label": "Задачи",               "icon": "checklist"},
    {"code": "comments",      "label": "Комментарии",          "icon": "message-circle"},
    # NB: "uploads" НЕ проходит через gate_or_apply (вложения пишутся напрямую) —
    # правило на них молча ничего бы не делало, поэтому в каталог не включён.
]

MODERATABLE_ACTIONS = [
    {"code": "create",        "label": "Создать"},
    {"code": "edit",          "label": "Изменить значение"},
    {"code": "replace",       "label": "Заменить целиком"},
    {"code": "comment",       "label": "Добавить комментарий"},
    {"code": "upload",        "label": "Загрузить файл"},
    {"code": "delete",        "label": "Удалить"},
    {"code": "status_change", "label": "Изменить статус"},
]
