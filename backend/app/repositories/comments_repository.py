"""Data access for Project/Task comments."""
from __future__ import annotations

from typing import Optional, Union
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.project import Project, ProjectComment
from app.models.task import Task, TaskComment
from app.models.user import User


CommentT = Union[ProjectComment, TaskComment]


def _model_for(kind: str):
    """kind = 'project' | 'task' → (parent_model, comment_model, fk_attr)."""
    if kind == "project":
        return Project, ProjectComment, "project_id"
    if kind == "task":
        return Task, TaskComment, "task_id"
    raise ValueError(f"Unknown kind: {kind}")


class CommentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_parent(self, kind: str, parent_id: UUID):
        parent_model, _comment_model, _fk = _model_for(kind)
        return await self.session.get(parent_model, parent_id)

    async def get_comment(self, kind: str, comment_id: UUID) -> Optional[CommentT]:
        _parent, comment_model, _fk = _model_for(kind)
        return await self.session.get(comment_model, comment_id)

    async def list_for_parent(self, kind: str, parent_id: UUID, *, limit: int = 200):
        _parent, comment_model, fk = _model_for(kind)
        res = await self.session.execute(
            select(comment_model)
            .where(getattr(comment_model, fk) == parent_id)
            .order_by(comment_model.created_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())

    async def get_user(self, user_id: UUID) -> Optional[User]:
        if not user_id:
            return None
        return await self.session.get(User, user_id)

    async def get_company(self, company_id: UUID) -> Optional[Company]:
        if not company_id:
            return None
        return await self.session.get(Company, company_id)

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
