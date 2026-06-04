"""Tasks repository — queries для boards / tasks / task_history / task_comment."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board import Board
from app.models.company import Company
from app.models.project import Project
from app.models.task import Task, TaskComment
from app.models.user import User


class TasksRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def carry_over_sources(
        self, target_ids: Sequence[UUID]
    ) -> dict[UUID, int]:
        """Reverse carry-over map: {target_task_id → source portfolio_year}.

        A task T (earlier year) deferred to a later year stores linked_task_id
        pointing at the target U; here we find, for each U in `target_ids`, the
        year T lived in — so the target side can show a «← FYxx» badge without
        any stored reciprocal link."""
        ids = [tid for tid in target_ids if tid is not None]
        if not ids:
            return {}
        res = await self.session.execute(
            select(Task.linked_task_id, Task.portfolio_year).where(
                Task.linked_task_id.in_(ids),
                Task.linked_task_id.is_not(None),
                Task.portfolio_year.is_not(None),
            )
        )
        return {tgt: yr for tgt, yr in res.all() if tgt is not None}

    # ─── Boards ───────────────────────────────────────────────────

    async def list_boards(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
        sector: Optional[str] = None,
        company_id: Optional[UUID] = None,
        archived: bool = False,
        search: Optional[str] = None,
    ) -> list[tuple[Board, Optional[str], Optional[str]]]:
        q = (
            select(Board, Company.code, Company.name_short)
            .outerjoin(Company, Board.company_id == Company.id)
            .where(Board.is_archived == archived)
        )
        if scope_company_ids is not None:
            q = q.where(Board.company_id.in_(list(scope_company_ids)))
        if sector:
            q = q.where(Board.sector_code == sector.lower())
        if company_id:
            q = q.where(Board.company_id == company_id)
        if search:
            s = f"%{search.strip().lower()}%"
            q = q.where(func.lower(Board.name).like(s))
        q = q.order_by(Board.sort_order.asc(), Board.name.asc())
        rows = (await self.session.execute(q)).all()
        return [(r.Board, r.code, r.name_short) for r in rows]

    async def get_board_with_company(
        self, board_id: UUID,
    ) -> Optional[tuple[Board, Optional[str], Optional[str]]]:
        q = (
            select(Board, Company.code, Company.name_short)
            .outerjoin(Company, Board.company_id == Company.id)
            .where(Board.id == board_id)
        )
        row = (await self.session.execute(q)).first()
        if not row:
            return None
        return (row.Board, row.code, row.name_short)

    async def count_tasks_by_status_per_board(
        self, board_ids: Sequence[UUID],
    ) -> dict[UUID, dict[str, int]]:
        out: dict[UUID, dict[str, int]] = {bid: {} for bid in board_ids}
        if not board_ids:
            return out
        q = (
            select(Task.board_id, Task.status, func.count())
            .where(Task.board_id.in_(list(board_ids)), Task.is_archived.is_(False))
            .group_by(Task.board_id, Task.status)
        )
        for bid, st, cnt in (await self.session.execute(q)).all():
            out[bid][st] = cnt
        return out

    async def count_tasks_by_status_for_board(
        self, board_id: UUID,
    ) -> dict[str, int]:
        q = (
            select(Task.status, func.count())
            .where(Task.board_id == board_id, Task.is_archived.is_(False))
            .group_by(Task.status)
        )
        return dict((await self.session.execute(q)).all())

    async def list_board_tasks(
        self,
        board_id: UUID,
        *,
        portfolio_year: Optional[int] = None,
    ) -> list[Task]:
        q = (
            select(Task)
            .where(Task.board_id == board_id, Task.is_archived.is_(False))
        )
        if portfolio_year:
            q = q.where(Task.portfolio_year == portfolio_year)
        q = q.order_by(Task.priority.asc(), Task.due_date.asc().nulls_last(), Task.num.asc())
        return list((await self.session.execute(q)).scalars().all())

    # ─── Tasks queries ────────────────────────────────────────────

    async def list_tasks(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
        board_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
        status: Optional[str] = None,
        direction: Optional[str] = None,
        priority: Optional[str] = None,
        assignee_email: Optional[str] = None,
        portfolio_year: Optional[int] = None,
        only_overdue: bool = False,
        search: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[tuple[Task, Optional[str], Optional[str]]], int]:
        q = (
            select(Task, Board.name.label("board_name"), Company.code.label("company_code"))
            .outerjoin(Board, Task.board_id == Board.id)
            .outerjoin(Company, Task.company_id == Company.id)
            .where(Task.is_archived.is_(False))
        )
        if scope_company_ids is not None:
            q = q.where(Task.company_id.in_(list(scope_company_ids)))
        if board_id:
            q = q.where(Task.board_id == board_id)
        if company_id:
            q = q.where(Task.company_id == company_id)
        if company_code:
            q = q.where(Company.code == company_code)
        if status:
            q = q.where(Task.status == status)
        if direction:
            q = q.where(Task.extra["direction"].astext == direction)
        if priority:
            q = q.where(Task.priority == priority)
        if assignee_email:
            q = q.where(Task.assignee_email == assignee_email)
        if portfolio_year:
            q = q.where(Task.portfolio_year == portfolio_year)
        if only_overdue:
            q = q.where(
                Task.due_date.is_not(None),
                Task.status != "done",
                Task.due_date < date.today(),
            )
        if search:
            s = f"%{search.strip().lower()}%"
            q = q.where(or_(
                func.lower(Task.title).like(s),
                func.lower(Task.description).like(s),
            ))

        # count total before pagination
        cnt_q = select(func.count()).select_from(q.subquery())
        total = int((await self.session.execute(cnt_q)).scalar_one())

        sort_col = {
            "updated_at": Task.updated_at,
            "created_at": Task.created_at,
            "due_date": Task.due_date,
            "priority": Task.priority,
            "num": Task.num,
        }.get(sort_by, Task.updated_at)
        q = q.order_by(desc(sort_col) if sort_dir == "desc" else asc(sort_col))
        q = q.limit(limit).offset(offset)

        rows = (await self.session.execute(q)).all()
        return [(r.Task, r.board_name, r.company_code) for r in rows], total

    async def get_task_with_meta(
        self, task_id: UUID,
    ) -> Optional[tuple[Task, Optional[str], Optional[str]]]:
        q = (
            select(Task, Board.name.label("board_name"), Company.code.label("company_code"))
            .outerjoin(Board, Task.board_id == Board.id)
            .outerjoin(Company, Task.company_id == Company.id)
            .where(Task.id == task_id)
        )
        row = (await self.session.execute(q)).first()
        if not row:
            return None
        return (row.Task, row.board_name, row.company_code)

    async def get_task(self, task_id: UUID) -> Optional[Task]:
        res = await self.session.execute(select(Task).where(Task.id == task_id))
        return res.scalar_one_or_none()

    async def get_project(self, project_id: UUID) -> Optional[Project]:
        return await self.session.get(Project, project_id)

    async def board_exists(self, board_id: UUID) -> bool:
        res = await self.session.execute(select(Board.id).where(Board.id == board_id))
        return res.scalar_one_or_none() is not None

    async def get_board_name(self, board_id: UUID) -> Optional[str]:
        res = await self.session.execute(select(Board.name).where(Board.id == board_id))
        return res.scalar_one_or_none()

    async def get_company_code(self, company_id: UUID) -> Optional[str]:
        res = await self.session.execute(select(Company.code).where(Company.id == company_id))
        return res.scalar_one_or_none()

    # ─── Comments + history ──────────────────────────────────────

    async def list_recent_comments(
        self, task_id: UUID, limit: int = 100,
    ) -> list[TaskComment]:
        res = await self.session.execute(
            select(TaskComment)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.desc()).limit(limit)
        )
        return list(res.scalars().all())

    async def get_users_by_ids(self, ids: Sequence[UUID]) -> list[User]:
        if not ids:
            return []
        res = await self.session.execute(select(User).where(User.id.in_(list(ids))))
        return list(res.scalars().all())

    async def get_user_by_email(self, email: str) -> Optional[User]:
        res = await self.session.execute(select(User).where(User.email == email))
        return res.scalar_one_or_none()

    # ─── Mutations ────────────────────────────────────────────────

    def add(self, obj: Any) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj: Any) -> None:
        await self.session.refresh(obj)
