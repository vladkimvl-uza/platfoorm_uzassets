"""Attachments — file upload/download for tasks, projects, and companies.

Endpoints:
  POST   /attachments/task/{task_id}        upload a file to a task
  POST   /attachments/project/{project_id}  upload to a project
  POST   /attachments/company/{company_id}  upload to a company (general docs)
  GET    /attachments/task/{task_id}        list task attachments
  GET    /attachments/project/{project_id}  list project attachments
  GET    /attachments/company/{company_id}  list company attachments
  GET    /attachments/{kind}/{id}/url       signed download URL
  DELETE /attachments/{kind}/{id}           remove attachment
  GET    /attachments/raw/{key:path}        (local backend only) signed-raw

All routes enforce per-company scope. Max size: 25 MB (matches nginx).
Whitelist mime types: pdf/word/excel/png/jpg/zip.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from fastapi import status as http_status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids, ensure_company_access
from app.core.security import get_current_user
from app.database import get_db
from app.models.project import Project
from app.models.task import Task, TaskAttachment
from app.models.user import User
from app.services.storage import get_storage, StorageError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/attachments", tags=["attachments"])

MAX_SIZE_BYTES = 25 * 1024 * 1024
ALLOWED_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image/png", "image/jpeg", "image/webp",
    "application/zip", "application/x-zip-compressed",
    "text/plain", "text/csv",
}


class AttachmentOut(BaseModel):
    id: str
    filename: str
    mime_type: Optional[str]
    size_bytes: Optional[int]
    is_result_doc: bool = False
    uploader_id: Optional[str]
    uploader_name: Optional[str] = None
    created_at: datetime
    download_url: Optional[str] = None  # populated only on demand
    denied_user_count: int = 0           # admin-visible: how many users this is hidden from


# ─── access-denial helpers ────────────────────────────────────────────
def _is_admin(user: User) -> bool:
    return bool(getattr(user, "is_owner", False) or getattr(user, "is_admin", False))


async def _denied_attachment_ids(
    db: AsyncSession, *, kind: str, user_id, attachment_ids: Optional[list] = None,
) -> set[str]:
    """Return the set of attachment_id values (as strings) hidden from `user_id`
    among the given kind. If `attachment_ids` is None, returns ALL denied for that
    kind+user."""
    if attachment_ids is not None and not attachment_ids:
        return set()
    sql = """
        SELECT attachment_id::text FROM attachment_access_denial
        WHERE kind = :k AND user_id = :u
    """
    params: dict = {"k": kind, "u": user_id}
    if attachment_ids is not None:
        sql += " AND attachment_id = ANY(:ids)"
        params["ids"] = list(attachment_ids)
    rows = (await db.execute(text(sql), params)).all()
    return {r[0] for r in rows}


async def _denied_counts(
    db: AsyncSession, *, kind: str, attachment_ids: list,
) -> dict[str, int]:
    """attachment_id → number of users it's hidden from (admin view)."""
    if not attachment_ids:
        return {}
    rows = (await db.execute(text("""
        SELECT attachment_id::text, COUNT(*) FROM attachment_access_denial
        WHERE kind = :k AND attachment_id = ANY(:ids)
        GROUP BY attachment_id
    """), {"k": kind, "ids": list(attachment_ids)})).all()
    return {r[0]: int(r[1]) for r in rows}


async def _check_not_denied(db: AsyncSession, *, kind: str, att_id, user: User) -> None:
    """Raise 403 if the file is hidden from this user (admins bypass)."""
    if _is_admin(user):
        return
    denied = await _denied_attachment_ids(db, kind=kind, user_id=user.id, attachment_ids=[att_id])
    if denied:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Access to this file is denied")


def _validate_upload(file: UploadFile, size_bytes: int) -> str:
    if size_bytes > MAX_SIZE_BYTES:
        raise HTTPException(http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"file too large ({size_bytes} > {MAX_SIZE_BYTES})")
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if mime not in ALLOWED_MIMES:
        raise HTTPException(http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"mime type '{mime}' is not allowed")
    return mime


