"""Data access for Project/Task comments."""
from __future__ import annotations

from typing import Optional, Union
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.project import Project, ProjectComment
from app.models.status_update import StatusUpdate
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

    # ─── List-row enrichment (current_health / unread comments) ───────

    async def latest_status_health_map(
        self, entity_type: str, ids: list[UUID]
    ) -> dict[str, Optional[str]]:
        """{entity_id(str) → health последней записи status_update}."""
        if not ids:
            return {}
        ids_str = [str(i) for i in ids]
        q = (
            select(StatusUpdate.entity_id, StatusUpdate.health)
            .where(
                StatusUpdate.entity_type == entity_type,
                StatusUpdate.entity_id.in_(ids_str),
            )
            .distinct(StatusUpdate.entity_id)
            .order_by(StatusUpdate.entity_id, StatusUpdate.created_at.desc())
        )
        return {r[0]: r[1] for r in (await self.session.execute(q)).all()}

    async def unread_comment_map(
        self, user_id: UUID, kind: str, ids: list[UUID]
    ) -> dict[str, bool]:
        """{entity_id(str) → есть ли непрочитанный юзером комментарий от другого}."""
        if not ids or not user_id:
            return {}
        _parent, comment_model, fk_name = _model_for(kind)
        fk = getattr(comment_model, fk_name)
        # последний комментарий НЕ от текущего юзера на сущность
        q = (
            select(fk, func.max(comment_model.created_at))
            .where(
                fk.in_(ids),
                or_(comment_model.author_id.is_(None), comment_model.author_id != user_id),
            )
            .group_by(fk)
        )
        last_other = {str(r[0]): r[1] for r in (await self.session.execute(q)).all()}
        if not last_other:
            return {}
        ids_str = list(last_other.keys())
        reads = {
            r[0]: r[1]
            for r in (
                await self.session.execute(
                    text(
                        "SELECT entity_id, last_read_at FROM comment_read "
                        "WHERE user_id = :uid AND entity_type = :et AND entity_id = ANY(:ids)"
                    ),
                    {"uid": user_id, "et": kind, "ids": ids_str},
                )
            ).all()
        }
        out: dict[str, bool] = {}
        for eid, last_c in last_other.items():
            rt = reads.get(eid)
            out[eid] = last_c is not None and (rt is None or last_c > rt)
        return out

    async def mark_read(self, user_id: UUID, kind: str, entity_id: UUID) -> None:
        """Отметить комментарии сущности прочитанными текущим юзером (upsert)."""
        await self.session.execute(
            text(
                "INSERT INTO comment_read (user_id, entity_type, entity_id, last_read_at) "
                "VALUES (:uid, :et, :eid, now()) "
                "ON CONFLICT (user_id, entity_type, entity_id) "
                "DO UPDATE SET last_read_at = now()"
            ),
            {"uid": user_id, "et": kind, "eid": str(entity_id)},
        )
