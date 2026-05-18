"""Pydantic schemas for moderation (Pack 11.1)."""
from datetime import datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


SubmissionStatus = Literal["pending", "under_review", "approved", "rejected", "withdrawn", "expired"]
ApprovalMode = Literal["any", "dual", "sequential"]
ModAction = Literal["edit", "replace", "comment", "upload", "delete", "status_change"]


# ─── Submission ──────────────────────────────────────────────

class SubmissionCreate(BaseModel):
    """Used by external/internal-restricted users to propose a change."""
    target_module:       str
    target_entity_id:    Optional[str] = None
    target_entity_label: Optional[str] = None
    target_field:        Optional[str] = None
    target_company_id:   Optional[UUID] = None
    target_sector_id:    Optional[UUID] = None
    action:              ModAction = "edit"
    proposed_value:      Optional[dict[str, Any]] = None
    original_value:      Optional[dict[str, Any]] = None
    diff_summary:        Optional[str] = None
    attachments:         Optional[List[dict[str, Any]]] = None
    reason:              Optional[str] = None


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime
    proposer_user_id: UUID
    proposer_is_external: bool
    target_module: str
    target_entity_id: Optional[str] = None
    target_entity_label: Optional[str] = None
    target_field: Optional[str] = None
    target_company_id: Optional[UUID] = None
    target_sector_id: Optional[UUID] = None
    action: str
    proposed_value: Optional[dict[str, Any]] = None
    original_value: Optional[dict[str, Any]] = None
    diff_summary: Optional[str] = None
    attachments: Optional[list[dict[str, Any]]] = None
    reason: Optional[str] = None
    status: SubmissionStatus
    rule_id: Optional[UUID] = None
    assigned_moderator_id: Optional[UUID] = None
    coapprover_id: Optional[UUID] = None
    reviewer_ids: Optional[list[UUID]] = None
    approval_mode: ApprovalMode
    approvals_given: list[dict[str, Any]]
    resolved_at: Optional[datetime] = None
    resolved_by_id: Optional[UUID] = None
    resolution_note: Optional[str] = None
    auto_resolved: bool
    expires_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    # Pack 148-followup B1: outcome of the apply-dispatcher on approve.
    apply_status: Optional[str] = None       # pending | applied | failed | skipped
    apply_error:  Optional[str] = None
    apply_result: Optional[dict[str, Any]] = None


class SubmissionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    proposer_user_id: UUID
    proposer_is_external: bool
    target_module: str
    target_entity_label: Optional[str] = None
    target_field: Optional[str] = None
    action: str
    status: SubmissionStatus
    assigned_moderator_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None
    diff_summary: Optional[str] = None


class SubmissionListResponse(BaseModel):
    items: List[SubmissionListItem]
    total: int
    counts_by_status: dict[str, int]
    page: int
    per_page: int


class SubmissionResolve(BaseModel):
    """Body for approve/reject/set-review endpoints."""
    note: Optional[str] = None


class SubmissionEditAndApprove(BaseModel):
    proposed_value: dict[str, Any]
    note: Optional[str] = None


# ─── Comment ─────────────────────────────────────────────────

class CommentCreate(BaseModel):
    text: str
    attachments: Optional[List[dict[str, Any]]] = None
    is_internal: bool = False


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    submission_id: UUID
    user_id: Optional[UUID] = None
    text: str
    attachments: Optional[list[dict[str, Any]]] = None
    is_internal: bool


# ─── Rule ────────────────────────────────────────────────────

class RuleConditionAtom(BaseModel):
    field: str
    op: Literal["=", "!=", ">", ">=", "<", "<=", "in", "not_in", "abs>", "delta>"]
    value: Any
    unit: Optional[str] = None  # e.g. 'USD', '%', 'tn'


class RuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: bool = True
    sort_order: int = 100

    # WHO
    trigger_user_ids: Optional[List[UUID]] = None
    trigger_group_codes: Optional[List[str]] = None
    trigger_role_codes: Optional[List[str]] = None
    trigger_is_external: bool = False
    # WHAT
    trigger_modules: Optional[List[str]] = None
    # WHERE
    trigger_company_ids: Optional[List[UUID]] = None
    trigger_sector_ids: Optional[List[UUID]] = None
    trigger_year_from: Optional[int] = None
    trigger_year_to: Optional[int] = None
    # ACTION
    trigger_actions: Optional[List[ModAction]] = None
    # THRESHOLDS
    trigger_conditions: Optional[List[RuleConditionAtom]] = None

    # Chain
    moderator_primary_id: Optional[UUID] = None
    moderator_coapprover_id: Optional[UUID] = None
    moderator_fallback_group_code: Optional[str] = None
    approval_mode: ApprovalMode = "any"

    # Auto-actions
    escalate_after_hours: Optional[int] = None
    auto_approve_after_hours: Optional[int] = None
    expire_after_days: int = 30

    # Notifications
    notify_proposer_assigned: bool = True
    notify_proposer_resolved: bool = True
    notify_coapprovers_cc: bool = True
    notify_owner_on_reject: bool = False
    log_to_audit: bool = True


class RuleCreate(RuleBase):
    pass


class RuleUpdate(RuleBase):
    pass


class RuleRead(RuleBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None
    version: int
    last_matched_at: Optional[datetime] = None
    total_matches: int
    total_approvals: int
    total_rejections: int


class RuleListResponse(BaseModel):
    items: List[RuleRead]
    total: int


# ─── Stats / overview ────────────────────────────────────────

class ModerationOverview(BaseModel):
    pending: int
    under_review: int
    resolved_today: int
    approved_today: int
    rejected_today: int
    avg_resolution_hours: Optional[float] = None
    my_pending_count: int = 0       # for moderators: assigned to me

    moderators_count: int
    external_users_count: int
    rules_active_count: int
    rules_total_count: int


# ─── Module catalog (helper for rule editor UI) ──────────────

class ModuleInfo(BaseModel):
    code: str
    label: str
    icon: str


class ActionInfo(BaseModel):
    code: str
    label: str


class CatalogResponse(BaseModel):
    modules: List[ModuleInfo]
    actions: List[ActionInfo]
