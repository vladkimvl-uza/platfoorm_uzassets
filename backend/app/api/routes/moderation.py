"""Moderation REST routes (Pack 11.1).

All endpoints under /moderation/*.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.moderation import (
    MODERATABLE_ACTIONS, MODERATABLE_MODULES,
    ModerationComment, ModerationRule, ModerationSubmission,
)
from app.models.user import User
from app.schemas.moderation import (
    ActionInfo,
    CatalogResponse,
    CommentCreate, CommentRead,
    ModerationOverview, ModuleInfo,
    RuleCreate, RuleListResponse, RuleRead, RuleUpdate,
    SubmissionCreate, SubmissionEditAndApprove,
    SubmissionListItem, SubmissionListResponse, SubmissionRead, SubmissionResolve,
)
from app.services import moderation_service as svc


router = APIRouter(prefix="/moderation", tags=["moderation"])


# ════════════════════════════════════════════════════════════
#   Overview
# ════════════════════════════════════════════════════════════

@router.get("/overview", response_model=ModerationOverview)
async def overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    pending     = (await db.execute(select(func.count(ModerationSubmission.id)).where(ModerationSubmission.status == "pending"))).scalar() or 0
    in_review   = (await db.execute(select(func.count(ModerationSubmission.id)).where(ModerationSubmission.status == "under_review"))).scalar() or 0

    resolved_today = (await db.execute(
        select(func.count(ModerationSubmission.id))
        .where(and_(ModerationSubmission.resolved_at >= today,
                    ModerationSubmission.status.in_(["approved", "rejected"]))),
    )).scalar() or 0
    approved_today = (await db.execute(
        select(func.count(ModerationSubmission.id))
        .where(and_(ModerationSubmission.resolved_at >= today,
                    ModerationSubmission.status == "approved")),
    )).scalar() or 0
    rejected_today = (await db.execute(
        select(func.count(ModerationSubmission.id))
        .where(and_(ModerationSubmission.resolved_at >= today,
                    ModerationSubmission.status == "rejected")),
    )).scalar() or 0

    avg_hours = (await db.execute(
        select(func.avg(
            func.extract("epoch",
                ModerationSubmission.resolved_at - ModerationSubmission.created_at) / 3600.0
        ))
        .where(and_(
            ModerationSubmission.resolved_at.is_not(None),
            ModerationSubmission.resolved_at >= today - timedelta(days=7),
        )),
    )).scalar()

    my_pending = (await db.execute(
        select(func.count(ModerationSubmission.id))
        .where(and_(
            ModerationSubmission.assigned_moderator_id == user.id,
            ModerationSubmission.status.in_(["pending", "under_review"]),
        )),
    )).scalar() or 0

    external_count = (await db.execute(
        select(func.count(User.id)).where(User.is_external.is_(True)),
    )).scalar() or 0
    rules_active = (await db.execute(
        select(func.count(ModerationRule.id)).where(ModerationRule.is_active.is_(True)),
    )).scalar() or 0
    rules_total = (await db.execute(select(func.count(ModerationRule.id)))).scalar() or 0

    # moderators = users with moderation.review permission (approx: count distinct rule.moderator_primary_id ∪ coapprover_id)
    rows = (await db.execute(
        select(ModerationRule.moderator_primary_id, ModerationRule.moderator_coapprover_id),
    )).all()
    mods = set()
    for r in rows:
        if r[0]: mods.add(str(r[0]))
        if r[1]: mods.add(str(r[1]))

    return ModerationOverview(
        pending=pending, under_review=in_review,
        resolved_today=resolved_today,
        approved_today=approved_today,
        rejected_today=rejected_today,
        avg_resolution_hours=float(avg_hours) if avg_hours is not None else None,
        my_pending_count=my_pending,
        moderators_count=len(mods),
        external_users_count=external_count,
        rules_active_count=rules_active,
        rules_total_count=rules_total,
    )


@router.get("/catalog", response_model=CatalogResponse)
async def catalog(_u: User = Depends(get_current_user)):
    return CatalogResponse(
        modules=[ModuleInfo(**m) for m in MODERATABLE_MODULES],
        actions=[ActionInfo(**a) for a in MODERATABLE_ACTIONS],
    )


# ════════════════════════════════════════════════════════════
#   Submissions — queue
# ════════════════════════════════════════════════════════════

@router.get("/queue", response_model=SubmissionListResponse)
async def queue(
    status: Optional[list[str]] = Query(None),
    assigned_to: Optional[str] = Query(None),  # "me" | user_id
    module: Optional[str] = Query(None),
    proposer_user_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base = select(ModerationSubmission)
    if status:
        base = base.where(ModerationSubmission.status.in_(status))
    if assigned_to == "me":
        base = base.where(ModerationSubmission.assigned_moderator_id == user.id)
    elif assigned_to:
        base = base.where(ModerationSubmission.assigned_moderator_id == UUID(assigned_to))
    if module:
        base = base.where(ModerationSubmission.target_module == module)
    if proposer_user_id:
        base = base.where(ModerationSubmission.proposer_user_id == proposer_user_id)

    total = (await db.execute(
        select(func.count()).select_from(base.subquery()),
    )).scalar() or 0

    # Counts by status (no filters applied, full picture)
    cnt_rows = (await db.execute(
        select(ModerationSubmission.status, func.count(ModerationSubmission.id))
        .group_by(ModerationSubmission.status),
    )).all()
    counts = {r[0]: r[1] for r in cnt_rows}

    rows = (await db.execute(
        base.order_by(ModerationSubmission.created_at.desc())
        .limit(per_page).offset((page - 1) * per_page),
    )).scalars().all()

    return SubmissionListResponse(
        items=[SubmissionListItem.model_validate(r) for r in rows],
        total=total,
        counts_by_status=counts,
        page=page, per_page=per_page,
    )


@router.get("/my-submissions", response_model=SubmissionListResponse)
async def my_submissions(
    status: Optional[list[str]] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base = select(ModerationSubmission).where(ModerationSubmission.proposer_user_id == user.id)
    if status:
        base = base.where(ModerationSubmission.status.in_(status))

    total = (await db.execute(
        select(func.count()).select_from(base.subquery()),
    )).scalar() or 0

    cnt_rows = (await db.execute(
        select(ModerationSubmission.status, func.count(ModerationSubmission.id))
        .where(ModerationSubmission.proposer_user_id == user.id)
        .group_by(ModerationSubmission.status),
    )).all()
    counts = {r[0]: r[1] for r in cnt_rows}

    rows = (await db.execute(
        base.order_by(ModerationSubmission.created_at.desc())
        .limit(per_page).offset((page - 1) * per_page),
    )).scalars().all()
    return SubmissionListResponse(
        items=[SubmissionListItem.model_validate(r) for r in rows],
        total=total, counts_by_status=counts,
        page=page, per_page=per_page,
    )


@router.post("/submissions", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def create_submission(
    body: SubmissionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.submit")),
):
    """Submit a proposed change for moderation.

    Requires `moderation.submit`. Bypass users (`user.bypass_moderation=True`)
    write directly to the underlying entity endpoint instead of here.
    """
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
    if not sub: raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    # Access control: proposer + assigned moderators + owner
    allowed = (
        user.is_owner or
        sub.proposer_user_id == user.id or
        sub.assigned_moderator_id == user.id or
        sub.coapprover_id == user.id
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access")
    return SubmissionRead.model_validate(sub)


@router.post("/submissions/{submission_id}/approve", response_model=SubmissionRead)
async def approve_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub: raise HTTPException(404, "Not found")
    try:
        result = await svc.approve(db, sub=sub, user=user, note=body.note)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return SubmissionRead.model_validate(result)


@router.post("/submissions/{submission_id}/reject", response_model=SubmissionRead)
async def reject_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub: raise HTTPException(404, "Not found")
    try:
        result = await svc.reject(db, sub=sub, user=user, note=body.note)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return SubmissionRead.model_validate(result)


@router.post("/submissions/{submission_id}/set-review", response_model=SubmissionRead)
async def set_review_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub: raise HTTPException(404, "Not found")
    try:
        result = await svc.set_review(db, sub=sub, user=user, note=body.note)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return SubmissionRead.model_validate(result)


@router.post("/submissions/{submission_id}/edit-and-approve", response_model=SubmissionRead)
async def edit_and_approve_submission(
    submission_id: UUID,
    body: SubmissionEditAndApprove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub: raise HTTPException(404, "Not found")
    try:
        result = await svc.edit_and_approve(db, sub=sub, user=user, proposed_value=body.proposed_value, note=body.note)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return SubmissionRead.model_validate(result)


@router.post("/submissions/{submission_id}/retry-apply", response_model=SubmissionRead)
async def retry_apply_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    """Re-run the apply-dispatcher on an already-approved submission.

    Used to recover from `apply_status='failed'` (handler raised) or
    `apply_status='skipped'` (no handler registered at approve-time, e.g.
    because the apply handler was added after the fact).

    Only operates on submissions whose status is 'approved' — refuses
    if the submission is pending/rejected/etc.
    """
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub:
        raise HTTPException(404, "Not found")
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
    # No moderation.review needed — proposer can always withdraw their own.
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub: raise HTTPException(404, "Not found")
    try:
        result = await svc.withdraw(db, sub=sub, user=user)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return SubmissionRead.model_validate(result)


# ════════════════════════════════════════════════════════════
#   Comments
# ════════════════════════════════════════════════════════════

@router.get("/submissions/{submission_id}/comments", response_model=list[CommentRead])
async def list_comments(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub: raise HTTPException(404, "Not found")
    is_moderator = user.is_owner or sub.assigned_moderator_id == user.id or sub.coapprover_id == user.id
    is_proposer  = sub.proposer_user_id == user.id
    if not (is_moderator or is_proposer):
        raise HTTPException(403, "No access")

    base = select(ModerationComment).where(ModerationComment.submission_id == submission_id)
    if not is_moderator:
        base = base.where(ModerationComment.is_internal.is_(False))
    rows = (await db.execute(base.order_by(ModerationComment.created_at.asc()))).scalars().all()
    return [CommentRead.model_validate(r) for r in rows]


@router.post("/submissions/{submission_id}/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def add_comment(
    submission_id: UUID,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub: raise HTTPException(404, "Not found")
    is_moderator = user.is_owner or sub.assigned_moderator_id == user.id or sub.coapprover_id == user.id
    is_proposer  = sub.proposer_user_id == user.id
    if not (is_moderator or is_proposer):
        raise HTTPException(403, "No access")
    if body.is_internal and not is_moderator:
        raise HTTPException(403, "Only moderators can post internal comments")

    c = await svc.add_comment(
        db, sub=sub, user=user, text=body.text,
        attachments=body.attachments, is_internal=body.is_internal,
    )
    return CommentRead.model_validate(c)


# ════════════════════════════════════════════════════════════
#   Rules CRUD
# ════════════════════════════════════════════════════════════

@router.get("/rules", response_model=RuleListResponse)
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("moderation.admin")),
):
    rows = (await db.execute(
        select(ModerationRule).order_by(ModerationRule.sort_order.asc(), ModerationRule.created_at.asc()),
    )).scalars().all()
    return RuleListResponse(items=[RuleRead.model_validate(r) for r in rows], total=len(rows))


@router.get("/rules/{rule_id}", response_model=RuleRead)
async def get_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("moderation.admin")),
):
    r = await db.get(ModerationRule, rule_id)
    if not r: raise HTTPException(404, "Not found")
    return RuleRead.model_validate(r)


@router.post("/rules", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.admin")),
):
    now = datetime.now(timezone.utc)
    data = body.model_dump(exclude_unset=True)
    # Convert conditions list of pydantic models to plain dicts for JSONB
    if data.get("trigger_conditions"):
        data["trigger_conditions"] = [c if isinstance(c, dict) else c.model_dump() for c in data["trigger_conditions"]]
    r = ModerationRule(created_at=now, updated_at=now, created_by_id=user.id, version=1, **data)
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return RuleRead.model_validate(r)


@router.patch("/rules/{rule_id}", response_model=RuleRead)
async def update_rule(
    rule_id: UUID,
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("moderation.admin")),
):
    r = await db.get(ModerationRule, rule_id)
    if not r: raise HTTPException(404, "Not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("trigger_conditions"):
        data["trigger_conditions"] = [c if isinstance(c, dict) else c.model_dump() for c in data["trigger_conditions"]]
    for k, v in data.items():
        setattr(r, k, v)
    r.version += 1
    r.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(r)
    return RuleRead.model_validate(r)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("moderation.admin")),
):
    r = await db.get(ModerationRule, rule_id)
    if not r: raise HTTPException(404, "Not found")
    await db.delete(r)
    await db.commit()


@router.post("/rules/{rule_id}/toggle", response_model=RuleRead)
async def toggle_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("moderation.admin")),
):
    r = await db.get(ModerationRule, rule_id)
    if not r: raise HTTPException(404, "Not found")
    r.is_active = not r.is_active
    r.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(r)
    return RuleRead.model_validate(r)


# ════════════════════════════════════════════════════════════
#   Moderators / External users — for sub-tabs
# ════════════════════════════════════════════════════════════

@router.get("/moderators")
async def list_moderators(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    """Users that are referenced as primary/co-approver in at least one rule, plus owners."""
    rows = (await db.execute(
        select(ModerationRule.moderator_primary_id, ModerationRule.moderator_coapprover_id),
    )).all()
    ids: set[UUID] = set()
    for r in rows:
        if r[0]: ids.add(r[0])
        if r[1]: ids.add(r[1])
    owner_rows = (await db.execute(select(User.id).where(User.is_owner.is_(True)))).all()
    for o in owner_rows: ids.add(o[0])

    if not ids:
        return {"items": []}
    users = (await db.execute(
        select(User).where(User.id.in_(ids)).order_by(User.full_name.asc()),
    )).scalars().all()
    return {"items": [
        {
            "id": str(u.id), "email": u.email, "full_name": u.full_name,
            "is_owner": u.is_owner, "is_active": u.is_active,
            "job_title": u.job_title, "department": u.department,
        } for u in users
    ]}


@router.get("/submitted-users")
async def list_submitted_users(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    """Users flagged as external (= subject to moderation by rule matching)."""
    rows = (await db.execute(
        select(User).where(User.is_external.is_(True)).order_by(User.full_name.asc()),
    )).scalars().all()
    return {"items": [
        {
            "id": str(u.id), "email": u.email, "full_name": u.full_name,
            "is_external": u.is_external,
            "bypass_moderation": u.bypass_moderation,
            "external_org_name": u.external_org_name,
            "is_active": u.is_active,
            "job_title": u.job_title,
        } for u in rows
    ]}


@router.patch("/users/{user_id}/flags")
async def patch_user_flags(
    user_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("admin.users")),
):
    """Toggle is_external / bypass_moderation / external_org_name."""
    u = await db.get(User, user_id)
    if not u: raise HTTPException(404, "Not found")
    for f in ("is_external", "bypass_moderation"):
        if f in body and isinstance(body[f], bool):
            setattr(u, f, body[f])
    if "external_org_name" in body:
        u.external_org_name = body["external_org_name"]
    await db.commit()
    await db.refresh(u)
    return {
        "id": str(u.id), "is_external": u.is_external,
        "bypass_moderation": u.bypass_moderation,
        "external_org_name": u.external_org_name,
    }
