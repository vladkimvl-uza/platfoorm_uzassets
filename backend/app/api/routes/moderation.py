"""Moderation API — thin HTTP layer (refactored 2026-05-25).

State transitions (approve/reject/edit-and-approve/withdraw/retry-apply/etc)
continue to delegate to the existing core `app/services/moderation_service.py`
(aliased as `svc` here) — that module is the gate-or-apply engine used by
all other route files, do not break its contract.

UI dashboard queries + rules CRUD + user flags live in the new
`moderation_admin/` services (with backing ModerationRepository).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.dependencies.moderation import (
    ModerationQueryServiceDep, ModerationRulesServiceDep,
)
from app.models.moderation import (
    MODERATABLE_ACTIONS, MODERATABLE_MODULES, ModerationSubmission,
)
from app.models.user import User
from app.schemas.moderation import (
    ActionInfo, CatalogResponse,
    CommentCreate, CommentRead,
    ModerationOverview, ModuleInfo,
    RuleCreate, RuleListResponse, RuleRead, RuleUpdate,
    SubmissionCreate, SubmissionEditAndApprove,
    SubmissionListResponse, SubmissionRead, SubmissionResolve,
)
from app.services import moderation_service as svc


router = APIRouter(prefix="/moderation", tags=["moderation"])


# ─── Overview / Catalog ───────────────────────────────────────────

@router.get("/overview", response_model=ModerationOverview)
async def overview(
    service: ModerationQueryServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.overview(user_id=user.id)


@router.get("/catalog", response_model=CatalogResponse)
async def catalog(_u: User = Depends(get_current_user)):
    return CatalogResponse(
        modules=[ModuleInfo(**m) for m in MODERATABLE_MODULES],
        actions=[ActionInfo(**a) for a in MODERATABLE_ACTIONS],
    )


# ─── Submissions queue ────────────────────────────────────────────

@router.get("/queue", response_model=SubmissionListResponse)
async def queue(
    service: ModerationQueryServiceDep,
    status: Optional[list[str]] = Query(None),
    assigned_to: Optional[str] = Query(None),  # "me" | user_id
    module: Optional[str] = Query(None),
    proposer_user_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    return await service.list_queue(
        status_in=status, assigned_to=assigned_to,
        module=module, proposer_user_id=proposer_user_id,
        page=page, per_page=per_page, actor_id=user.id,
    )


@router.get("/my-submissions", response_model=SubmissionListResponse)
async def my_submissions(
    service: ModerationQueryServiceDep,
    status: Optional[list[str]] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    return await service.list_my_submissions(
        actor_id=user.id, status_in=status,
        page=page, per_page=per_page,
    )


@router.post("/submissions", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def create_submission(
    body: SubmissionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.submit")),
):
    sub = await svc.create_submission(
        db,
        proposer=user,
        target_module=body.target_module,
        target_entity_id=body.target_entity_id,
        target_entity_label=body.target_entity_label,
        target_field=body.target_field,
        target_company_id=body.target_company_id,
        target_sector_id=body.target_sector_id,
        action=body.action,
        proposed_value=body.proposed_value,
        original_value=body.original_value,
        diff_summary=body.diff_summary,
        attachments=body.attachments,
        reason=body.reason,
        source_ip=request.client.host if request.client else None,
        source_user_agent=request.headers.get("user-agent"),
    )
    return SubmissionRead.model_validate(sub)


@router.get("/submissions/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    allowed = (
        user.is_owner
        or sub.proposer_user_id == user.id
        or sub.assigned_moderator_id == user.id
        or sub.coapprover_id == user.id
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access")
    return SubmissionRead.model_validate(sub)


# ─── Submission state transitions ─────────────────────────────────

async def _load_sub(db: AsyncSession, submission_id: UUID):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub:
        raise HTTPException(404, "Not found")
    return sub


def _wrap_state_change(coro):
    """Run a coro and convert PermissionError → 403, ValueError → 409."""
    async def runner():
        try:
            return await coro
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return runner()


@router.post("/submissions/{submission_id}/approve", response_model=SubmissionRead)
async def approve_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.approve(db, sub=sub, user=user, note=body.note))
    return SubmissionRead.model_validate(result)


@router.post("/submissions/{submission_id}/reject", response_model=SubmissionRead)
async def reject_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.reject(db, sub=sub, user=user, note=body.note))
    return SubmissionRead.model_validate(result)


@router.post("/submissions/{submission_id}/set-review", response_model=SubmissionRead)
async def set_review_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.set_review(db, sub=sub, user=user, note=body.note))
    return SubmissionRead.model_validate(result)


@router.post("/submissions/{submission_id}/edit-and-approve", response_model=SubmissionRead)
async def edit_and_approve_submission(
    submission_id: UUID,
    body: SubmissionEditAndApprove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.edit_and_approve(
        db, sub=sub, user=user, proposed_value=body.proposed_value, note=body.note,
    ))
    return SubmissionRead.model_validate(result)


@router.post("/submissions/{submission_id}/retry-apply", response_model=SubmissionRead)
async def retry_apply_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    if sub.status != "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only approved submissions can be re-applied (current: {sub.status})",
        )
    await svc._dispatch_apply(db, sub, user)
    await db.refresh(sub)
    return SubmissionRead.model_validate(sub)


@router.post("/submissions/{submission_id}/withdraw", response_model=SubmissionRead)
async def withdraw_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.withdraw(db, sub=sub, user=user))
    return SubmissionRead.model_validate(result)


# ─── Comments ─────────────────────────────────────────────────────

@router.get("/submissions/{submission_id}/comments", response_model=list[CommentRead])
async def list_comments(
    submission_id: UUID,
    service: ModerationRulesServiceDep,
    user: User = Depends(get_current_user),
):
    sub = await service.get_submission_for_access(submission_id)
    if not sub:
        raise HTTPException(404, "Not found")
    is_moderator = (
        user.is_owner
        or sub.assigned_moderator_id == user.id
        or sub.coapprover_id == user.id
    )
    is_proposer = sub.proposer_user_id == user.id
    if not (is_moderator or is_proposer):
        raise HTTPException(403, "No access")
    return await service.list_comments(submission_id, include_internal=is_moderator)


@router.post("/submissions/{submission_id}/comments", response_model=CommentRead,
             status_code=status.HTTP_201_CREATED)
async def add_comment(
    submission_id: UUID,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await _load_sub(db, submission_id)
    is_moderator = (
        user.is_owner
        or sub.assigned_moderator_id == user.id
        or sub.coapprover_id == user.id
    )
    is_proposer = sub.proposer_user_id == user.id
    if not (is_moderator or is_proposer):
        raise HTTPException(403, "No access")
    if body.is_internal and not is_moderator:
        raise HTTPException(403, "Only moderators can post internal comments")

    c = await svc.add_comment(
        db, sub=sub, user=user, text=body.text,
        attachments=body.attachments, is_internal=body.is_internal,
    )
    return CommentRead.model_validate(c)


# ─── Rules CRUD ───────────────────────────────────────────────────

@router.get("/rules", response_model=RuleListResponse)
async def list_rules(
    service: ModerationRulesServiceDep,
    _u: User = Depends(require_permission("moderation.admin")),
):
    return await service.list_rules()


@router.get("/rules/{rule_id}", response_model=RuleRead)
async def get_rule(
    rule_id: UUID,
    service: ModerationRulesServiceDep,
    _u: User = Depends(require_permission("moderation.admin")),
):
    return await service.get_rule(rule_id)


@router.post("/rules", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    service: ModerationRulesServiceDep,
    user: User = Depends(require_permission("moderation.admin")),
):
    return await service.create_rule(body, created_by_id=user.id)


@router.patch("/rules/{rule_id}", response_model=RuleRead)
async def update_rule(
    rule_id: UUID,
    body: RuleUpdate,
    service: ModerationRulesServiceDep,
    _u: User = Depends(require_permission("moderation.admin")),
):
    return await service.update_rule(rule_id, body)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    service: ModerationRulesServiceDep,
    _u: User = Depends(require_permission("moderation.admin")),
):
    await service.delete_rule(rule_id)


@router.post("/rules/{rule_id}/toggle", response_model=RuleRead)
async def toggle_rule(
    rule_id: UUID,
    service: ModerationRulesServiceDep,
    _u: User = Depends(require_permission("moderation.admin")),
):
    return await service.toggle_rule(rule_id)


# ─── Moderators / External users sub-tabs ─────────────────────────

@router.get("/moderators")
async def list_moderators(
    service: ModerationQueryServiceDep,
    _u: User = Depends(get_current_user),
):
    return {"items": await service.list_moderators()}


@router.get("/submitted-users")
async def list_submitted_users(
    service: ModerationQueryServiceDep,
    _u: User = Depends(get_current_user),
):
    return {"items": await service.list_external_users()}


@router.patch("/users/{user_id}/flags")
async def patch_user_flags(
    user_id: UUID,
    body: dict,
    service: ModerationRulesServiceDep,
    _u: User = Depends(require_permission("admin.users")),
):
    return await service.patch_user_flags(user_id, body)
