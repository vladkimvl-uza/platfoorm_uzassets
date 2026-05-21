"""Comments API for projects and tasks."""
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.project import Project, ProjectComment
from app.models.task import Task, TaskComment
from app.models.user import User

router = APIRouter(tags=["comments"])


# ─── audit helper (so company Активность widget sees comment CRUD) ──────
# entity_id MUST be the parent task/project UUID so the per-company SQL
# filter in /companies/{code}/activity (which joins audit_log → tasks/projects)
# picks the event up.
async def _audit_comment(
    db: AsyncSession,
    *,
    user: User,
    verb: str,                       # "created" | "updated" | "deleted"
    parent_kind: str,                # "task" | "project"
    parent_id: UUID,
    parent_title: str,
    body_excerpt: str,
) -> None:
    try:
        from app.services import audit_service
        verb_ru = {"created": "оставил", "updated": "обновил", "deleted": "удалил"}.get(verb, verb)
        kind_ru = "задаче" if parent_kind == "task" else "проекте"
        snippet = (body_excerpt or "").strip().replace("\n", " ")[:80]
        notes = (
            f"{verb_ru} комментарий в {kind_ru} «{parent_title or '—'}»"
            + (f": {snippet}" if snippet else "")
        )
        await audit_service.write_event(
            db,
            actor_id=user.id,
            actor_email=user.email,
            actor_role=(user.roles[0].code if getattr(user, "roles", None) else None),
            action=f"comment.{verb}",
            module="comments",
            entity_type="comment",
            entity_id=str(parent_id),
            entity_label=(parent_title or "")[:140],
            notes=notes,
            is_critical=False,
        )
    except Exception:
        # Audit failure must never block the user-facing operation
        import logging
        logging.getLogger(__name__).warning("comment audit failed", exc_info=True)


class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)


class CommentUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)


class CommentResponse(BaseModel):
    id: UUID
    author_id: Optional[UUID] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    body: str
    is_edited: bool
    created_at: datetime
    updated_at: datetime


def _is_admin(user):
    if getattr(user, "is_owner", False):
        return True
    if getattr(user, "is_admin", False):
        return True
    roles = getattr(user, "roles", None) or []
    if isinstance(roles, list):
        admin_roles = {"admin", "ROLE_ADMIN", "ROLE_OWNER", "owner"}
        return any(r in admin_roles for r in roles)
    return False


async def _resolve_author(db, author_id):
    if not author_id:
        return (None, None)
    user = await db.get(User, author_id)
    if not user:
        return (None, None)
    name = getattr(user, "full_name", None) or getattr(user, "name", None) or getattr(user, "email", None)
    return (name, getattr(user, "email", None))


def _to_response(c, name, email):
    return CommentResponse(
        id=c.id, author_id=c.author_id,
        author_name=name, author_email=email,
        body=c.body, is_edited=c.is_edited,
        created_at=c.created_at, updated_at=c.updated_at,
    )


