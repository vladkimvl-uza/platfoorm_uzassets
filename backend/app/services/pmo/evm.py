"""PMO — освоенный объём (Earned Value Management, PMBOK 7).

Точечный EVM на дату `today`. На вход берём бюджет (BAC) и факт затрат (AC)
проектов + взвешенный прогресс (из core.progress) + базовый план дат, считаем
EV/PV, индексы SPI/CPI, отклонения SV/CV и прогнозы EAC/ETC/VAC/TCPI.

SPI считается из прогресса/планового % и доступен даже без бюджета (BAC
сокращается). Стоимостные метрики требуют BAC и AC.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.progress import task_pct, weighted_pct
from app.models.company import Company
from app.models.project import Project
from app.models.task import Task
from app.schemas.pmo import EvmProject, EvmResponse


def _planned_fraction(today: date, start: Optional[date], end: Optional[date]) -> Optional[float]:
    """Доля планового времени, прошедшая на `today` (0..1). None если нет дат."""
    if not start or not end or end <= start:
        # Если есть только дедлайн — план=1 после него, иначе None.
        if end and today >= end:
            return 1.0
        return None
    if today <= start:
        return 0.0
    if today >= end:
        return 1.0
    return (today - start).days / (end - start).days


def _r(v: Optional[float], n: int = 2) -> Optional[float]:
    return round(v, n) if v is not None else None


def _rag(spi: Optional[float], cpi: Optional[float]) -> str:
    vals = [v for v in (spi, cpi) if v is not None]
    if not vals:
        return "na"
    worst = min(vals)
    if worst >= 0.95:
        return "green"
    if worst >= 0.85:
        return "amber"
    return "red"


def _project_evm(
    *, project_id, title: str, progress_pct: int,
    bac: Optional[float], ac: Optional[float],
    planned: Optional[float],
) -> EvmProject:
    progress = progress_pct / 100.0
    ev = bac * progress if bac is not None else None
    pv = bac * planned if (bac is not None and planned is not None) else None

    spi = (progress / planned) if (planned and planned > 0) else None
    cpi = (ev / ac) if (ev is not None and ac and ac > 0) else None
    sv = (ev - pv) if (ev is not None and pv is not None) else None
    cv = (ev - ac) if (ev is not None and ac is not None) else None

    eac = (bac / cpi) if (bac is not None and cpi and cpi > 0) else None
    etc = (eac - ac) if (eac is not None and ac is not None) else None
    vac = (bac - eac) if (bac is not None and eac is not None) else None
    tcpi = None
    if bac is not None and ev is not None and ac is not None and (bac - ac) != 0:
        tcpi = (bac - ev) / (bac - ac)

    return EvmProject(
        project_id=project_id, title=title,
        progress_percent=progress_pct,
        planned_percent=(round(planned * 100) if planned is not None else None),
        bac=_r(bac), ev=_r(ev), pv=_r(pv), ac=_r(ac),
        spi=_r(spi), cpi=_r(cpi), sv=_r(sv), cv=_r(cv),
        eac=_r(eac), etc=_r(etc), vac=_r(vac), tcpi=_r(tcpi),
        rag=_rag(spi, cpi),
    )


async def compute_evm(
    db: AsyncSession, company_code: str, today: date, year: Optional[int] = None,
) -> Optional[EvmResponse]:
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

    task_rows = (
        await db.execute(
            select(Task).where(
                Task.company_id == company.id,
                Task.is_archived.is_(False),
            )
        )
    ).scalars().all()
    proj_ids = {p.id for p in proj_rows}
    if proj_ids:
        extra = (
            await db.execute(
                select(Task).where(
                    Task.project_id.in_(proj_ids),
                    Task.is_archived.is_(False),
                )
            )
        ).scalars().all()
        seen = {t.id for t in task_rows}
        task_rows = list(task_rows) + [t for t in extra if t.id not in seen]
    if year is not None:
        task_rows = [t for t in task_rows if t.portfolio_year in (None, year)]

    projects: list[EvmProject] = []
    # Вес проекта для портфельных индексов = число его задач (объём работ).
    # Нужен, чтобы SPI без бюджета не считался средним арифметическим по
    # проектам: проект на две задачи не должен весить столько же, сколько
    # годовой (та же ошибка «среднее из отношений», что чинили в дашборде).
    weight_by_project: dict = {}
    for p in proj_rows:
        kids = [t for t in task_rows if t.project_id == p.id]
        weight_by_project[p.id] = len(kids) or 1
        if kids:
            progress_pct = weighted_pct((t.status, t.extra) for t in kids)
        else:
            progress_pct = task_pct(p.status, p.extra) or 0
        bac = float(p.budget_amount) if p.budget_amount is not None else None
        ac = float(p.actual_cost) if p.actual_cost is not None else None
        planned = _planned_fraction(
            today,
            p.baseline_start or p.start_date,
            p.baseline_due or p.due_date,
        )
        projects.append(_project_evm(
            project_id=p.id, title=p.title, progress_pct=progress_pct,
            bac=bac, ac=ac, planned=planned,
        ))

    # ── Портфельный rollup (бюджетные проекты) ──
    budgeted = [p for p in projects if p.bac is not None]
    BAC = sum(p.bac for p in budgeted) if budgeted else None

    # Каждый индекс — по СВОЕЙ паре: EV есть у любого бюджетного проекта,
    # AC — только где внесли факт затрат, PV — только где есть плановые даты.
    # Раньше CPI делил EV всех бюджетных на AC подмножества: портфель показывал
    # CPI 3.4 и «экономию» зелёным, хотя ни один проект такого CPI не имел.
    # Правило то же, что у портфельных марж: в дробь попадает проект, у
    # которого есть ОБА слагаемых.
    sched_pair = [p for p in budgeted if p.ev is not None and p.pv is not None]
    cost_pair = [p for p in budgeted if p.ev is not None and p.ac is not None]
    EV_s = sum(p.ev for p in sched_pair) if sched_pair else None
    PV = sum(p.pv for p in sched_pair) if sched_pair else None
    EV_c = sum(p.ev for p in cost_pair) if cost_pair else None
    AC = sum(p.ac for p in cost_pair) if cost_pair else None
    BAC_c = sum(p.bac for p in cost_pair) if cost_pair else None
    # EV в ответе — общий освоенный объём портфеля (по всем бюджетным).
    EV = sum(p.ev for p in budgeted if p.ev is not None) if budgeted else None

    spi = (EV_s / PV) if (EV_s is not None and PV and PV > 0) else None
    # SPI без бюджета — ВЗВЕШЕННЫЙ по объёму работ проекта (числу задач), а не
    # среднее арифметическое проектных SPI: маленький проект иначе тянул индекс
    # наравне с крупным и портфельная цифра переставала описывать портфель.
    if spi is None:
        num = 0.0
        den = 0.0
        for p in projects:
            if p.spi is None:
                continue
            w = float(weight_by_project.get(p.project_id, 1))
            num += p.spi * w
            den += w
        spi = (num / den) if den > 0 else None
    # Стоимостные метрики — строго по cost_pair: и числитель, и знаменатель,
    # и бюджет для прогнозов из одного набора проектов, иначе EAC/VAC
    # «предсказывают» экономию там, где просто не внесли затраты.
    cpi = (EV_c / AC) if (EV_c is not None and AC and AC > 0) else None
    sv = (EV_s - PV) if (EV_s is not None and PV is not None) else None
    cv = (EV_c - AC) if (EV_c is not None and AC is not None) else None
    eac = (BAC_c / cpi) if (BAC_c is not None and cpi and cpi > 0) else None
    etc = (eac - AC) if (eac is not None and AC is not None) else None
    vac = (BAC_c - eac) if (BAC_c is not None and eac is not None) else None
    tcpi = None
    if BAC_c is not None and EV_c is not None and AC is not None and (BAC_c - AC) != 0:
        tcpi = (BAC_c - EV_c) / (BAC_c - AC)

    return EvmResponse(
        company_code=company_code,
        as_of=today,
        bac=_r(BAC), ev=_r(EV), pv=_r(PV), ac=_r(AC),
        spi=_r(spi), cpi=_r(cpi), sv=_r(sv), cv=_r(cv),
        eac=_r(eac), etc=_r(etc), vac=_r(vac), tcpi=_r(tcpi),
        rag=_rag(spi, cpi),
        projects=projects,
        budgeted_count=len(budgeted),
        total_count=len(projects),
        scheduled_count=sum(1 for p in projects if p.spi is not None),
        costed_count=len(cost_pair),
    )
