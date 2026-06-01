"""Tasks query service — read-only use-cases для boards + tasks."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.schemas.task import (
    BoardBrief,
    BoardKanban,
    BoardListResponse,
    KanbanColumn,
    TaskBrief,
    TaskDetail,
    TaskListResponse,
)
from app.services.tasks._constants import STATUS_META, enrich_direction_meta
from app.services.tasks._helpers import task_to_brief
from app.uow.ports import UnitOfWorkABC


class TasksQueryService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── Boards ───────────────────────────────────────────────────

    async def list_boards(
        self,
        *,
        scope_company_ids: Optional[list[UUID]] = None,
        sector: Optional[str] = None,
        company_id: Optional[UUID] = None,
        archived: bool = False,
        search: Optional[str] = None,
    ) -> BoardListResponse:
        async with self.uow:
            # Empty scope → empty result без queries
            if scope_company_ids is not None and len(scope_company_ids) == 0:
                return BoardListResponse(items=[], total=0)

            rows = await self.uow.tasks.list_boards(
                scope_company_ids=scope_company_ids,
                sector=sector,
                company_id=company_id,
                archived=archived,
                search=search,
            )
            board_ids = [r[0].id for r in rows]
            counts = await self.uow.tasks.count_tasks_by_status_per_board(board_ids)

        items = []
        for b, co_code, co_name in rows:
            cnts = counts.get(b.id, {})
            items.append(BoardBrief(
                id=b.id, name=b.name, description=b.description,
                color_hex=b.color_hex, sector_code=b.sector_code,
                company_id=b.company_id, company_code=co_code, company_name=co_name,
                is_archived=b.is_archived, sort_order=b.sort_order,
                tasks_total=sum(cnts.values()),
                tasks_by_status=cnts,
            ))
        return BoardListResponse(items=items, total=len(items))

    async def get_board(
        self,
        board_id: UUID,
        *,
        scope_company_ids: Optional[list[UUID]] = None,
    ) -> BoardBrief:
        async with self.uow:
            row = await self.uow.tasks.get_board_with_company(board_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Board not found")
            b, co_code, co_name = row

            if scope_company_ids is not None:
                if b.company_id is None or b.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this board")

            cnts = await self.uow.tasks.count_tasks_by_status_for_board(board_id)

        return BoardBrief(
            id=b.id, name=b.name, description=b.description,
            color_hex=b.color_hex, sector_code=b.sector_code,
            company_id=b.company_id, company_code=co_code, company_name=co_name,
            is_archived=b.is_archived, sort_order=b.sort_order,
            tasks_total=sum(cnts.values()),
            tasks_by_status=cnts,
        )

    async def get_board_kanban(
        self,
        board_id: UUID,
        *,
        scope_company_ids: Optional[list[UUID]] = None,
        portfolio_year: Optional[int] = None,
    ) -> BoardKanban:
        async with self.uow:
            row = await self.uow.tasks.get_board_with_company(board_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Board not found")
            b, co_code, co_name = row

            if scope_company_ids is not None:
                if b.company_id is None or b.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this board")

            tasks = await self.uow.tasks.list_board_tasks(board_id, portfolio_year=portfolio_year)

        by_status: dict[str, list[TaskBrief]] = {s: [] for s, _, _ in STATUS_META}
        for t in tasks:
            if t.status in by_status:
                by_status[t.status].append(task_to_brief(t, b.name, co_code))

        columns = [
            KanbanColumn(status=s, label=label, color=color,
                         tasks=by_status[s], count=len(by_status[s]))
            for s, label, color in STATUS_META
        ]
        board_brief = BoardBrief(
            id=b.id, name=b.name, description=b.description,
            color_hex=b.color_hex, sector_code=b.sector_code,
            company_id=b.company_id, company_code=co_code, company_name=co_name,
            is_archived=b.is_archived, sort_order=b.sort_order,
            tasks_total=len(tasks),
            tasks_by_status={s: len(by_status[s]) for s in by_status},
        )
        return BoardKanban(board=board_brief, columns=columns)

    # ─── Tasks ────────────────────────────────────────────────────

    async def list_tasks(
        self,
        *,
        scope_company_ids: Optional[list[UUID]] = None,
        **filters,
    ) -> TaskListResponse:
        async with self.uow:
            if scope_company_ids is not None and len(scope_company_ids) == 0:
                return TaskListResponse(items=[], total=0)
            rows, total = await self.uow.tasks.list_tasks(
                scope_company_ids=scope_company_ids, **filters,
            )
        items = [task_to_brief(t, bn, cc) for t, bn, cc in rows]
        enrich_direction_meta(items)
        return TaskListResponse(items=items, total=total)

    async def get_task(
        self,
        task_id: UUID,
        *,
        scope_company_ids: Optional[list[UUID]] = None,
    ) -> TaskDetail:
        async with self.uow:
            row = await self.uow.tasks.get_task_with_meta(task_id)
            if not row:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")
            t, board_name, company_code = row

            if scope_company_ids is not None:
                if t.company_id is None or t.company_id not in scope_company_ids:
                    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this task")

            base = task_to_brief(t, board_name, company_code)
            enrich_direction_meta([base])
            extra = t.extra or {}

        return TaskDetail(
            **base.model_dump(),
            description=t.description,
            scope=extra.get("scope"),
            consultants=extra.get("consultants", []) or [],
            extra=extra,
            legacy_id=t.legacy_id,
            creator_id=t.creator_id,
            start_date=t.start_date,
            completed_at=t.completed_at,
        )
