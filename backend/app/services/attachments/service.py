"""Use cases for Attachments (task / project / company).

`get_storage()` returns whichever storage backend is configured
(local/s3); service treats it as an opaque port — upload/download/
signed_url/delete.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile, status as http_status

from app.models.task import TaskAttachment
from app.models.user import User
from app.services.attachments._helpers import (
    is_admin, make_key, validate_upload,
)
from app.services.storage import StorageError, get_storage
from app.uow.ports import UnitOfWorkABC


log = logging.getLogger(__name__)


def _to_attachment_out(
    *, att_id: str, filename: str, mime: Optional[str],
    size_bytes: Optional[int], is_result_doc: bool = False,
    uploader_id: Optional[str], uploader_name: Optional[str] = None,
    created_at: datetime, denied_user_count: int = 0,
) -> dict:
    return {
        "id": att_id,
        "filename": filename,
        "mime_type": mime,
        "size_bytes": size_bytes,
        "is_result_doc": is_result_doc,
        "uploader_id": uploader_id,
        "uploader_name": uploader_name,
        "created_at": created_at,
        "denied_user_count": denied_user_count,
    }


class AttachmentsService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── access denial helpers (route also uses them) ─────────────

    async def check_not_denied(self, *, kind: str, att_id: UUID, user: User) -> None:
        """Raise 403 if file hidden from user (admins bypass)."""
        if is_admin(user):
            return
        async with self.uow:
            denied = await self.uow.attachments.denied_attachment_ids(
                kind=kind, user_id=user.id, attachment_ids=[att_id],
            )
        if denied:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Access to this file is denied",
            )

    # ─── task uploads ─────────────────────────────────────────────

    async def upload_task(
        self, task_id: UUID, file: UploadFile, *,
        is_result_doc: bool, user: User,
    ) -> dict:
        async with self.uow:
            task = await self.uow.attachments.get_task(task_id)
            if not task:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")

            data = await file.read()
            mime = validate_upload(file, len(data))

            storage = get_storage()
            key = make_key(
                "tasks",
                str(task.company_id) if task.company_id else "_no_company",
                str(task.portfolio_year or "_"),
                str(task.id),
                filename=file.filename or "file",
            )
            try:
                await storage.upload(key, data, mime_type=mime)
            except StorageError as e:
                raise HTTPException(
                    http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                    f"storage failed: {e}",
                )

            att = TaskAttachment(
                task_id=task.id,
                uploader_id=user.id,
                filename=file.filename or "file",
                file_path=key,
                mime_type=mime,
                size_bytes=len(data),
            )
            att.storage_key = key  # type: ignore[attr-defined]
            att.is_result_doc = bool(is_result_doc)  # type: ignore[attr-defined]
            self.uow.attachments.add(att)
            await self.uow.attachments.flush()
            return _to_attachment_out(
                att_id=str(att.id),
                filename=att.filename,
                mime=att.mime_type,
                size_bytes=att.size_bytes,
                is_result_doc=bool(getattr(att, "is_result_doc", False)),
                uploader_id=str(att.uploader_id) if att.uploader_id else None,
                uploader_name=user.full_name or user.email,
                created_at=att.created_at,
            )

    async def list_task(self, task_id: UUID, *, user: User) -> tuple[list[dict], dict]:
        """Returns (items, parent_task) — caller does scope check on parent."""
        async with self.uow:
            r = self.uow.attachments
            task = await r.get_task(task_id)
            if not task:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")
            attachments = await r.list_task_attachments(task_id)
            ids = [str(a.id) for a in attachments]
            if is_admin(user):
                counts = await r.denied_counts(kind="task", attachment_ids=ids)
                items = attachments
            else:
                denied = await r.denied_attachment_ids(
                    kind="task", user_id=user.id, attachment_ids=ids,
                )
                items = [a for a in attachments if str(a.id) not in denied]
                counts = {}
        return [
            _to_attachment_out(
                att_id=str(a.id), filename=a.filename, mime=a.mime_type,
                size_bytes=a.size_bytes,
                is_result_doc=bool(getattr(a, "is_result_doc", False)),
                uploader_id=str(a.uploader_id) if a.uploader_id else None,
                created_at=a.created_at,
                denied_user_count=counts.get(str(a.id), 0),
            )
            for a in items
        ], {"company_id": task.company_id}

    async def get_task_for_url(self, att_id: UUID):
        async with self.uow:
            r = self.uow.attachments
            att = await r.get_task_attachment(att_id)
            if not att:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
            t = await r.get_task(att.task_id)
        return att, t

    async def delete_task(self, att_id: UUID, *, user: User) -> dict:
        async with self.uow:
            r = self.uow.attachments
            att = await r.get_task_attachment(att_id)
            if not att:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
            t = await r.get_task(att.task_id)
            if att.uploader_id != user.id and not is_admin(user):
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN, "Only uploader or admin",
                )
            key = getattr(att, "storage_key", None) or att.file_path
            company_id = t.company_id if t else None

        await self._delete_blob_and_row(
            key=key,
            row_deleter=lambda r2, aid: r2.attachments.delete_task_attachment_row(aid),
            att_id=att_id,
        )
        return {"company_id": company_id}

    # ─── project uploads ──────────────────────────────────────────

    async def upload_project(
        self, project_id: UUID, file: UploadFile, *,
        is_result_doc: bool, user: User,
    ) -> dict:
        async with self.uow:
            r = self.uow.attachments
            project = await r.get_project(project_id)
            if not project:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
            data = await file.read()
            mime = validate_upload(file, len(data))
            storage = get_storage()
            key = make_key(
                "projects",
                str(project.company_id) if project.company_id else "_no_company",
                str(project.portfolio_year or "_"),
                str(project.id),
                filename=file.filename or "file",
            )
            try:
                await storage.upload(key, data, mime_type=mime)
            except StorageError as e:
                raise HTTPException(
                    http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                    f"storage failed: {e}",
                )
            new_id = _uuid.uuid4()
            now = datetime.now(timezone.utc)
            await r.insert_project_attachment(
                att_id=new_id, project_id=project.id, uploader_id=user.id,
                filename=file.filename or "file", key=key, mime=mime,
                size_bytes=len(data), is_result_doc=is_result_doc, ts=now,
            )
        return _to_attachment_out(
            att_id=str(new_id),
            filename=file.filename or "file",
            mime=mime, size_bytes=len(data),
            is_result_doc=bool(is_result_doc),
            uploader_id=str(user.id),
            uploader_name=user.full_name or user.email,
            created_at=now,
        )

    async def list_project(self, project_id: UUID, *, user: User) -> tuple[list[dict], dict]:
        async with self.uow:
            r = self.uow.attachments
            project = await r.get_project(project_id)
            if not project:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
            rows = await r.list_project_attachments(project_id)
            ids = [row[0] for row in rows]
            if is_admin(user):
                counts = await r.denied_counts(kind="project", attachment_ids=ids)
                visible_rows = rows
            else:
                denied = await r.denied_attachment_ids(
                    kind="project", user_id=user.id, attachment_ids=ids,
                )
                visible_rows = [row for row in rows if row[0] not in denied]
                counts = {}
        return [
            _to_attachment_out(
                att_id=row[0], filename=row[1], mime=row[2],
                size_bytes=row[3],
                is_result_doc=bool(row[4]),
                uploader_id=row[5],
                created_at=row[6],
                denied_user_count=counts.get(row[0], 0),
            )
            for row in visible_rows
        ], {"company_id": project.company_id}

    async def get_project_for_url(self, att_id: UUID):
        async with self.uow:
            row = await self.uow.attachments.get_project_attachment_for_download(att_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
        # (project_id, storage_key, filename, mime_type, company_id)
        return row

    async def delete_project(self, att_id: UUID, *, user: User) -> dict:
        async with self.uow:
            r = self.uow.attachments
            row = await r.get_project_attachment_for_delete(att_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
            uploader_id, storage_key, company_id = row
            if uploader_id != user.id and not is_admin(user):
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN, "Only uploader or admin",
                )
        await self._delete_blob_and_row(
            key=storage_key,
            row_deleter=lambda r2, aid: r2.attachments.delete_project_attachment(aid),
            att_id=att_id,
        )
        return {"company_id": company_id}

    # ─── company uploads ──────────────────────────────────────────

    async def upload_company(
        self, company_id: UUID, file: UploadFile, *,
        title: str, category: Optional[str], description: Optional[str],
        year: Optional[int], user: User,
    ) -> dict:
        data = await file.read()
        mime = validate_upload(file, len(data))
        storage = get_storage()
        key = make_key(
            "company", str(company_id), str(year or "_"),
            category or "general",
            filename=file.filename or "file",
        )
        try:
            await storage.upload(key, data, mime_type=mime)
        except StorageError as e:
            raise HTTPException(
                http_status.HTTP_500_INTERNAL_SERVER_ERROR, f"storage failed: {e}",
            )
        new_id = _uuid.uuid4()
        async with self.uow:
            await self.uow.attachments.insert_company_attachment(
                att_id=new_id, company_id=company_id, uploader_id=user.id,
                category=category, title=title, description=description,
                filename=file.filename or "file", key=key, mime=mime,
                size_bytes=len(data), year=year,
            )
        return _to_attachment_out(
            att_id=str(new_id),
            filename=file.filename or "file",
            mime=mime, size_bytes=len(data),
            uploader_id=str(user.id),
            uploader_name=user.full_name or user.email,
            created_at=datetime.now(timezone.utc),
        )

    async def list_company(
        self, company_id: UUID, *,
        category: Optional[str], year: Optional[int], user: User,
    ) -> list[dict]:
        async with self.uow:
            r = self.uow.attachments
            rows = await r.list_company_attachments(
                company_id, category=category, year=year,
            )
            ids = [row[0] for row in rows]
            if is_admin(user):
                counts = await r.denied_counts(kind="company", attachment_ids=ids)
                visible_rows = rows
            else:
                denied = await r.denied_attachment_ids(
                    kind="company", user_id=user.id, attachment_ids=ids,
                )
                visible_rows = [row for row in rows if row[0] not in denied]
                counts = {}
        return [
            _to_attachment_out(
                att_id=row[0], filename=row[1], mime=row[2], size_bytes=row[3],
                uploader_id=row[4], created_at=row[5],
                denied_user_count=counts.get(row[0], 0),
            )
            for row in visible_rows
        ]

    async def get_company_for_url(self, att_id: UUID):
        async with self.uow:
            row = await self.uow.attachments.get_company_attachment_for_download(att_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
        # (company_id, storage_key, filename, mime_type)
        return row

    async def delete_company(self, att_id: UUID, *, user: User) -> UUID:
        """Returns company_id (route does scope check)."""
        async with self.uow:
            r = self.uow.attachments
            row = await r.get_company_attachment_for_delete(att_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Attachment not found")
            company_id, uploader_id, storage_key = row
            if uploader_id != user.id and not is_admin(user):
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN, "Only uploader or admin",
                )
        await self._delete_blob_and_row(
            key=storage_key,
            row_deleter=lambda r2, aid: r2.attachments.delete_company_attachment(aid),
            att_id=att_id,
        )
        return company_id

    # ─── signed URL builder ───────────────────────────────────────

    @staticmethod
    async def signed_url(key: str, *, ttl_seconds: int = 300) -> str:
        return await get_storage().signed_url(key, ttl_seconds=ttl_seconds)

    # ─── per-user access denial (Pack 150) ────────────────────────

    async def list_denied_users(self, *, kind: str, att_id: UUID):
        if kind not in ("task", "project", "company"):
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid kind")
        async with self.uow:
            return await self.uow.attachments.list_denied_users(kind=kind, att_id=att_id)

    async def deny_user(
        self, *, kind: str, att_id: UUID, user_id_str: str,
        reason: Optional[str], denied_by: UUID,
    ) -> None:
        if kind not in ("task", "project", "company"):
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid kind")
        try:
            uid = UUID(user_id_str)
        except (ValueError, TypeError):
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid user_id")
        async with self.uow:
            r = self.uow.attachments
            if not await r.user_exists(uid):
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
            await r.upsert_denial(
                kind=kind, att_id=att_id, user_id=uid,
                denied_by=denied_by, reason=reason,
            )

    async def allow_user(self, *, kind: str, att_id: UUID, user_id: UUID) -> None:
        if kind not in ("task", "project", "company"):
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid kind")
        async with self.uow:
            await self.uow.attachments.delete_denial(
                kind=kind, att_id=att_id, user_id=user_id,
            )

    # ─── internal blob+row delete ─────────────────────────────────

    async def _delete_blob_and_row(
        self, *, key: str, row_deleter, att_id: UUID,
    ) -> None:
        storage = get_storage()
        try:
            await storage.delete(key)
        except Exception as e:
            log.warning("storage delete failed for key=%s: %s", key, e)
        async with self.uow:
            await row_deleter(self.uow, att_id)
            await self.uow.attachments.flush()
