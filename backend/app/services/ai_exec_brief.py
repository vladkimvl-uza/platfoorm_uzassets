"""ИИ-аналитик секторного исполнения.

Собирает компактный контекст для эндпоинта /ai/exec-sector-brief.

ВАЖНО (точность): проект СОСТОИТ из задач, и прогресс проекта = доля
выполненных задач (см. app.core.progress). Поэтому реальные причины задержек
видны именно НА УРОВНЕ ЗАДАЧ — в их статусах, сроках и комментариях, которые
заполняют пользователи. Этот билдер:
  • грузит дочерние задачи проектов (одним запросом, без N+1);
  • считает по каждому проекту разбивку задач (готово/просрочено/в работе/
    не начато) единым правилом прогресса;
  • определяет ПРОБЛЕМНЫЕ проекты по сигналам ЗАДАЧ (просроченные задачи,
    низкая доля выполнения), а не только по проценту проекта;
  • для проблемных проектов отдаёт КОНКРЕТНЫЕ открытые задачи + комментарии
    к ним (и к проекту) — то, что люди реально пишут в карточках.

RBAC: только компании из allowed_company_ids (как в /projects).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.progress import is_task_overdue, task_weight
from app.models.company import Company, Sector
from app.models.project import Project, ProjectComment
from app.models.task import Task, TaskComment
from app.models.user import User

_DONE = {"done"}
_NON_PROGRESS = {"done", "monthly", "ongoing", "quarterly"}
_IN_PROGRESS = {"active", "review"}
_NOT_STARTED = {"new", "init"}
_STATUS_RU = {
    "init": "инициирование", "new": "не начато", "active": "в процессе",
    "review": "на согласовании", "done": "завершено", "deferred": "перенесено",
    "quarterly": "ежеквартально", "monthly": "ежемесячно", "ongoing": "постоянно",
}


def _short(text: str | None, n: int = 360) -> str:
    return " ".join((text or "").split())[:n]


async def build_exec_brief_context(
    db: AsyncSession,
    user: User,
    *,
    year: int,
    sectors: list[str] | None = None,
    company_id: UUID | None = None,
    max_problem: int = 20,
) -> tuple[str, dict]:
    """Возвращает (компактный_контекст_текст, scope_meta). Без вызова модели."""
    allowed = await allowed_company_ids(db, user)  # None = без ограничений (owner/полный)

    cq = (
        select(Company.id, Company.name_ru, Company.name_short, Sector.name_ru.label("sector"))
        .join(Sector, Company.sector_id == Sector.id, isouter=True)
    )
    if allowed is not None:
        cq = cq.where(Company.id.in_(allowed))
    if company_id is not None:
        cq = cq.where(Company.id == company_id)
    else:
        # Сводный бриф: демо и непрофильные компании (include_in_rollups=false) не должны искажать портфельные и секторные цифры; для брифа по одной компании фильтр не применяем.
        cq = cq.where(Company.include_in_rollups.is_(True))
    if sectors:
        cq = cq.where(or_(Sector.code.in_(sectors), Sector.name_ru.in_(sectors)))
    companies = (await db.execute(cq)).all()
    if not companies:
        return ("Нет компаний в зоне доступа по заданным фильтрам.", {"companies": 0, "projects": 0})

    co_map = {c.id: c for c in companies}
    company_ids = list(co_map.keys())

    projects = (
        await db.execute(
            select(Project).where(
                Project.company_id.in_(company_ids),
                Project.portfolio_year == year,
                Project.is_archived.is_(False),
            )
        )
    ).scalars().all()

    today = date.today()

    # ── Дочерние задачи всех проектов (один запрос) ───────────────────
    project_ids = [p.id for p in projects]
    tasks_by_pid: dict[UUID, list[Task]] = {}
    if project_ids:
        trows = (
            await db.execute(
                select(Task).where(
                    Task.project_id.in_(project_ids),
                    Task.is_archived.is_(False),
                )
            )
        ).scalars().all()
        for t in trows:
            tasks_by_pid.setdefault(t.project_id, []).append(t)

    def task_overdue(t: Task) -> bool:
        return is_task_overdue(t.status, t.due_date, today=today)

    def is_open(t: Task) -> bool:
        # «Открытая» = ещё не завершена и не бессрочная (monthly/ongoing исключены).
        w = task_weight(t.status, t.extra)
        return w is not None and w < 1.0

    def task_stats(tlist: list[Task]) -> dict:
        done = total = overdue_n = in_prog = not_started = excluded = 0
        wsum = 0.0
        for t in tlist:
            w = task_weight(t.status, t.extra)
            if w is None:           # monthly/ongoing — вне процента
                excluded += 1
                continue
            total += 1
            wsum += w
            if w >= 1.0:
                done += 1
                continue
            if task_overdue(t):
                overdue_n += 1
            if t.status in _IN_PROGRESS:
                in_prog += 1
            elif t.status in _NOT_STARTED:
                not_started += 1
        return {
            "done": done, "total": total, "wsum": wsum, "overdue": overdue_n,
            "in_prog": in_prog, "not_started": not_started, "excluded": excluded,
        }

    def proj_overdue(p: Project) -> bool:
        return is_task_overdue(p.status, p.due_date, today=today)

    stats_by_pid = {p.id: task_stats(tasks_by_pid.get(p.id, [])) for p in projects}

    def is_problem(p: Project) -> bool:
        st = stats_by_pid[p.id]
        if proj_overdue(p):
            return True
        if st["overdue"] > 0:
            return True
        if st["total"] > 0 and (st["wsum"] / st["total"]) < 0.4:
            return True
        # Проект без задач — судим по его собственному проценту.
        if st["total"] == 0 and p.progress_percent < 40 and p.status not in _NON_PROGRESS:
            return True
        return False

    def completion(p: Project) -> float:
        st = stats_by_pid[p.id]
        return (st["wsum"] / st["total"]) if st["total"] else (p.progress_percent / 100.0)

    problem = [p for p in projects if is_problem(p)]
    # Сначала с просрочкой, затем по возрастанию доли выполнения.
    problem.sort(key=lambda p: (not (proj_overdue(p) or stats_by_pid[p.id]["overdue"] > 0), completion(p)))
    problem = problem[:max_problem]
    problem_ids = {p.id for p in problem}

    # ── Открытые задачи проблемных проектов (что показываем) ──────────
    open_by_pid: dict[UUID, list[Task]] = {}
    shown_task_ids: list[UUID] = []
    for p in problem:
        opens = [t for t in tasks_by_pid.get(p.id, []) if is_open(t)]
        opens.sort(key=lambda t: (not task_overdue(t), t.due_date or date.max))
        opens = opens[:8]
        open_by_pid[p.id] = opens
        shown_task_ids.extend(t.id for t in opens)

    # ── Комментарии: к проблемным проектам и к показанным задачам ─────
    pcomments_by_pid: dict[UUID, list[str]] = {}
    if problem_ids:
        rows = (
            await db.execute(
                select(ProjectComment.project_id, ProjectComment.body)
                .where(ProjectComment.project_id.in_(list(problem_ids)))
                .order_by(ProjectComment.created_at.desc())
            )
        ).all()
        for pid, body in rows:
            lst = pcomments_by_pid.setdefault(pid, [])
            if len(lst) < 3 and body:
                lst.append(_short(body, 400))

    tcomments_by_tid: dict[UUID, list[str]] = {}
    if shown_task_ids:
        rows = (
            await db.execute(
                select(TaskComment.task_id, TaskComment.body)
                .where(TaskComment.task_id.in_(shown_task_ids))
                .order_by(TaskComment.created_at.desc())
            )
        ).all()
        for tid, body in rows:
            lst = tcomments_by_tid.setdefault(tid, [])
            if len(lst) < 2 and body:
                lst.append(_short(body, 300))

    # ── Группировка сектор → компания → проекты ───────────────────────
    by_sector: dict[str, dict[str, list[Project]]] = {}
    for p in projects:
        co = co_map.get(p.company_id)
        if not co:
            continue
        sec = co.sector or "Без сектора"
        coname = co.name_short or co.name_ru
        by_sector.setdefault(sec, {}).setdefault(coname, []).append(p)

    # ── Портфельные агрегаты ──────────────────────────────────────────
    total = len(projects)
    done_proj = sum(1 for p in projects if p.status in _DONE)
    overdue_proj = sum(1 for p in projects if proj_overdue(p))
    t_done = sum(s["done"] for s in stats_by_pid.values())
    t_total = sum(s["total"] for s in stats_by_pid.values())
    t_overdue = sum(s["overdue"] for s in stats_by_pid.values())

    lines: list[str] = [
        f"Портфель FY{year}: компаний {len(companies)}, проектов {total} "
        f"(завершено {done_proj}, просрочено {overdue_proj}). "
        f"Задач в этих проектах: {t_total} (выполнено {t_done}"
        + (f", {round(t_done / t_total * 100)}%" if t_total else "")
        + f", просрочено {t_overdue}). "
        "Прогресс проекта = доля выполненных задач; смотри причины на уровне задач и комментариев.",
    ]

    def task_line(t: Task) -> str:
        flag = " [ПРОСРОЧЕНА]" if task_overdue(t) else ""
        due = t.due_date.isoformat() if t.due_date else "—"
        num = f"{t.num} " if t.num else ""
        who = f", отв.: {t.assignee_name}" if t.assignee_name else ""
        return (
            f"    · задача {num}«{t.title}» — {_STATUS_RU.get(t.status, t.status)}, "
            f"срок {due}{flag}{who}"
        )

    for sec, comps in by_sector.items():
        sproj = [p for plist in comps.values() for p in plist]
        avg = round(sum(p.progress_percent for p in sproj) / len(sproj)) if sproj else 0
        so = sum(stats_by_pid[p.id]["overdue"] for p in sproj)
        lines.append(
            f"\n## Сектор: {sec} — компаний {len(comps)}, проектов {len(sproj)}, "
            f"средний прогресс {avg}%, просроченных задач {so}"
        )
        for coname, plist in comps.items():
            lines.append(f"### {coname}")
            for p in plist:
                st = stats_by_pid[p.id]
                flag = " [ПРОСРОЧЕН]" if proj_overdue(p) else ""
                due = p.due_date.isoformat() if p.due_date else "—"
                tsum = (
                    f"задач {st['total']}: готово {st['done']}, просрочено {st['overdue']}, "
                    f"в работе {st['in_prog']}, не начато {st['not_started']}"
                    + (f", бессрочных {st['excluded']}" if st["excluded"] else "")
                ) if (st["total"] or st["excluded"]) else "без задач"
                lines.append(
                    f"- «{p.title}» — статус: {_STATUS_RU.get(p.status, p.status)}, "
                    f"прогресс {p.progress_percent}% ({tsum}), приоритет {p.priority}, срок {due}{flag}"
                )
                if p.id in problem_ids:
                    for cmt in pcomments_by_pid.get(p.id, []):
                        lines.append(f"    · комментарий к проекту: {cmt}")
                    opens = open_by_pid.get(p.id, [])
                    if opens:
                        lines.append(f"    Открытые задачи ({len(opens)} показано):")
                        for t in opens:
                            lines.append(task_line(t))
                            for cmt in tcomments_by_tid.get(t.id, []):
                                lines.append(f"      – комментарий: {cmt}")

    text = "\n".join(lines)
    if len(text) > 38000:  # бюджет контекста (токен-лимит модели)
        text = text[:38000] + "\n…(контекст усечён по объёму)"
    scope = {
        "companies": len(companies),
        "projects": total,
        "tasks": t_total,
        "tasks_overdue": t_overdue,
        "overdue": overdue_proj,
        "problem": len(problem),
    }
    return text, scope
