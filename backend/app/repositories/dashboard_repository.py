"""Data access for Shareholder Dashboard + drill-down endpoints."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency_rating import AgencyRating
from app.models.board import Board
from app.models.company import Company, Direction, Sector
from app.models.project import Project
from app.models.task import Task


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── years ────────────────────────────────────────────────────

    async def available_task_years(self) -> list[int]:
        res = await self.session.execute(
            select(Task.portfolio_year).distinct()
            .where(Task.portfolio_year.is_not(None))
        )
        return sorted({y for (y,) in res.all() if y}, reverse=True)

    # ─── projects + tasks (filtered) ──────────────────────────────

    async def filtered_projects_shareholder(
        self,
        *,
        year: Optional[int],
        allowed_board_ids: Optional[set],
        allowed_dir_ids: Optional[set],
    ):
        # 05-25: also select extra so service can fallback to
        # extra->>'direction' when direction_id is NULL (legacy rows imported
        # before direction_id existed).
        q = (select(
            Project.id, Project.status, Project.due_date, Project.direction_id,
            Project.board_id, Project.company_id, Project.linked_year,
            Project.linked_project_id, Project.portfolio_year,
            Project.extra,
        ).where(Project.is_archived == False))  # noqa: E712
        if year:
            q = q.where(Project.portfolio_year == year)
        if allowed_board_ids is not None:
            q = q.where(Project.board_id.in_(allowed_board_ids))
        if allowed_dir_ids is not None:
            q = q.where(Project.direction_id.in_(allowed_dir_ids))
        return list((await self.session.execute(q)).all())

    async def filtered_tasks_shareholder(
        self,
        *,
        year: Optional[int],
        allowed_board_ids: Optional[set],
        allowed_dir_ids: Optional[set],
    ):
        q = (select(
            Task.id, Task.status, Task.due_date, Task.direction_id,
            Task.board_id, Task.company_id, Task.linked_year, Task.linked_task_id,
            Task.portfolio_year,
            Task.extra,
        ).where(Task.is_archived == False))  # noqa: E712
        if year:
            q = q.where(Task.portfolio_year == year)
        if allowed_board_ids is not None:
            q = q.where(Task.board_id.in_(allowed_board_ids))
        if allowed_dir_ids is not None:
            q = q.where(Task.direction_id.in_(allowed_dir_ids))
        return list((await self.session.execute(q)).all())

    # ─── projects + tasks (with full fields for drill-downs) ──────

    async def filtered_projects_drill(
        self,
        *,
        year: Optional[int],
        allowed_board_ids: Optional[set],
        allowed_dir_ids: Optional[set],
    ):
        q = (select(
            Project.id, Project.num, Project.title, Project.status, Project.priority,
            Project.due_date, Project.linked_year, Project.linked_project_id,
            Project.portfolio_year,
            Project.progress_percent, Project.assignee_name, Project.assignee_email,
            Project.board_id, Project.company_id, Project.direction_id,
        ).where(Project.is_archived == False))  # noqa: E712
        if year:
            q = q.where(Project.portfolio_year == year)
        if allowed_board_ids is not None:
            q = q.where(Project.board_id.in_(allowed_board_ids))
        if allowed_dir_ids is not None:
            q = q.where(Project.direction_id.in_(allowed_dir_ids))
        return list((await self.session.execute(q)).all())

    async def filtered_tasks_drill(
        self,
        *,
        year: Optional[int],
        allowed_board_ids: Optional[set],
        allowed_dir_ids: Optional[set],
    ):
        q = (select(
            Task.id, Task.num, Task.title, Task.status, Task.priority,
            Task.due_date, Task.linked_year, Task.linked_task_id,
            Task.portfolio_year,
            Task.progress_percent, Task.assignee_name, Task.assignee_email,
            Task.board_id, Task.company_id, Task.direction_id, Task.extra,
        ).where(Task.is_archived == False))  # noqa: E712
        if year:
            q = q.where(Task.portfolio_year == year)
        if allowed_board_ids is not None:
            q = q.where(Task.board_id.in_(allowed_board_ids))
        if allowed_dir_ids is not None:
            q = q.where(Task.direction_id.in_(allowed_dir_ids))
        return list((await self.session.execute(q)).all())

    # ─── filter helpers (resolve codes → ids) ─────────────────────

    async def resolve_company_ids(
        self,
        *,
        sector_code: Optional[str],
        company_code: Optional[str],
    ) -> Optional[set]:
        if not sector_code and not company_code:
            return None
        q = select(Company.id).outerjoin(Sector, Sector.id == Company.sector_id)
        if sector_code:
            q = q.where(Sector.code == sector_code)
        if company_code:
            q = q.where(Company.code == company_code)
        rows = (await self.session.execute(q)).all()
        return {r[0] for r in rows} or {None}

    async def resolve_board_ids_for_companies(self, company_ids: set) -> set:
        if not company_ids:
            return {None}
        rows = (await self.session.execute(
            select(Board.id).where(Board.company_id.in_(company_ids))
        )).all()
        return {r[0] for r in rows} or {None}

    async def resolve_direction_ids(self, direction_code: str) -> set:
        rows = (await self.session.execute(
            select(Direction.id).where(Direction.code == direction_code)
        )).all()
        return {r[0] for r in rows} or {None}

    # ─── lookups ──────────────────────────────────────────────────

    async def board_to_company_map(self) -> dict:
        rows = (await self.session.execute(
            select(Board.id, Board.company_id)
        )).all()
        return {bid: cid for bid, cid in rows}

    async def inactive_company_ids(self) -> set:
        """ID деактивированных компаний (is_active=false). Их данные не должны
        попадать в дашборды/сводки — деактивация = скрыть везде."""
        rows = (await self.session.execute(
            select(Company.id).where(Company.is_active.is_(False))
        )).all()
        return {cid for (cid,) in rows}

    async def boards_with_names_map(self) -> dict[Any, dict]:
        rows = (await self.session.execute(
            select(Board.id, Board.name, Board.company_id)
        )).all()
        return {bid: {"name": name, "company_id": cid} for bid, name, cid in rows}

    async def companies_meta(self) -> dict:
        rows = (await self.session.execute(
            select(Company.id, Company.code, Company.name_short,
                   Company.name_ru, Sector.code)
            .outerjoin(Sector, Sector.id == Company.sector_id)
        )).all()
        return {
            cid: {"id": cid, "code": code, "name_short": ns,
                  "name_ru": nr, "sector": sec or "other"}
            for cid, code, ns, nr, sec in rows
        }

    async def direction_id_to_code(self) -> dict:
        rows = (await self.session.execute(
            select(Direction.id, Direction.code)
        )).all()
        return {did: dcode for did, dcode in rows}

    async def get_company_by_code(self, company_code: str):
        return (await self.session.execute(
            select(
                Company.id, Company.code, Company.name_short,
                Company.name_ru, Sector.code,
            )
            .outerjoin(Sector, Sector.id == Company.sector_id)
            .where(Company.code == company_code)
        )).first()

    async def board_ids_for_company(self, company_id: UUID) -> set:
        rows = (await self.session.execute(
            select(Board.id).where(Board.company_id == company_id)
        )).all()
        return {r[0] for r in rows}

    # ─── ratings ──────────────────────────────────────────────────

    async def list_agency_ratings_for_dashboard(self):
        res = await self.session.execute(
            select(AgencyRating.company_id, AgencyRating.agency,
                   AgencyRating.rating, AgencyRating.score,
                   AgencyRating.rating_date, AgencyRating.is_esg)
            .order_by(AgencyRating.rating_date.desc().nullslast())
        )
        return list(res.all())
