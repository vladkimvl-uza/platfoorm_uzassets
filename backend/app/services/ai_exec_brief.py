"""ИИ-аналитик секторного исполнения.

Собирает компактный контекст для эндпоинта /ai/exec-sector-brief: проекты
портфеля по секторам/компаниям за год (статус, прогресс, сроки, просрочка) +
комментарии и ход по ПРОБЛЕМНЫМ проектам (то, что люди заполняют в карточках).
RBAC: только компании из allowed_company_ids (как в /projects).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.models.company import Company, Sector
from app.models.project import Project, ProjectComment
from app.models.user import User

_DONE = {"done"}
_NON_PROGRESS = {"done", "monthly", "ongoing", "quarterly"}
_STATUS_RU = {
    "init": "инициирование", "new": "не начато", "active": "в процессе",
    "review": "на согласовании", "done": "завершено", "deferred": "перенесено",
    "quarterly": "ежеквартально", "monthly": "ежемесячно", "ongoing": "постоянно",
}


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

    def overdue(p: Project) -> bool:
        return bool(p.due_date and p.due_date < today and p.status not in _DONE)

    problem = [
        p for p in projects
        if overdue(p) or (p.progress_percent < 40 and p.status not in _NON_PROGRESS)
    ]
    problem.sort(key=lambda p: (not overdue(p), p.progress_percent))
    problem = problem[:max_problem]
    problem_ids = {p.id for p in problem}

    comments_by_pid: dict[UUID, list[str]] = {}
    if problem:
        rows = (
            await db.execute(
                select(ProjectComment.project_id, ProjectComment.body)
                .where(ProjectComment.project_id.in_(list(problem_ids)))
                .order_by(ProjectComment.created_at.desc())
            )
        ).all()
        for pid, body in rows:
            lst = comments_by_pid.setdefault(pid, [])
            if len(lst) < 3 and body:
                lst.append(" ".join(body.split())[:400])

    # Группировка сектор → компания → проекты
    by_sector: dict[str, dict[str, list[Project]]] = {}
    for p in projects:
        co = co_map.get(p.company_id)
        if not co:
            continue
        sec = co.sector or "Без сектора"
        coname = co.name_short or co.name_ru
        by_sector.setdefault(sec, {}).setdefault(coname, []).append(p)

    total = len(projects)
    done = sum(1 for p in projects if p.status in _DONE)
    overdue_n = sum(1 for p in projects if overdue(p))

    lines: list[str] = [
        f"Портфель FY{year}: компаний {len(companies)}, проектов {total}, "
        f"завершено {done}, просрочено {overdue_n}.",
    ]
    for sec, comps in by_sector.items():
        sproj = [p for plist in comps.values() for p in plist]
        avg = round(sum(p.progress_percent for p in sproj) / len(sproj)) if sproj else 0
        lines.append(
            f"\n## Сектор: {sec} — компаний {len(comps)}, проектов {len(sproj)}, средний прогресс {avg}%"
        )
        for coname, plist in comps.items():
            lines.append(f"### {coname}")
            for p in plist:
                flag = " [ПРОСРОЧЕН]" if overdue(p) else ""
                due = p.due_date.isoformat() if p.due_date else "—"
                lines.append(
                    f"- «{p.title}» — статус: {_STATUS_RU.get(p.status, p.status)}, "
                    f"прогресс {p.progress_percent}%, приоритет {p.priority}, срок {due}{flag}"
                )
                for cmt in comments_by_pid.get(p.id, []):
                    lines.append(f"    · комментарий: {cmt}")

    text = "\n".join(lines)
    if len(text) > 38000:  # бюджет контекста (токен-лимит модели)
        text = text[:38000] + "\n…(контекст усечён по объёму)"
    scope = {"companies": len(companies), "projects": total, "overdue": overdue_n, "problem": len(problem)}
    return text, scope
