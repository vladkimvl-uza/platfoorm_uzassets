"""Data access for Executive Dashboard."""
from __future__ import annotations

from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company
from app.models.task import Task


class ExecDashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── companies ────────────────────────────────────────────────

    async def list_companies(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> list[Company]:
        cos_q = await self.session.execute(
            select(Company)
            .options(selectinload(Company.sector))
            .where(Company.is_archived.is_(False) if hasattr(Company, "is_archived") else True)
        )
        all_companies = list(cos_q.scalars().all())
        if scope_company_ids is not None:
            if not scope_company_ids:
                return []
            ids = set(scope_company_ids)
            all_companies = [co for co in all_companies if co.id in ids]
        return all_companies

    # ─── boards mapping ───────────────────────────────────────────

    async def boards_by_company(self) -> dict[UUID, UUID]:
        try:
            from app.models.board import Board
        except ImportError:
            return {}
        try:
            res = await self.session.execute(select(Board))
            return {
                b.company_id: b.id
                for b in res.scalars().all()
                if getattr(b, "company_id", None)
            }
        except Exception:
            return {}

    # ─── tasks ────────────────────────────────────────────────────

    async def list_tasks_for_year(self, year: int) -> list[Task]:
        filters = [Task.portfolio_year == year]
        if hasattr(Task, "is_archived"):
            filters.append(Task.is_archived.is_(False))
        res = await self.session.execute(select(Task).where(*filters))
        return list(res.scalars().all())

    # ─── projects (optional model) ────────────────────────────────

    async def list_projects_for_year(self, year: int) -> list[Any]:
        try:
            from app.models.project import Project
        except ImportError:
            return []
        try:
            filters = []
            if hasattr(Project, "portfolio_year"):
                filters.append(Project.portfolio_year == year)
            if hasattr(Project, "is_archived"):
                filters.append(Project.is_archived.is_(False))
            stmt = select(Project).where(*filters) if filters else select(Project)
            res = await self.session.execute(stmt)
            return list(res.scalars().all())
        except Exception:
            return []

    # ─── agency ratings (multi-import) ────────────────────────────

    @staticmethod
    def _try_load_agency_rating_model():
        for module_name, class_name in [
            ("app.models.agency_rating", "AgencyRating"),
            ("app.models.rating", "AgencyRating"),
            ("app.models.rating", "Rating"),
            ("app.models.ratings", "AgencyRating"),
            ("app.models.ratings", "Rating"),
        ]:
            try:
                mod = __import__(module_name, fromlist=[class_name])
                return getattr(mod, class_name)
            except (ImportError, AttributeError):
                continue
        return None

    async def list_agency_ratings(self) -> list:
        model = self._try_load_agency_rating_model()
        if model is None:
            return []
        res = await self.session.execute(select(model))
        return list(res.scalars().all())

    # ─── directions (for build_directions_block) ──────────────────

    async def direction_id_to_code(self) -> dict[UUID, str]:
        try:
            from app.models.company import Direction
        except ImportError:
            return {}
        try:
            res = await self.session.execute(select(Direction.id, Direction.code))
            return {did: dcode for did, dcode in res.all()}
        except Exception:
            return {}

    # ─── available years ──────────────────────────────────────────

    async def available_task_years(self) -> list[int]:
        res = await self.session.execute(
            select(distinct(Task.portfolio_year))
            .where(Task.portfolio_year.isnot(None))
        )
        return sorted(
            [int(y) for y in res.scalars().all() if y is not None],
            reverse=True,
        )