def _make_key(prefix: str, *parts: str, filename: str) -> str:
    """Construct storage key. Random UUID prevents enumeration + clash."""
    safe_name = "".join(c for c in (filename or "file") if c.isalnum() or c in (".", "-", "_"))[:120]
    suffix = _uuid.uuid4().hex
    parts_clean = "/".join(p for p in parts if p)
    return f"{prefix}/{parts_clean}/{suffix}-{safe_name}"


# =====================================================================
# Task attachments
# =====================================================================

@router.post("/task/{task_id}", response_model=AttachmentOut, status_code=http_status.HTTP_201_CREATED)
async def upload_task_attachment(
    task_id: UUID,
    file: UploadFile = File(...),
    is_result_doc: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.core.security import has_effective_permission
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")

    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")
    if task.company_id:
        await ensure_company_access(db, user, task.company_id)

    data = await file.read()
    mime = _validate_upload(file, len(data))

    storage = get_storage()
    key = _make_key(
        "tasks",
        str(task.company_id) if task.company_id else "_no_company",
        str(task.portfolio_year or "_"),
        str(task.id),
        filename=file.filename or "file",
    )
    try:
        await storage.upload(key, data, mime_type=mime)
    except StorageError as e:
        raise HTTPException(http_status.HTTP_500_INTERNAL_SERVER_ERROR, f"storage failed: {e}")

    att = TaskAttachment(
        task_id=task.id,
        uploader_id=user.id,
        filename=file.filename or "file",
        file_path=key,  # legacy column — store key here too for compat
        mime_type=mime,
        size_bytes=len(data),
    )
    # New columns from 9aV migration
    att.storage_key = key  # type: ignore[attr-defined]
    att.is_result_doc = bool(is_result_doc)  # type: ignore[attr-defined]
    db.add(att)
    await db.commit()
    await db.refresh(att)

    return AttachmentOut(
        id=str(att.id),
        filename=att.filename,
        mime_type=att.mime_type,
        size_bytes=att.size_bytes,
        is_result_doc=bool(getattr(att, "is_result_doc", False)),
        uploader_id=str(att.uploader_id) if att.uploader_id else None,
        uploader_name=user.full_name or user.email,
        created_at=att.created_at,
    )


@router.get("/task/{task_id}", response_model=list[AttachmentOut])
async def list_task_attachments(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")
    if task.company_id:
        await ensure_company_access(db, user, task.company_id)
    res = await db.execute(
        select(TaskAttachment).where(TaskAttachment.task_id == task_id).order_by(TaskAttachment.created_at.desc())
    )
    attachments = list(res.scalars().all())
    ids = [str(a.id) for a in attachments]
    admin = _is_admin(user)
    # Filter out denied for non-admins; admins see everything (with counts).
    if not admin:
        denied = await _denied_attachment_ids(db, kind="task", user_id=user.id, attachment_ids=ids)
        attachments = [a for a in attachments if str(a.id) not in denied]
        counts: dict[str, int] = {}
    else:
        counts = await _denied_counts(db, kind="task", attachment_ids=ids)
    return [
        AttachmentOut(
            id=str(a.id),
            filename=a.filename,
            mime_type=a.mime_type,
            size_bytes=a.size_bytes,
            is_result_doc=bool(getattr(a, "is_result_doc", False)),
            uploader_id=str(a.uploader_id) if a.uploader_id else None,
            created_at=a.created_at,
            denied_user_count=counts.get(str(a.id), 0),
        )
        for a in attachments
    ]


# =====================================================================
# Project attachments — project_attachments table accessed via raw SQL
# (no ORM model wraps it currently). Mirrors the task endpoints exactly.
# =====================================================================

@router.post("/project/{project_id}", response_model=AttachmentOut, status_code=http_status.HTTP_201_CREATED)
async def upload_project_attachment(
    project_id: UUID,
    file: UploadFile = File(...),
    is_result_doc: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.core.security import has_effective_permission
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
    if project.company_id:
        await ensure_company_access(db, user, project.company_id)

    data = await file.read()
    mime = _validate_upload(file, len(data))

    storage = get_storage()
    key = _make_key(
        "projects",
        str(project.company_id) if project.company_id else "_no_company",
        str(project.portfolio_year or "_"),
        str(project.id),
        filename=file.filename or "file",
    )
    try:
        await storage.upload(key, data, mime_type=mime)
    except StorageError as e:
        raise HTTPException(http_status.HTTP_500_INTERNAL_SERVER_ERROR, f"storage failed: {e}")

    new_id = _uuid.uuid4()
    now = datetime.now(timezone.utc)
    await db.execute(text("""
        INSERT INTO project_attachments
          (id, project_id, uploader_id, filename, storage_key, mime_type, size_bytes,
           is_result_doc, created_at, updated_at)
        VALUES (:id, :pid, :u, :fn, :key, :mime, :sz, :res, :ts, :ts)
    """), {
        "id": new_id, "pid": project.id, "u": user.id,
        "fn": file.filename or "file", "key": key, "mime": mime,
        "sz": len(data), "res": bool(is_result_doc), "ts": now,
    })
    await db.commit()
    return AttachmentOut(
        id=str(new_id),
        filename=file.filename or "file",
        mime_type=mime, size_bytes=len(data),
        is_result_doc=bool(is_result_doc),
        uploader_id=str(user.id),
        uploader_name=user.full_name or user.email,
        created_at=now,
    )


@router.get("/project/{project_id}", response_model=list[AttachmentOut])
async def list_project_attachments(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
    if project.company_id:
        await ensure_company_access(db, user, project.company_id)
    rows = (await db.execute(text("""
        SELECT id::text, filename, mime_type, size_bytes, is_result_doc,
               uploader_id::text, created_at
        FROM project_attachments
        WHERE project_id=:pid
        ORDER BY created_at DESC
    """), {"pid": project_id})).all()
    ids = [r[0] for r in rows]
    admin = _is_admin(user)
    if not admin:
        denied = await _denied_attachment_ids(db, kind="project", user_id=user.id, attachment_ids=ids)
        rows = [r for r in rows if r[0] not in denied]
        counts: dict[str, int] = {}
    else:
        counts = await _denied_counts(db, kind="project", attachment_ids=ids)
    return [
        AttachmentOut(
            id=r[0], filename=r[1], mime_type=r[2], size_bytes=r[3],
            is_result_doc=bool(r[4]), uploader_id=r[5], created_at=r[6],
            denied_user_count=counts.get(r[0], 0),
        )
        for r in rows
    ]


@router.get("/project/{att_id}/url")
async def get_project_attachment_url(
    att_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (await db.execute(text("""
        SELECT pa.project_id, pa.storage_key, pa.filename, pa.mime_type, p.company_id
        FROM project_attachments pa
        JOIN projects p ON p.id = pa.project_id
        WHERE pa.id=:i
    """), {"i": att_id})).first()
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
    if row[4]:
        await ensure_company_access(db, user, row[4])
    await _check_not_denied(db, kind="project", att_id=att_id, user=user)
    url = await get_storage().signed_url(row[1], ttl_seconds=300)
    return {"url": url, "expires_in": 300, "filename": row[2], "mime_type": row[3]}


# =====================================================================
# Delete endpoints — author or admin can delete
# =====================================================================

async def _delete_blob_and_row(
    db: AsyncSession, *, key: str, sql_delete: str, sql_params: dict,
) -> None:
    storage = get_storage()
    try:
        await storage.delete(key)
    except Exception as e:
        # Storage failure should NOT block DB cleanup — orphan blob is preferable
        # to a broken UI that still shows a "deleted" file row.
        log.warning("storage delete failed for key=%s: %s", key, e)
    await db.execute(text(sql_delete), sql_params)
    await db.commit()


@router.delete("/task/{att_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_task_attachment(
    att_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att = (await db.execute(select(TaskAttachment).where(TaskAttachment.id == att_id))).scalar_one_or_none()
    if not att:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
    t = (await db.execute(select(Task).where(Task.id == att.task_id))).scalar_one_or_none()
    if t and t.company_id:
        await ensure_company_access(db, user, t.company_id)
    # Author or admin only
    is_admin = bool(getattr(user, "is_owner", False) or getattr(user, "is_admin", False))
    if att.uploader_id != user.id and not is_admin:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Only uploader or admin")
    key = getattr(att, "storage_key", None) or att.file_path
    await _delete_blob_and_row(
        db, key=key,
        sql_delete="DELETE FROM task_attachments WHERE id=:i",
        sql_params={"i": att_id},
    )


@router.delete("/project/{att_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_project_attachment(
    att_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (await db.execute(text("""
        SELECT pa.uploader_id, pa.storage_key, p.company_id
        FROM project_attachments pa
        JOIN projects p ON p.id = pa.project_id
        WHERE pa.id=:i
    """), {"i": att_id})).first()
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
    if row[2]:
        await ensure_company_access(db, user, row[2])
    is_admin = bool(getattr(user, "is_owner", False) or getattr(user, "is_admin", False))
    if row[0] != user.id and not is_admin:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Only uploader or admin")
    await _delete_blob_and_row(
        db, key=row[1],
        sql_delete="DELETE FROM project_attachments WHERE id=:i",
        sql_params={"i": att_id},
    )


@router.delete("/company/{att_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_company_attachment(
    att_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (await db.execute(text("""
        SELECT company_id, uploader_id, storage_key FROM company_attachments WHERE id=:i
    """), {"i": att_id})).first()
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
    await ensure_company_access(db, user, row[0])
    is_admin = bool(getattr(user, "is_owner", False) or getattr(user, "is_admin", False))
    if row[1] != user.id and not is_admin:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Only uploader or admin")
    await _delete_blob_and_row(
        db, key=row[2],
        sql_delete="DELETE FROM company_attachments WHERE id=:i",
        sql_params={"i": att_id},
    )


# =====================================================================
# Company attachments
# =====================================================================

@router.post("/company/{company_id}", response_model=AttachmentOut, status_code=http_status.HTTP_201_CREATED)
async def upload_company_attachment(
    company_id: UUID,
    file: UploadFile = File(...),
    title: str = Form(...),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.core.security import has_effective_permission
    if not await has_effective_permission(db, user, "companies.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: companies.edit")
    await ensure_company_access(db, user, company_id)

    data = await file.read()
    mime = _validate_upload(file, len(data))

    storage = get_storage()
    key = _make_key(
        "company",
        str(company_id),
        str(year or "_"),
        category or "general",
        filename=file.filename or "file",
    )
    try:
        await storage.upload(key, data, mime_type=mime)
    except StorageError as e:
        raise HTTPException(http_status.HTTP_500_INTERNAL_SERVER_ERROR, f"storage failed: {e}")

    new_id = _uuid.uuid4()
    await db.execute(text("""
        INSERT INTO company_attachments
          (id, company_id, uploader_id, category, title, description,
           filename, storage_key, mime_type, size_bytes, year)
        VALUES (:id, :co, :u, :cat, :title, :desc, :fn, :key, :mime, :sz, :yr)
    """), {
        "id": new_id, "co": company_id, "u": user.id, "cat": category,
        "title": title, "desc": description,
        "fn": file.filename, "key": key, "mime": mime, "sz": len(data), "yr": year,
    })
    await db.commit()
    return AttachmentOut(
        id=str(new_id),
        filename=file.filename or "file",
        mime_type=mime,
        size_bytes=len(data),
        uploader_id=str(user.id),
        uploader_name=user.full_name or user.email,
        created_at=datetime.now(timezone.utc),
    )


@router.get("/company/{company_id}", response_model=list[AttachmentOut])
async def list_company_attachments(
    company_id: UUID,
    category: Optional[str] = None,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_company_access(db, user, company_id)
    q = "SELECT id::text, filename, mime_type, size_bytes, uploader_id::text, created_at FROM company_attachments WHERE company_id=:co"
    params: dict = {"co": company_id}
    if category:
        q += " AND category=:cat"; params["cat"] = category
    if year is not None:
        q += " AND year=:yr"; params["yr"] = year
    q += " ORDER BY created_at DESC"
    rows = (await db.execute(text(q), params)).all()
    ids = [r[0] for r in rows]
    admin = _is_admin(user)
    if not admin:
        denied = await _denied_attachment_ids(db, kind="company", user_id=user.id, attachment_ids=ids)
        rows = [r for r in rows if r[0] not in denied]
        counts: dict[str, int] = {}
    else:
        counts = await _denied_counts(db, kind="company", attachment_ids=ids)
    return [
        AttachmentOut(
            id=r[0], filename=r[1], mime_type=r[2], size_bytes=r[3],
            uploader_id=r[4], created_at=r[5],
            denied_user_count=counts.get(r[0], 0),
        )
        for r in rows
    ]


# =====================================================================
# Signed download URL
# =====================================================================

@router.get("/task/{att_id}/url")
async def get_task_attachment_url(
    att_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att = (await db.execute(select(TaskAttachment).where(TaskAttachment.id == att_id))).scalar_one_or_none()
    if not att:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
    # Scope via parent task
    t = (await db.execute(select(Task).where(Task.id == att.task_id))).scalar_one_or_none()
    if t and t.company_id:
        await ensure_company_access(db, user, t.company_id)
    await _check_not_denied(db, kind="task", att_id=att_id, user=user)

    storage = get_storage()
    key = getattr(att, "storage_key", None) or att.file_path
    url = await storage.signed_url(key, ttl_seconds=300)
    return {"url": url, "expires_in": 300, "filename": att.filename, "mime_type": att.mime_type}


@router.get("/company/{att_id}/url")
async def get_company_attachment_url(
    att_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (await db.execute(text("""
        SELECT company_id, storage_key, filename, mime_type FROM company_attachments WHERE id=:i
    """), {"i": att_id})).first()
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
    await ensure_company_access(db, user, row[0])
    await _check_not_denied(db, kind="company", att_id=att_id, user=user)
    url = await get_storage().signed_url(row[1], ttl_seconds=300)
    return {"url": url, "expires_in": 300, "filename": row[2], "mime_type": row[3]}


# =====================================================================
# Admin per-user access control (Pack 150)
# =====================================================================

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


def _require_admin(user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Admin only")


@router.get("/{kind}/{att_id}/denied-users", response_model=list[DeniedUser])
async def list_denied_users(
    kind: str,
    att_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List users this file is hidden from. Admin only."""
    _require_admin(user)
    if kind not in ("task", "project", "company"):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid kind")
    rows = (await db.execute(text("""
        SELECT u.id::text, u.email, u.full_name, aad.denied_at,
               b.email AS by_email, aad.reason
        FROM attachment_access_denial aad
        JOIN users u ON u.id = aad.user_id
        LEFT JOIN users b ON b.id = aad.denied_by
        WHERE aad.kind = :k AND aad.attachment_id = :i
        ORDER BY aad.denied_at DESC
    """), {"k": kind, "i": att_id})).all()
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Admin: hide this file from a specific user."""
    _require_admin(user)
    if kind not in ("task", "project", "company"):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid kind")
    try:
        uid = UUID(body.user_id)
    except (ValueError, TypeError):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid user_id")
    # Validate user exists
    exists = (await db.execute(text("SELECT 1 FROM users WHERE id = :u"), {"u": uid})).scalar()
    if not exists:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
    # Upsert (unique on kind+att+user)
    await db.execute(text("""
        INSERT INTO attachment_access_denial (kind, attachment_id, user_id, denied_by, reason)
        VALUES (:k, :a, :u, :by, :r)
        ON CONFLICT (kind, attachment_id, user_id) DO UPDATE
        SET denied_by = EXCLUDED.denied_by,
            denied_at = NOW(),
            reason    = EXCLUDED.reason
    """), {"k": kind, "a": att_id, "u": uid, "by": user.id, "r": body.reason})
    await db.commit()


@router.delete("/{kind}/{att_id}/deny/{user_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def allow_user(
    kind: str,
    att_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Admin: remove the hide for a specific user (restore access)."""
    _require_admin(user)
    if kind not in ("task", "project", "company"):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid kind")
    await db.execute(text("""
        DELETE FROM attachment_access_denial
        WHERE kind = :k AND attachment_id = :a AND user_id = :u
    """), {"k": kind, "a": att_id, "u": user_id})
    await db.commit()


# =====================================================================
# Local-backend raw download (signed)
# =====================================================================

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
