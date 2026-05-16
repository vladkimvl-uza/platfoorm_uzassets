"""Comments API for projects and tasks."""
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.project import Project, ProjectComment
from app.models.task import Task, TaskComment
from app.models.user import User

router = APIRouter(tags=["comments"])


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
    await db.delete(c)
    await db.commit()
    return None


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
    await db.delete(c)
    await db.commit()
    return None
