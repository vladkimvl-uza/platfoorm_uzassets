"""PMO P1 — построение расписания, критического пути (CPM) и слипа.

Функциональный сервис (как ai_exec_brief): принимает db, возвращает DTO.
Критический путь = самая длинная по суммарной длительности цепочка задач
через зависимости FS. Слип = текущий due − базовый due.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.schemas.pmo import ScheduleBar, ScheduleResponse


def _duration_days(start: Optional[date], due: Optional[date], is_milestone: bool) -> int:
    if is_milestone:
        return 0
    if start and due:
        return max((due - start).days, 0)
    return 1


def _slip(due: Optional[date], baseline_due: Optional[date]) -> int:
    if due and baseline_due:
        return (due - baseline_due).days
    return 0


def _critical_path(tasks: list[Task], deps: list[TaskDependency]) -> set[UUID]:
    """Longest-path (по длительности) через DAG зависимостей FS → множество
    id задач на критическом пути. Циклы игнорируются (Kahn по indeg)."""
    dur: dict[UUID, int] = {
        t.id: _duration_days(t.start_date, t.due_date, bool(t.is_milestone)) for t in tasks
    }
    ids = set(dur)
    succ: dict[UUID, list[tuple[UUID, int]]] = defaultdict(list)
    preds: dict[UUID, list[tuple[UUID, int]]] = defaultdict(list)
    indeg: dict[UUID, int] = {tid: 0 for tid in ids}
    for d in deps:
        if d.predecessor_id in ids and d.successor_id in ids:
            succ[d.predecessor_id].append((d.successor_id, int(d.lag_days or 0)))
            preds[d.successor_id].append((d.predecessor_id, int(d.lag_days or 0)))
            indeg[d.successor_id] += 1

    # Топологический порядок (Kahn)
    q = deque([tid for tid in ids if indeg[tid] == 0])
    topo: list[UUID] = []
    indeg_work = dict(indeg)
    while q:
        n = q.popleft()
        topo.append(n)
        for s, _lag in succ[n]:
            indeg_work[s] -= 1
            if indeg_work[s] == 0:
                q.append(s)
    if len(topo) != len(ids):
        return set()  # цикл — критический путь не считаем (защита)

    # Forward pass: EF = max(EF[pred] + lag) + dur
    ef: dict[UUID, int] = {}
    best_pred: dict[UUID, Optional[UUID]] = {}
    for n in topo:
        es = 0
        bp: Optional[UUID] = None
        for p, lag in preds[n]:
            cand = ef.get(p, 0) + lag
            if cand > es:
                es = cand
                bp = p
        ef[n] = es + dur[n]
        best_pred[n] = bp

    if not ef:
        return set()
    # Конец критического пути = узел с макс EF; бэктрек
    end = max(ef, key=lambda k: ef[k])
    path: set[UUID] = set()
    cur: Optional[UUID] = end
    while cur is not None:
        path.add(cur)
        cur = best_pred.get(cur)
    return path


async def build_schedule(
    db: AsyncSession,
    company_code: str,
    year: Optional[int],
    today: date,
) -> Optional[ScheduleResponse]:
    company = (
        await db.execute(select(Company).where(Company.code == company_code))
    ).scalar_one_or_none()
    if company is None:
        return None

    proj_rows = (
        await db.execute(
            select(Project).where(
                Project.company_id == company.id,
                Project.is_archived.is_(False),
            )
        )
    ).scalars().all()
    if year is not None:
        proj_rows = [p for p in proj_rows if p.portfolio_year in (None, year)]
    proj_ids = {p.id for p in proj_rows}

    task_rows = (
        await db.execute(
            select(Task).where(
                Task.company_id == company.id,
                Task.is_archived.is_(False),
            )
        )
    ).scalars().all()
    # задачи без company_id, но привязанные к проектам компании — добираем
    if proj_ids:
        extra_tasks = (
            await db.execute(
                select(Task).where(
                    Task.project_id.in_(proj_ids),
                    Task.is_archived.is_(False),
                )
            )
        ).scalars().all()
        seen = {t.id for t in task_rows}
        task_rows = list(task_rows) + [t for t in extra_tasks if t.id not in seen]
    if year is not None:
        task_rows = [t for t in task_rows if t.portfolio_year in (None, year)]

    task_ids = {t.id for t in task_rows}
    deps: list[TaskDependency] = []
    if task_ids:
        deps = list(
            (
                await db.execute(
                    select(TaskDependency).where(
                        TaskDependency.successor_id.in_(task_ids)
                    )
                )
            ).scalars().all()
        )

    # Карты для блокировок / критического пути
    status_by_id = {t.id: t.status for t in task_rows}
    preds_by_succ: dict[UUID, list[UUID]] = defaultdict(list)
    for d in deps:
        preds_by_succ[d.successor_id].append(d.predecessor_id)

    critical = _critical_path(list(task_rows), deps)

    bars: list[ScheduleBar] = []

    # Проекты — summary-бары
    for p in proj_rows:
        bars.append(ScheduleBar(
            id=p.id, kind="project", project_id=None, title=p.title,
            status=p.status, progress_percent=int(p.progress_percent or 0),
            start=p.start_date, due=p.due_date,
            baseline_start=p.baseline_start, baseline_due=p.baseline_due,
            is_milestone=False, assignee_name=p.assignee_name,
            direction=(p.extra or {}).get("direction") if p.extra else None,
            slip_days=_slip(p.due_date, p.baseline_due),
            on_critical_path=False, predecessor_ids=[], blocked=False,
        ))

    # Задачи
    for t in task_rows:
        preds = preds_by_succ.get(t.id, [])
        blocked = any(status_by_id.get(pid) not in ("done",) for pid in preds)
        bars.append(ScheduleBar(
            id=t.id, kind="task", project_id=t.project_id, title=t.title,
            status=t.status, progress_percent=int(t.progress_percent or 0),
            start=t.start_date, due=t.due_date,
            baseline_start=t.baseline_start, baseline_due=t.baseline_due,
            is_milestone=bool(t.is_milestone), assignee_name=t.assignee_name,
            direction=(t.extra or {}).get("direction") if t.extra else None,
            slip_days=_slip(t.due_date, t.baseline_due),
            on_critical_path=t.id in critical,
            predecessor_ids=preds,
            blocked=blocked,
        ))

    # Сводка
    dues = [b.due for b in bars if b.due]
    base_dues = [b.baseline_due for b in bars if b.baseline_due]
    forecast_finish = max(dues) if dues else None
    baseline_finish = max(base_dues) if base_dues else None
    if forecast_finish and baseline_finish:
        portfolio_slip = (forecast_finish - baseline_finish).days
    else:
        portfolio_slip = max((b.slip_days for b in bars), default=0)
    overdue_count = sum(
        1 for b in bars
        if b.kind == "task" and b.due and b.due < today and b.status != "done"
    )
    blocked_count = sum(1 for b in bars if b.blocked)

    return ScheduleResponse(
        company_code=company_code,
        year=year,
        as_of=today,
        bars=bars,
        portfolio_slip_days=portfolio_slip,
        forecast_finish=forecast_finish,
        baseline_finish=baseline_finish,
        critical_path_ids=list(critical),
        overdue_count=overdue_count,
        blocked_count=blocked_count,
    )
