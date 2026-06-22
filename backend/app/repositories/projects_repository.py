"""Data access for Projects domain."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board import Board
from app.models.company import Company
from app.models.project import Project, ProjectComment
from app.models.task import Task
from app.models.user import User


class ProjectsRepository:
    """All SQL queries for Projects + child Task aggregates + comments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def carry_over_sources(
        self, target_ids: Sequence[UUID]
    ) -> dict[UUID, int]:
        """Reverse carry-over map: {target_project_id → source portfolio_year}."""
        ids = [pid for pid in target_ids if pid is not None]
        if not ids:
            return {}
        res = await self.session.execute(
            select(Project.linked_project_id, Project.portfolio_year).where(
                Project.linked_project_id.in_(ids),
                Project.linked_project_id.is_not(None),
                Project.portfolio_year.is_not(None),
            )
        )
        return {tgt: yr for tgt, yr in res.all() if tgt is not None}

    # ─── single object lookups ────────────────────────────────────

    async def get(self, project_id: UUID) -> Optional[Project]:
        res = await self.session.execute(select(Project).where(Project.id == project_id))
        return res.scalar_one_or_none()

    async def get_with_joined(self, project_id: UUID):
        q = (select(Project,
                    Board.name.label("board_name"),
                    Company.code.label("company_code"),
                    Company.name_short.label("company_name"))
             .outerjoin(Board, Project.board_id == Board.id)
             .outerjoin(Company, Project.company_id == Company.id)
             .where(Project.id == project_id))
        return (await self.session.execute(q)).first()

    async def get_company_id(self, project_id: UUID) -> Optional[UUID]:
        res = await self.session.execute(
            select(Project.company_id).where(Project.id == project_id)
        )
        return res.scalar_one_or_none()

    async def get_by_id(self, project_id: UUID) -> Optional[Project]:
        return await self.session.get(Project, project_id)

    # ─── list / filtering ─────────────────────────────────────────

    async def list_projects(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
        portfolio_year: Optional[int] = None,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
        board_id: Optional[UUID] = None,
        status: Optional[str] = None,
        direction_id: Optional[Any] = None,
        priority: Optional[str] = None,
        assignee_email: Optional[str] = None,
        only_overdue: bool = False,
        has_economic_effect: bool = False,
        search: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list, int]:
        q = (select(Project,
                    Board.name.label("board_name"),
                    Company.code.label("company_code"),
                    Company.name_short.label("company_name"))
             .outerjoin(Board, Project.board_id == Board.id)
             .outerjoin(Company, Project.company_id == Company.id)
             .where(Project.is_archived.is_(False)))

        if scope_company_ids is not None:
            q = q.where(Project.company_id.in_(scope_company_ids))
        if portfolio_year:
            q = q.where(Project.portfolio_year == portfolio_year)
        if company_id:
            q = q.where(Project.company_id == company_id)
        if company_code:
            q = q.where(func.lower(Company.code) == company_code.lower())
        if board_id:
            q = q.where(Project.board_id == board_id)
        if status == "deferred":
            q = q.where(Project.linked_year.is_not(None))
        elif status:
            q = q.where(Project.status == status)
        if direction_id is not None:
            q = q.where(Project.direction_id == direction_id)
        if priority:
            q = q.where(Project.priority == priority)
        if assignee_email:
            q = q.where(func.lower(Project.assignee_email) == assignee_email.lower())
        if only_overdue:
            q = q.where(Project.due_date < date.today(), Project.status != "done")
        if has_economic_effect:
            ee_key = Project.extra["economicEffect"]
            q = q.where(
                Project.extra.is_not(None),
                ee_key.is_not(None),
                or_(
                    ee_key["plannedValue"].as_float() > 0,
                    ee_key["realizedValue"].as_float() > 0,
                ),
            )
        if search:
            s = f"%{search.strip().lower()}%"
            q = q.where(or_(
                func.lower(Project.title).like(s),
                func.lower(Project.num).like(s),
                func.lower(Project.assignee_name).like(s),
                func.lower(Project.assignee_email).like(s),
            ))

        total = (await self.session.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        sort_col = {
            "updated_at": Project.updated_at,
            "created_at": Project.created_at,
            "due_date":   Project.due_date,
            "priority":   Project.priority,
            "num":        Project.num,
            "title":      Project.title,
        }.get(sort_by, Project.updated_at)
        q = q.order_by(
            asc(sort_col).nulls_last() if sort_dir == "asc"
            else desc(sort_col).nulls_last()
        )
        q = q.limit(limit).offset(offset)
        rows = (await self.session.execute(q)).all()
        return rows, total

    # ─── child tasks aggregates ───────────────────────────────────

    async def child_task_counts_bulk(self, project_ids: Sequence[UUID]) -> dict:
        """Return {pid: {'total': N, 'done': M}} for given project_ids.

        Прогресс проекта = среднее по задачам: задача «Завершено» → 1, остальные
        статусы → 0 (в счёт не идут). monthly/ongoing исключаются полностью
        (бессрочная работа без точки завершения); quarterly засчитывается как
        done только если закрыты все 4 квартала. Зеркалит frontend
        utils/progress.ts → taskWeight()/computeProgress() (единый источник правды).
        """
        out = {pid: {"total": 0, "done": 0, "sum": 0.0} for pid in project_ids}
        if not project_ids:
            return out
        from app.core.progress import task_weight
        q = (select(Task.project_id, Task.status, Task.extra)
             .where(Task.project_id.in_(project_ids),
                    Task.is_archived.is_(False)))
        for pid, st, extra in (await self.session.execute(q)).all():
            if pid not in out:
                continue
            w = task_weight(st, extra)
            if w is None:
                continue  # monthly/ongoing — в счёт не идут
            out[pid]["total"] += 1
            out[pid]["sum"] += w               # дробный вес статуса
            if w >= 1.0:
                out[pid]["done"] += 1          # полностью завершённые
        return out

    async def child_task_counts(self, project_id: UUID) -> dict[str, int]:
        cnt_q = (select(Task.status, func.count())
                 .where(Task.project_id == project_id,
                        Task.is_archived.is_(False))
                 .group_by(Task.status))
        return dict((await self.session.execute(cnt_q)).all())

    async def list_child_tasks(self, project_id: UUID):
        q = (select(Task, Board.name.label("board_name"),
                    Company.code.label("company_code"))
             .outerjoin(Board, Task.board_id == Board.id)
             .outerjoin(Company, Task.company_id == Company.id)
             .where(Task.project_id == project_id, Task.is_archived.is_(False))
             .order_by(Task.priority.asc(), Task.due_date.asc().nulls_last()))
        return (await self.session.execute(q)).all()

    # ─── facets ───────────────────────────────────────────────────

    async def facets_status_priority(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
        portfolio_year: Optional[int] = None,
        company_id: Optional[UUID] = None,
        board_id: Optional[UUID] = None,
    ):
        q = (select(Project.status, Project.priority)
             .where(Project.is_archived.is_(False)))
        if scope_company_ids is not None:
            q = q.where(Project.company_id.in_(scope_company_ids))
        if portfolio_year:
            q = q.where(Project.portfolio_year == portfolio_year)
        if company_id:
            q = q.where(Project.company_id == company_id)
        if board_id:
            q = q.where(Project.board_id == board_id)
        return (await self.session.execute(q)).all()

    async def count_deferred(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
        portfolio_year: Optional[int] = None,
        company_id: Optional[UUID] = None,
        board_id: Optional[UUID] = None,
    ) -> int:
        q = (select(func.count()).select_from(Project)
             .where(Project.is_archived.is_(False),
                    Project.linked_year.is_not(None)))
        if scope_company_ids is not None:
            q = q.where(Project.company_id.in_(scope_company_ids))
        if portfolio_year:
            q = q.where(Project.portfolio_year == portfolio_year)
        if company_id:
            q = q.where(Project.company_id == company_id)
        if board_id:
            q = q.where(Project.board_id == board_id)
        return (await self.session.execute(q)).scalar() or 0

    async def available_years(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]] = None,
    ) -> list[int]:
        q = (select(Project.portfolio_year, func.count())
             .where(Project.portfolio_year.is_not(None),
                    Project.is_archived.is_(False)))
        if scope_company_ids is not None:
            q = q.where(Project.company_id.in_(scope_company_ids))
        q = q.group_by(Project.portfolio_year).order_by(Project.portfolio_year.desc())
        return [y for y, _ in (await self.session.execute(q)).all()]

    # ─── direction lookups ────────────────────────────────────────

    async def get_direction_id_by_code(self, code: str):
        from app.models.company import Direction as _DirM
        res = await self.session.execute(
            select(_DirM.id).where(_DirM.code == code)
        )
        return res.scalar_one_or_none()

    # ─── hydration helpers ────────────────────────────────────────

    async def get_board_name(self, board_id: UUID) -> Optional[str]:
        return (await self.session.execute(
            select(Board.name).where(Board.id == board_id)
        )).scalar_one_or_none()

    async def get_company_short(self, company_id: UUID):
        return (await self.session.execute(
            select(Company.code, Company.name_short).where(Company.id == company_id)
        )).first()

    # ─── comments ─────────────────────────────────────────────────

    async def list_comments(self, project_id: UUID, limit: int = 100):
        rows = await self.session.execute(
            select(ProjectComment)
            .where(ProjectComment.project_id == project_id)
            .order_by(ProjectComment.created_at.desc())
            .limit(limit)
        )
        return rows.scalars().all()

    async def get_users_by_ids(self, user_ids: Sequence[UUID]):
        if not user_ids:
            return []
        rows = await self.session.execute(
            select(User).where(User.id.in_(user_ids))
        )
        return rows.scalars().all()

    # ─── mutation helpers ─────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
