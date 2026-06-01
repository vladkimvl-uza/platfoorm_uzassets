"""Comments API for projects and tasks — thin HTTP layer (refactored 2026-05-25).

Side-effects (mention notifications, participant notifications, audit log)
are post-commit best-effort and stay in route file. They need the request
actor identity and are explicitly fire-and-forget.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.dependencies.comments import CommentsServiceDep
from app.models.user import User

router = APIRouter(tags=["comments"])


# ─── pydantic ─────────────────────────────────────────────────────

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


# ─── side-effects helpers ─────────────────────────────────────────

async def _audit_comment(
    db: AsyncSession, *, user: User, verb: str,
    parent_kind: str, parent_id: UUID,
    parent_title: str, body_excerpt: str,
) -> None:
    try:
        from app.services import audit_service
        verb_ru = {"created": "оставил", "updated": "обновил",
                   "deleted": "удалил"}.get(verb, verb)
        kind_ru = "задаче" if parent_kind == "task" else "проекте"
        snippet = (body_excerpt or "").strip().replace("\n", " ")[:80]
        notes = (
            f"{verb_ru} комментарий в {kind_ru} «{parent_title or '—'}»"
            + (f": {snippet}" if snippet else "")
        )
        await audit_service.write_event(
            db,
            actor_id=user.id, actor_email=user.email,
            actor_role=(user.roles[0].code if getattr(user, "roles", None) else None),
            action=f"comment.{verb}", module="comments",
            entity_type="comment", entity_id=str(parent_id),
            entity_label=(parent_title or "")[:140],
            notes=notes, is_critical=False,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("comment audit failed", exc_info=True)


async def _notify_mentions_and_participants(
    db: AsyncSession, *,
    kind: str, parent, parent_id: UUID,
    body: str, comment_id: UUID,
    actor: User, company_name: Optional[str],
) -> None:
    from app.services.comment_participants_service import notify_comment_participants
    from app.services.mention_service import notify_mentioned_users
    link_url = f"/{'projects' if kind == 'project' else 'tasks'}/{parent_id}"
    mentioned_ids = await notify_mentioned_users(
        db, text=body,
        actor_id=actor.id,
        actor_name=actor.full_name or actor.email,
        entity_type=kind, entity_id=str(parent_id),
        entity_title=getattr(parent, "title", None) or "(без названия)",
        company_name=company_name,
        comment_id=str(comment_id),
        link_url=link_url,
    )
    await notify_comment_participants(
        db,
        entity_type=kind, entity=parent,
        comment_id=comment_id, body=body,
        actor_id=actor.id,
        actor_name=actor.full_name or actor.email,
        company_name=company_name,
        link_url=link_url,
        skip_user_ids=mentioned_ids,
    )


def _to_response(c, name, email) -> CommentResponse:
    return CommentResponse(
        id=c.id, author_id=c.author_id,
        author_name=name, author_email=email,
        body=c.body, is_edited=c.is_edited,
        created_at=c.created_at, updated_at=c.updated_at,
    )


# ─── PROJECT comments ─────────────────────────────────────────────

@router.post("/projects/{project_id}/comments",
             response_model=CommentResponse,
             status_code=http_status.HTTP_201_CREATED)
async def create_project_comment(
    project_id: UUID,
    payload: CommentCreate,
    service: CommentsServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    info = await service.create_comment(
        "project", project_id,
        body=payload.body, author_id=current_user.id,
    )
    c, parent = info["comment"], info["parent"]
    await _notify_mentions_and_participants(
        db, kind="project", parent=parent, parent_id=project_id,
        body=payload.body, comment_id=c.id,
        actor=current_user, company_name=info["company_name"],
    )
    await _audit_comment(
        db, user=current_user, verb="created",
        parent_kind="project", parent_id=project_id,
        parent_title=parent.title or "(без названия)",
        body_excerpt=payload.body,
    )
    await db.commit()
    return _to_response(c, info["author_name"], info["author_email"])


@router.patch("/comments/projects/{comment_id}", response_model=CommentResponse)
async def update_project_comment(
    comment_id: UUID,
    payload: CommentUpdate,
    service: CommentsServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    info = await service.update_comment(
        "project", comment_id, body=payload.body, actor=current_user,
    )
    c = info["comment"]
    await _audit_comment(
        db, user=current_user, verb="updated",
        parent_kind="project", parent_id=info["parent_id"],
        parent_title=(info["parent"].title if info["parent"] else "") or "(без названия)",
        body_excerpt=payload.body,
    )
    await db.commit()
    return _to_response(c, info["author_name"], info["author_email"])


@router.delete("/comments/projects/{comment_id}",
               status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_project_comment(
    comment_id: UUID,
    service: CommentsServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    info = await service.delete_comment("project", comment_id, actor=current_user)
    await _audit_comment(
        db, user=current_user, verb="deleted",
        parent_kind="project", parent_id=info["parent_id"],
        parent_title=info["parent_title"], body_excerpt=info["body_snap"],
    )
    await db.commit()
    return None


@router.get("/projects/{project_id}/comments", response_model=list[CommentResponse])
async def list_project_comments(
    project_id: UUID,
    service: CommentsServiceDep,
    current_user: User = Depends(get_current_user),
):
    rows = await service.list_comments("project", project_id)
    return [_to_response(c, name, email) for c, name, email in rows]


# ─── TASK comments ────────────────────────────────────────────────

@router.post("/tasks/{task_id}/comments",
             response_model=CommentResponse,
             status_code=http_status.HTTP_201_CREATED)
async def create_task_comment(
    task_id: UUID,
    payload: CommentCreate,
    service: CommentsServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    info = await service.create_comment(
        "task", task_id, body=payload.body, author_id=current_user.id,
    )
    c, parent = info["comment"], info["parent"]
    await _notify_mentions_and_participants(
        db, kind="task", parent=parent, parent_id=task_id,
        body=payload.body, comment_id=c.id,
        actor=current_user, company_name=info["company_name"],
    )
    await _audit_comment(
        db, user=current_user, verb="created",
        parent_kind="task", parent_id=task_id,
        parent_title=parent.title or "(без названия)",
        body_excerpt=payload.body,
    )
    await db.commit()
    return _to_response(c, info["author_name"], info["author_email"])


@router.patch("/comments/tasks/{comment_id}", response_model=CommentResponse)
async def update_task_comment(
    comment_id: UUID,
    payload: CommentUpdate,
    service: CommentsServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    info = await service.update_comment(
        "task", comment_id, body=payload.body, actor=current_user,
    )
    c = info["comment"]
    await _audit_comment(
        db, user=current_user, verb="updated",
        parent_kind="task", parent_id=info["parent_id"],
        parent_title=(info["parent"].title if info["parent"] else "") or "(без названия)",
        body_excerpt=payload.body,
    )
    await db.commit()
    return _to_response(c, info["author_name"], info["author_email"])


@router.delete("/comments/tasks/{comment_id}",
               status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_task_comment(
    comment_id: UUID,
    service: CommentsServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    info = await service.delete_comment("task", comment_id, actor=current_user)
    await _audit_comment(
        db, user=current_user, verb="deleted",
        parent_kind="task", parent_id=info["parent_id"],
        parent_title=info["parent_title"], body_excerpt=info["body_snap"],
    )
    await db.commit()
    return None


@router.get("/tasks/{task_id}/comments", response_model=list[CommentResponse])
async def list_task_comments(
    task_id: UUID,
    service: CommentsServiceDep,
    current_user: User = Depends(get_current_user),
):
    rows = await service.list_comments("task", task_id)
    return [_to_response(c, name, email) for c, name, email in rows]
