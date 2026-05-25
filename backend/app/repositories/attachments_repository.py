"""Data access for Attachments (task / project / company).

`project_attachments` and `company_attachments` have no ORM model —
accessed via raw `text()`. `task_attachments` uses TaskAttachment ORM.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.task import Task, TaskAttachment


class AttachmentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── parents ──────────────────────────────────────────────────

    async def get_task(self, task_id: UUID) -> Optional[Task]:
        res = await self.session.execute(select(Task).where(Task.id == task_id))
        return res.scalar_one_or_none()

    async def get_project(self, project_id: UUID) -> Optional[Project]:
        res = await self.session.execute(select(Project).where(Project.id == project_id))
        return res.scalar_one_or_none()

    # ─── task attachments (ORM) ───────────────────────────────────

    async def list_task_attachments(self, task_id: UUID) -> list[TaskAttachment]:
        res = await self.session.execute(
            select(TaskAttachment)
            .where(TaskAttachment.task_id == task_id)
            .order_by(TaskAttachment.created_at.desc())
        )
        return list(res.scalars().all())

    async def get_task_attachment(self, att_id: UUID) -> Optional[TaskAttachment]:
        res = await self.session.execute(
            select(TaskAttachment).where(TaskAttachment.id == att_id)
        )
        return res.scalar_one_or_none()

    def add(self, obj) -> None:
        self.session.add(obj)

    # ─── project attachments (raw SQL) ────────────────────────────

    async def insert_project_attachment(
        self, *,
        att_id: UUID, project_id: UUID, uploader_id: UUID,
        filename: str, key: str, mime: str, size_bytes: int,
        is_result_doc: bool, ts: datetime,
    ) -> None:
        await self.session.execute(text("""
            INSERT INTO project_attachments
              (id, project_id, uploader_id, filename, storage_key, mime_type,
               size_bytes, is_result_doc, created_at, updated_at)
            VALUES (:id, :pid, :u, :fn, :key, :mime, :sz, :res, :ts, :ts)
        """), {
            "id": att_id, "pid": project_id, "u": uploader_id,
            "fn": filename, "key": key, "mime": mime, "sz": size_bytes,
            "res": bool(is_result_doc), "ts": ts,
        })

    async def list_project_attachments(self, project_id: UUID):
        rows = await self.session.execute(text("""
            SELECT id::text, filename, mime_type, size_bytes, is_result_doc,
                   uploader_id::text, created_at
            FROM project_attachments
            WHERE project_id=:pid
            ORDER BY created_at DESC
        """), {"pid": project_id})
        return list(rows.all())

    async def get_project_attachment_for_download(self, att_id: UUID):
        return (await self.session.execute(text("""
            SELECT pa.project_id, pa.storage_key, pa.filename, pa.mime_type,
                   p.company_id
            FROM project_attachments pa
            JOIN projects p ON p.id = pa.project_id
            WHERE pa.id=:i
        """), {"i": att_id})).first()

    async def get_project_attachment_for_delete(self, att_id: UUID):
        return (await self.session.execute(text("""
            SELECT pa.uploader_id, pa.storage_key, p.company_id
            FROM project_attachments pa
            JOIN projects p ON p.id = pa.project_id
            WHERE pa.id=:i
        """), {"i": att_id})).first()

    async def delete_project_attachment(self, att_id: UUID) -> None:
        await self.session.execute(
            text("DELETE FROM project_attachments WHERE id=:i"),
            {"i": att_id},
        )

    # ─── company attachments (raw SQL) ────────────────────────────

    async def insert_company_attachment(
        self, *,
        att_id: UUID, company_id: UUID, uploader_id: UUID,
        category: Optional[str], title: str, description: Optional[str],
        filename: str, key: str, mime: str, size_bytes: int,
        year: Optional[int],
    ) -> None:
        await self.session.execute(text("""
            INSERT INTO company_attachments
              (id, company_id, uploader_id, category, title, description,
               filename, storage_key, mime_type, size_bytes, year)
            VALUES (:id, :co, :u, :cat, :title, :desc, :fn, :key, :mime, :sz, :yr)
        """), {
            "id": att_id, "co": company_id, "u": uploader_id, "cat": category,
            "title": title, "desc": description,
            "fn": filename, "key": key, "mime": mime,
            "sz": size_bytes, "yr": year,
        })

    async def list_company_attachments(
        self, company_id: UUID, *,
        category: Optional[str], year: Optional[int],
    ):
        q = ("SELECT id::text, filename, mime_type, size_bytes, "
             "uploader_id::text, created_at FROM company_attachments "
             "WHERE company_id=:co")
        params: dict = {"co": company_id}
        if category:
            q += " AND category=:cat"; params["cat"] = category
        if year is not None:
            q += " AND year=:yr"; params["yr"] = year
        q += " ORDER BY created_at DESC"
        return list((await self.session.execute(text(q), params)).all())

    async def get_company_attachment_for_download(self, att_id: UUID):
        return (await self.session.execute(text("""
            SELECT company_id, storage_key, filename, mime_type
            FROM company_attachments WHERE id=:i
        """), {"i": att_id})).first()

    async def get_company_attachment_for_delete(self, att_id: UUID):
        return (await self.session.execute(text("""
            SELECT company_id, uploader_id, storage_key
            FROM company_attachments WHERE id=:i
        """), {"i": att_id})).first()

    async def delete_company_attachment(self, att_id: UUID) -> None:
        await self.session.execute(
            text("DELETE FROM company_attachments WHERE id=:i"),
            {"i": att_id},
        )

    async def delete_task_attachment_row(self, att_id: UUID) -> None:
        await self.session.execute(
            text("DELETE FROM task_attachments WHERE id=:i"),
            {"i": att_id},
        )

    # ─── per-user access denial (Pack 150) ────────────────────────

    async def denied_attachment_ids(
        self, *, kind: str, user_id: UUID, attachment_ids: Optional[list] = None,
    ) -> set[str]:
        if attachment_ids is not None and not attachment_ids:
            return set()
        sql = ("SELECT attachment_id::text FROM attachment_access_denial "
               "WHERE kind = :k AND user_id = :u")
        params: dict = {"k": kind, "u": user_id}
        if attachment_ids is not None:
            sql += " AND attachment_id = ANY(:ids)"
            params["ids"] = list(attachment_ids)
        rows = (await self.session.execute(text(sql), params)).all()
        return {r[0] for r in rows}

    async def denied_counts(self, *, kind: str, attachment_ids: list) -> dict[str, int]:
        if not attachment_ids:
            return {}
        rows = (await self.session.execute(text("""
            SELECT attachment_id::text, COUNT(*)
            FROM attachment_access_denial
            WHERE kind = :k AND attachment_id = ANY(:ids)
            GROUP BY attachment_id
        """), {"k": kind, "ids": list(attachment_ids)})).all()
        return {r[0]: int(r[1]) for r in rows}

    async def list_denied_users(self, *, kind: str, att_id: UUID):
        return list((await self.session.execute(text("""
            SELECT u.id::text, u.email, u.full_name, aad.denied_at,
                   b.email AS by_email, aad.reason
            FROM attachment_access_denial aad
            JOIN users u ON u.id = aad.user_id
            LEFT JOIN users b ON b.id = aad.denied_by
            WHERE aad.kind = :k AND aad.attachment_id = :i
            ORDER BY aad.denied_at DESC
        """), {"k": kind, "i": att_id})).all())

    async def user_exists(self, user_id: UUID) -> bool:
        res = await self.session.execute(
            text("SELECT 1 FROM users WHERE id = :u"), {"u": user_id},
        )
        return bool(res.scalar())

    async def upsert_denial(
        self, *, kind: str, att_id: UUID, user_id: UUID,
        denied_by: UUID, reason: Optional[str],
    ) -> None:
        await self.session.execute(text("""
            INSERT INTO attachment_access_denial
              (kind, attachment_id, user_id, denied_by, reason)
            VALUES (:k, :a, :u, :by, :r)
            ON CONFLICT (kind, attachment_id, user_id) DO UPDATE
            SET denied_by = EXCLUDED.denied_by,
                denied_at = NOW(),
                reason    = EXCLUDED.reason
        """), {
            "k": kind, "a": att_id, "u": user_id,
            "by": denied_by, "r": reason,
        })

    async def delete_denial(
        self, *, kind: str, att_id: UUID, user_id: UUID,
    ) -> None:
        await self.session.execute(text("""
            DELETE FROM attachment_access_denial
            WHERE kind = :k AND attachment_id = :a AND user_id = :u
        """), {"k": kind, "a": att_id, "u": user_id})

    # ─── transaction helpers ──────────────────────────────────────

    async def flush(self) -> None:
        await self.session.flush()
