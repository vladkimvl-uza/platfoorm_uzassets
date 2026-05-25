"""Read-only use cases for Projects domain."""
from __future__ import annotations

from datetime import date
from typing import Optional, Sequence
from uuid import UUID

from fastapi import HTTPException, status as http_status

from app.schemas.project import ProjectDetail, ProjectListResponse
from app.schemas.task import TaskBrief
from app.services.projects._helpers import project_to_brief, serialize_comment
from app.uow.ports import UnitOfWorkABC


class ProjectsQueryService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def list_projects(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
        portfolio_year: Optional[int],
        company_id: Optional[UUID],
        company_code: Optional[str],
        board_id: Optional[UUID],
        status: Optional[str],
        direction: Optional[str],
        priority: Optional[str],
        assignee_email: Optional[str],
        only_overdue: bool,
        has_economic_effect: bool,
        search: Optional[str],
        sort_by: str,
        sort_dir: str,
        limit: int,
        offset: int,
    ) -> ProjectListResponse:
        # Empty scope shortcut
        if scope_company_ids is not None and len(scope_company_ids) == 0:
            return ProjectListResponse(items=[], total=0)

        async with self.uow:
            # Resolve direction code → id
            direction_id = None
            if direction:
                direction_id = await self.uow.projects.get_direction_id_by_code(direction)

            rows, total = await self.uow.projects.list_projects(
                scope_company_ids=scope_company_ids,
                portfolio_year=portfolio_year,
                company_id=company_id,
                company_code=company_code,
                board_id=board_id,
                status=status,
                direction_id=direction_id,
                priority=priority,
                assignee_email=assignee_email,
                only_overdue=only_overdue,
                has_economic_effect=has_economic_effect,
                search=search,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            )

            project_ids = [r.Project.id for r in rows]
            child_counts = await self.uow.projects.child_task_counts_bulk(project_ids)

            items = [
                project_to_brief(
                    r.Project, r.board_name, r.company_code, r.company_name,
                    tasks_total=child_counts.get(r.Project.id, {}).get("total", 0),
                    tasks_done=child_counts.get(r.Project.id, {}).get("done", 0),
                )
                for r in rows
            ]

            # Facets
            facet_rows = await self.uow.projects.facets_status_priority(
                scope_company_ids=scope_company_ids,
                portfolio_year=portfolio_year,
                company_id=company_id,
                board_id=board_id,
            )
            by_status: dict[str, int] = {}
            by_priority: dict[str, int] = {}
            for st, pr in facet_rows:
                by_status[st] = by_status.get(st, 0) + 1
                by_priority[pr] = by_priority.get(pr, 0) + 1

            by_status['deferred'] = await self.uow.projects.count_deferred(
                scope_company_ids=scope_company_ids,
                portfolio_year=portfolio_year,
                company_id=company_id,
                board_id=board_id,
            )

            available_years = await self.uow.projects.available_years(
                scope_company_ids=scope_company_ids,
            )

        return ProjectListResponse(
            items=items, total=total,
            by_status=by_status, by_priority=by_priority,
            available_years=available_years,
        )

    async def get_project(
        self,
        project_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ProjectDetail:
        async with self.uow:
            row = await self.uow.projects.get_with_joined(project_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")

            p = row.Project
            if scope_company_ids is not None:
                if p.company_id is None or p.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")

            counts = await self.uow.projects.child_task_counts(p.id)
            tasks_total = sum(counts.values())
            tasks_done = counts.get("done", 0)

            base = project_to_brief(
                p, row.board_name, row.company_code, row.company_name,
                tasks_total=tasks_total, tasks_done=tasks_done,
            )
            extra = p.extra or {}

            cmt_objs = await self.uow.projects.list_comments(p.id)
            author_ids = list({c.author_id for c in cmt_objs if c.author_id})
            users = await self.uow.projects.get_users_by_ids(author_ids)
            author_map = {
                u.id: (
                    getattr(u, "full_name", None) or getattr(u, "name", None) or getattr(u, "email", None),
                    getattr(u, "email", None),
                )
                for u in users
            }
            comments_list = [
                serialize_comment(c, *author_map.get(c.author_id, (None, None)))
                for c in cmt_objs
            ]

        return ProjectDetail(
            **base.model_dump(),
            description=p.description,
            scope=extra.get("scope"),
            consultants=extra.get("consultants", []) or [],
            extra=extra,
            legacy_id=p.legacy_id,
            creator_id=p.creator_id,
            start_date=p.start_date,
            completed_at=p.completed_at,
            consultant_comment=extra.get("consultant_comment"),
            economic_effect=extra.get("economic_effect")
            if isinstance(extra.get("economic_effect"), dict) else None,
            comments=comments_list,
        )

    async def get_project_tasks(
        self,
        project_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> list[TaskBrief]:
        async with self.uow:
            proj_co = await self.uow.projects.get_company_id(project_id)
            if proj_co is None:
                if scope_company_ids is not None:
                    raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
            else:
                if scope_company_ids is not None and proj_co not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")

            rows = await self.uow.projects.list_child_tasks(project_id)

        out: list[TaskBrief] = []
        for r in rows:
            t = r.Task
            is_overdue = bool(t.due_date and t.status != "done" and t.due_date < date.today())
            out.append(TaskBrief(
                id=t.id, num=t.num, title=t.title,
                status=t.status, priority=t.priority,
                board_id=t.board_id, board_name=r.board_name,
                company_id=t.company_id, company_code=r.company_code,
                assignee_email=t.assignee_email, assignee_name=t.assignee_name,
                assignee_id=t.assignee_id,
                due_date=t.due_date, portfolio_year=t.portfolio_year,
                is_project=False,
                progress_percent=t.progress_percent,
                is_overdue=is_overdue, tags=t.tags,
                created_at=t.created_at, updated_at=t.updated_at,
            ))
        return out
