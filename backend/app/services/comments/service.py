"""Use cases for Project + Task comments — generic over kind."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from app.models.project import ProjectComment
from app.models.task import TaskComment
from app.uow.ports import UnitOfWorkABC


def is_admin(user) -> bool:
    if getattr(user, "is_owner", False) or getattr(user, "is_admin", False):
        return True
    roles = getattr(user, "roles", None) or []
    if isinstance(roles, list):
        admin_roles = {"admin", "ROLE_ADMIN", "ROLE_OWNER", "owner"}
        return any(r in admin_roles for r in roles)
    return False


class CommentsService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── list ─────────────────────────────────────────────────────

    async def list_comments(self, kind: str, parent_id: UUID) -> list[tuple]:
        """Returns [(comment, author_name, author_email), ...]"""
        async with self.uow:
            parent = await self.uow.comments.get_parent(kind, parent_id)
            if not parent:
                raise HTTPException(404, f"{kind.title()} not found")
            rows = await self.uow.comments.list_for_parent(kind, parent_id)
            out = []
            for c in rows:
                u = await self.uow.comments.get_user(c.author_id) if c.author_id else None
                name = (
                    (getattr(u, "full_name", None)
                     or getattr(u, "name", None)
                     or getattr(u, "email", None))
                    if u else None
                )
                email = getattr(u, "email", None) if u else None
                out.append((c, name, email))
        return out

    # ─── create ───────────────────────────────────────────────────

    async def create_comment(
        self,
        kind: str,
        parent_id: UUID,
        *,
        body: str,
        author_id: UUID,
    ) -> dict:
        """Returns dict with: comment, parent, company_name, author_name, author_email."""
        async with self.uow:
            parent = await self.uow.comments.get_parent(kind, parent_id)
            if not parent or getattr(parent, "is_archived", False):
                raise HTTPException(404, f"{kind.title()} not found")

            comment_model = ProjectComment if kind == "project" else TaskComment
            kwargs = {
                "author_id": author_id, "body": body, "is_edited": False,
            }
            if kind == "project":
                kwargs["project_id"] = parent_id
            else:
                kwargs["task_id"] = parent_id
            c = comment_model(**kwargs)
            self.uow.comments.add(c)
            await self.uow.comments.flush()

            company_name = None
            if getattr(parent, "company_id", None):
                co = await self.uow.comments.get_company(parent.company_id)
                if co:
                    company_name = co.name_short or co.name_ru

            await self.uow.comments.refresh(c)
            u = await self.uow.comments.get_user(c.author_id) if c.author_id else None
            name = (
                (getattr(u, "full_name", None)
                 or getattr(u, "name", None)
                 or getattr(u, "email", None))
                if u else None
            )
            email = getattr(u, "email", None) if u else None

            return {
                "comment": c, "parent": parent,
                "company_name": company_name,
                "author_name": name, "author_email": email,
            }

    # ─── update ───────────────────────────────────────────────────

    async def update_comment(
        self,
        kind: str,
        comment_id: UUID,
        *,
        body: str,
        actor,
    ) -> dict:
        async with self.uow:
            c = await self.uow.comments.get_comment(kind, comment_id)
            if not c:
                raise HTTPException(404, "Comment not found")
            if c.author_id != actor.id and not is_admin(actor):
                raise HTTPException(403, "Only author or admin")
            c.body = body
            c.is_edited = True
            parent_id = c.project_id if kind == "project" else c.task_id
            parent = await self.uow.comments.get_parent(kind, parent_id)
            await self.uow.comments.flush()
            await self.uow.comments.refresh(c)
            u = await self.uow.comments.get_user(c.author_id) if c.author_id else None
            name = (
                (getattr(u, "full_name", None)
                 or getattr(u, "name", None)
                 or getattr(u, "email", None))
                if u else None
            )
            email = getattr(u, "email", None) if u else None
            return {
                "comment": c, "parent": parent, "parent_id": parent_id,
                "author_name": name, "author_email": email,
            }

    # ─── delete ───────────────────────────────────────────────────

    async def delete_comment(
        self,
        kind: str,
        comment_id: UUID,
        *,
        actor,
    ) -> dict:
        async with self.uow:
            c = await self.uow.comments.get_comment(kind, comment_id)
            if not c:
                raise HTTPException(404, "Comment not found")
            if c.author_id != actor.id and not is_admin(actor):
                raise HTTPException(403, "Only author or admin")
            parent_id = c.project_id if kind == "project" else c.task_id
            body_snap = c.body
            parent = await self.uow.comments.get_parent(kind, parent_id)
            parent_title = (getattr(parent, "title", "") or "") if parent else ""
            await self.uow.comments.delete(c)
            await self.uow.comments.flush()
            return {
                "parent_id": parent_id,
                "parent_title": parent_title or "(без названия)",
                "body_snap": body_snap,
            }