@router.post("/projects/{project_id}/comments", response_model=CommentResponse, status_code=http_status.HTTP_201_CREATED)
async def create_project_comment(
    project_id: UUID,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await db.get(Project, project_id)
    if not project or project.is_archived:
        raise HTTPException(404, "Project not found")
    c = ProjectComment(project_id=project_id, author_id=current_user.id, body=payload.body, is_edited=False)
    db.add(c)
    await db.flush()
    company_name = None
    if project.company_id:
        from app.models.company import Company
        co = await db.get(Company, project.company_id)
        if co:
            company_name = co.name_short or co.name_ru
    from app.services.mention_service import notify_mentioned_users
    mentioned_ids = await notify_mentioned_users(
        db, text=payload.body,
        actor_id=current_user.id,
        actor_name=current_user.full_name or current_user.email,
        entity_type="project", entity_id=str(project_id),
        entity_title=project.title or "(без названия)",
        company_name=company_name,
        comment_id=str(c.id),
        link_url=f"/projects/{project_id}",
    )
    from app.services.comment_participants_service import notify_comment_participants
    await notify_comment_participants(
        db,
        entity_type="project", entity=project,
        comment_id=c.id, body=payload.body,
        actor_id=current_user.id,
        actor_name=current_user.full_name or current_user.email,
        company_name=company_name,
        link_url=f"/projects/{project_id}",
        skip_user_ids=mentioned_ids,
    )
    await _audit_comment(
        db, user=current_user, verb="created",
        parent_kind="project", parent_id=project_id,
        parent_title=project.title or "(без названия)",
        body_excerpt=payload.body,
    )
    await db.commit()
    await db.refresh(c)
    name, email = await _resolve_author(db, c.author_id)
    return _to_response(c, name, email)


@router.patch("/comments/projects/{comment_id}", response_model=CommentResponse)
async def update_project_comment(
    comment_id: UUID,
    payload: CommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = await db.get(ProjectComment, comment_id)
    if not c:
        raise HTTPException(404, "Comment not found")
    if c.author_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(403, "Only author or admin")
    c.body = payload.body
    c.is_edited = True
    project = await db.get(Project, c.project_id)
    await _audit_comment(
        db, user=current_user, verb="updated",
        parent_kind="project", parent_id=c.project_id,
        parent_title=(project.title if project else "") or "(без названия)",
        body_excerpt=payload.body,
    )
    await db.commit()
    await db.refresh(c)
    name, email = await _resolve_author(db, c.author_id)
    return _to_response(c, name, email)


@router.delete("/comments/projects/{comment_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_project_comment(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = await db.get(ProjectComment, comment_id)
    if not c:
        raise HTTPException(404, "Comment not found")
    if c.author_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(403, "Only author or admin")
    # Snapshot parent + body before deletion so the audit message is informative.
    parent_id = c.project_id
    body_snap = c.body
    project = await db.get(Project, parent_id)
    parent_title = (project.title if project else "") or "(без названия)"
    await db.delete(c)
    await _audit_comment(
        db, user=current_user, verb="deleted",
        parent_kind="project", parent_id=parent_id,
        parent_title=parent_title, body_excerpt=body_snap,
    )
    await db.commit()
    return None


@router.get("/tasks/{task_id}/comments", response_model=list[CommentResponse])
async def list_task_comments(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all comments for a task (latest first)."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    res = await db.execute(
        select(TaskComment)
        .where(TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at.desc())
        .limit(200)
    )
    out = []
    for c in res.scalars().all():
        name, email = await _resolve_author(db, c.author_id)
        out.append(_to_response(c, name, email))
    return out


@router.get("/projects/{project_id}/comments", response_model=list[CommentResponse])
async def list_project_comments(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all comments for a project (latest first)."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    res = await db.execute(
        select(ProjectComment)
        .where(ProjectComment.project_id == project_id)
        .order_by(ProjectComment.created_at.desc())
        .limit(200)
    )
    out = []
    for c in res.scalars().all():
        name, email = await _resolve_author(db, c.author_id)
        out.append(_to_response(c, name, email))
    return out


@router.post("/tasks/{task_id}/comments", response_model=CommentResponse, status_code=http_status.HTTP_201_CREATED)
async def create_task_comment(
    task_id: UUID,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task or task.is_archived:
        raise HTTPException(404, "Task not found")
    c = TaskComment(task_id=task_id, author_id=current_user.id, body=payload.body, is_edited=False)
    db.add(c)
    await db.flush()
    # Resolve company name for richer mention context
    company_name = None
    if task.company_id:
        from app.models.company import Company
        co = await db.get(Company, task.company_id)
        if co:
            company_name = co.name_short or co.name_ru
    from app.services.mention_service import notify_mentioned_users
    mentioned_ids = await notify_mentioned_users(
        db, text=payload.body,
        actor_id=current_user.id,
        actor_name=current_user.full_name or current_user.email,
        entity_type="task", entity_id=str(task_id),
        company_name=company_name,
        comment_id=str(c.id),
        entity_title=task.title or "(без названия)",
        link_url=f"/tasks/{task_id}",
    )
    from app.services.comment_participants_service import notify_comment_participants
    await notify_comment_participants(
        db,
        entity_type="task", entity=task,
        comment_id=c.id, body=payload.body,
        actor_id=current_user.id,
        actor_name=current_user.full_name or current_user.email,
        company_name=company_name,
        link_url=f"/tasks/{task_id}",
        skip_user_ids=mentioned_ids,
    )
    await _audit_comment(
        db, user=current_user, verb="created",
        parent_kind="task", parent_id=task_id,
        parent_title=task.title or "(без названия)",
        body_excerpt=payload.body,
    )
    await db.commit()
    await db.refresh(c)
    name, email = await _resolve_author(db, c.author_id)
    return _to_response(c, name, email)


@router.patch("/comments/tasks/{comment_id}", response_model=CommentResponse)
async def update_task_comment(
    comment_id: UUID,
    payload: CommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = await db.get(TaskComment, comment_id)
    if not c:
        raise HTTPException(404, "Comment not found")
    if c.author_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(403, "Only author or admin")
    c.body = payload.body
    c.is_edited = True
    task = await db.get(Task, c.task_id)
    await _audit_comment(
        db, user=current_user, verb="updated",
        parent_kind="task", parent_id=c.task_id,
        parent_title=(task.title if task else "") or "(без названия)",
        body_excerpt=payload.body,
    )
    await db.commit()
    await db.refresh(c)
    name, email = await _resolve_author(db, c.author_id)
    return _to_response(c, name, email)


@router.delete("/comments/tasks/{comment_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_task_comment(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = await db.get(TaskComment, comment_id)
    if not c:
        raise HTTPException(404, "Comment not found")
    if c.author_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(403, "Only author or admin")
    parent_id = c.task_id
    body_snap = c.body
    task = await db.get(Task, parent_id)
    parent_title = (task.title if task else "") or "(без названия)"
    await db.delete(c)
    await _audit_comment(
        db, user=current_user, verb="deleted",
        parent_kind="task", parent_id=parent_id,
        parent_title=parent_title, body_excerpt=body_snap,
    )
    await db.commit()
    return None
