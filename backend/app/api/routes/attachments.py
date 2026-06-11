"""Attachments — thin HTTP layer (refactored 2026-05-25).

File upload/download for tasks, projects, and companies. Scope-checks
via `ensure_company_access` stay in route (need request actor). Storage
backend (local/S3) abstracted in `app/services/storage/`.

Endpoints (URLs preserved):
  POST   /attachments/task|project|company/{id}     upload
  GET    /attachments/task|project|company/{id}     list
  GET    /attachments/{kind}/{id}/url               signed download URL
  DELETE /attachments/{kind}/{id}                   delete
  GET    /attachments/{kind}/{id}/denied-users      admin: list hidden users
  POST   /attachments/{kind}/{id}/deny              admin: hide for user
  DELETE /attachments/{kind}/{id}/deny/{user}       admin: restore access
  GET    /attachments/raw/{path}                    LocalStorage signed-raw
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi import status as http_status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import ensure_company_access
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.dependencies.attachments import AttachmentsServiceDep
from app.models.user import User
from app.services.attachments._helpers import is_admin
from app.services.storage import StorageError, get_storage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/attachments", tags=["attachments"])


# ─── pydantic ─────────────────────────────────────────────────────

class AttachmentOut(BaseModel):
    id: str
    filename: str
    mime_type: Optional[str]
    size_bytes: Optional[int]
    is_result_doc: bool = False
    uploader_id: Optional[str]
    uploader_name: Optional[str] = None
    created_at: datetime
    download_url: Optional[str] = None
    denied_user_count: int = 0


class DenyIn(BaseModel):
    user_id: str
    reason: Optional[str] = None


class DeniedUser(BaseModel):
    user_id: str
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    denied_at: datetime
    denied_by_email: Optional[str] = None
    reason: Optional[str] = None


def _require_admin_user(user: User) -> None:
    if not is_admin(user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Admin only")


# ─── task ─────────────────────────────────────────────────────────

@router.post("/task/{task_id}", response_model=AttachmentOut,
             status_code=http_status.HTTP_201_CREATED)
async def upload_task_attachment(
    task_id: UUID,
    service: AttachmentsServiceDep,
    file: UploadFile = File(...),
    is_result_doc: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")
    # Pre-fetch task for scope check
    from sqlalchemy import select

    from app.models.task import Task
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")
    if task.company_id:
        await ensure_company_access(db, user, task.company_id)
    out = await service.upload_task(
        task_id, file, is_result_doc=is_result_doc, user=user,
    )
    from app.services import watch_service
    await watch_service.auto_follow(db, user.id, "task", str(task_id)); await db.commit()
    await watch_service.notify_watchers(
        db, entity_type="task", entity_id=str(task_id), actor_id=user.id,
        notif_type="watch.comment", title="Файл в отслеживаемой задаче",
        body=f"{user.full_name or user.email} загрузил(а) файл: {out.get('filename', '')}"[:255],
        payload={"entity_type": "task", "entity_id": str(task_id)},
    )
    return AttachmentOut(**out)


@router.get("/task/{task_id}", response_model=list[AttachmentOut])
async def list_task_attachments(
    task_id: UUID,
    service: AttachmentsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, parent = await service.list_task(task_id, user=user)
    if parent.get("company_id"):
        await ensure_company_access(db, user, parent["company_id"])
    return [AttachmentOut(**it) for it in items]


@router.get("/task/{att_id}/url")
async def get_task_attachment_url(
    att_id: UUID,
    service: AttachmentsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att, task = await service.get_task_for_url(att_id)
    if task and task.company_id:
        await ensure_company_access(db, user, task.company_id)
    await service.check_not_denied(kind="task", att_id=att_id, user=user)
    key = getattr(att, "storage_key", None) or att.file_path
    url = await service.signed_url(key)
    return {"url": url, "expires_in": 300, "filename": att.filename, "mime_type": att.mime_type}


@router.delete("/task/{att_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_task_attachment(
    att_id: UUID,
    service: AttachmentsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await service.delete_task(att_id, user=user)
    if info.get("company_id"):
        await ensure_company_access(db, user, info["company_id"])


# ─── project ──────────────────────────────────────────────────────

@router.post("/project/{project_id}", response_model=AttachmentOut,
             status_code=http_status.HTTP_201_CREATED)
async def upload_project_attachment(
    project_id: UUID,
    service: AttachmentsServiceDep,
    file: UploadFile = File(...),
    is_result_doc: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")
    from sqlalchemy import select

    from app.models.project import Project
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
    if project.company_id:
        await ensure_company_access(db, user, project.company_id)
    out = await service.upload_project(
        project_id, file, is_result_doc=is_result_doc, user=user,
    )
    from app.services import watch_service
    await watch_service.auto_follow(db, user.id, "project", str(project_id)); await db.commit()
    await watch_service.notify_watchers(
        db, entity_type="project", entity_id=str(project_id), actor_id=user.id,
        notif_type="watch.comment", title="Файл в отслеживаемом проекте",
        body=f"{user.full_name or user.email} загрузил(а) файл: {out.get('filename', '')}"[:255],
        payload={"entity_type": "project", "entity_id": str(project_id)},
    )
    return AttachmentOut(**out)


@router.get("/project/{project_id}", response_model=list[AttachmentOut])
async def list_project_attachments(
    project_id: UUID,
    service: AttachmentsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, parent = await service.list_project(project_id, user=user)
    if parent.get("company_id"):
        await ensure_company_access(db, user, parent["company_id"])
    return [AttachmentOut(**it) for it in items]


@router.get("/project/{att_id}/url")
async def get_project_attachment_url(
    att_id: UUID,
    service: AttachmentsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = await service.get_project_for_url(att_id)
    if row[4]:
        await ensure_company_access(db, user, row[4])
    await service.check_not_denied(kind="project", att_id=att_id, user=user)
    url = await service.signed_url(row[1])
    return {"url": url, "expires_in": 300, "filename": row[2], "mime_type": row[3]}


@router.delete("/project/{att_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_project_attachment(
    att_id: UUID,
    service: AttachmentsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await service.delete_project(att_id, user=user)
    if info.get("company_id"):
        await ensure_company_access(db, user, info["company_id"])


# ─── company ──────────────────────────────────────────────────────

@router.post("/company/{company_id}", response_model=AttachmentOut,
             status_code=http_status.HTTP_201_CREATED)
async def upload_company_attachment(
    company_id: UUID,
    service: AttachmentsServiceDep,
    file: UploadFile = File(...),
    title: str = Form(...),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "companies.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: companies.edit")
    await ensure_company_access(db, user, company_id)
    out = await service.upload_company(
        company_id, file, title=title, category=category,
        description=description, year=year, user=user,
    )
    return AttachmentOut(**out)


@router.get("/company/{company_id}", response_model=list[AttachmentOut])
async def list_company_attachments(
    company_id: UUID,
    service: AttachmentsServiceDep,
    category: Optional[str] = None,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_company_access(db, user, company_id)
    items = await service.list_company(
        company_id, category=category, year=year, user=user,
    )
    return [AttachmentOut(**it) for it in items]


@router.get("/company/{att_id}/url")
async def get_company_attachment_url(
    att_id: UUID,
    service: AttachmentsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = await service.get_company_for_url(att_id)
    await ensure_company_access(db, user, row[0])
    await service.check_not_denied(kind="company", att_id=att_id, user=user)
    url = await service.signed_url(row[1])
    return {"url": url, "expires_in": 300, "filename": row[2], "mime_type": row[3]}


@router.delete("/company/{att_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_company_attachment(
    att_id: UUID,
    service: AttachmentsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = await service.delete_company(att_id, user=user)
    await ensure_company_access(db, user, company_id)


# ─── per-user access denial ────────────────────────────

@router.get("/{kind}/{att_id}/denied-users", response_model=list[DeniedUser])
async def list_denied_users(
    kind: str,
    att_id: UUID,
    service: AttachmentsServiceDep,
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    rows = await service.list_denied_users(kind=kind, att_id=att_id)
    return [
        DeniedUser(
            user_id=r[0], user_email=r[1], user_full_name=r[2],
            denied_at=r[3], denied_by_email=r[4], reason=r[5],
        )
        for r in rows
    ]


@router.post("/{kind}/{att_id}/deny", status_code=http_status.HTTP_204_NO_CONTENT)
async def deny_user(
    kind: str,
    att_id: UUID,
    body: DenyIn,
    service: AttachmentsServiceDep,
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    await service.deny_user(
        kind=kind, att_id=att_id, user_id_str=body.user_id,
        reason=body.reason, denied_by=user.id,
    )


@router.delete("/{kind}/{att_id}/deny/{user_id}",
               status_code=http_status.HTTP_204_NO_CONTENT)
async def allow_user(
    kind: str,
    att_id: UUID,
    user_id: UUID,
    service: AttachmentsServiceDep,
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    await service.allow_user(kind=kind, att_id=att_id, user_id=user_id)


# ─── local backend raw download (signed) ──────────────────────────

@router.get("/raw/{path:path}")
async def serve_local_signed(path: str, request: Request):
    """Validate signed URL and stream from disk. Only used by LocalStorage."""
    from app.services.storage.local import LocalStorage
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(http_status.HTTP_404_NOT_FOUND)
    exp = request.query_params.get("exp")
    sig = request.query_params.get("sig")
    if not exp or not sig:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Missing signature")
    try:
        if not storage.verify_signed(path, int(exp), sig):
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Invalid or expired signature")
        data = await storage.download(path)
    except StorageError:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Not found")
    return Response(content=data, media_type="application/octet-stream")
