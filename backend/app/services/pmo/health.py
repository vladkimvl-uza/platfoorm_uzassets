"""PMO P2 — авто-RAG здоровья портфеля + генерация статус-отчёта.

RAG по проекту из сигналов: слип, блокировки, доля просрочки, открытые
высокие риски. Статус-отчёт = снимок метрик + текст-резюме (опц. через ИИ-движок).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.pmo import RaidItem, StatusReport
from app.schemas.pmo import HealthProject, HealthResponse
from app.services.pmo.schedule import build_schedule

log = logging.getLogger(__name__)

RAG_RU = {"red": "красный", "amber": "жёлтый", "green": "зелёный"}
_RANK = {"green": 0, "amber": 1, "red": 2}


def _project_rag(slip: int, blocked: int, overdue: int, total: int,
                 open_risks: int, high_risks: int) -> tuple[str, list[str]]:
    reasons: list[str] = []
    ratio = (overdue / total) if total else 0.0
    red = False
    if slip > 14:
        reasons.append(f"слип {slip} дн"); red = True
    if blocked:
        reasons.append(f"{blocked} блок."); red = True
    if ratio > 0.3:
        reasons.append(f"просрочка {round(ratio * 100)}%"); red = True
    if high_risks:
        reasons.append(f"{high_risks} высоких риск."); red = True
    if red:
        return "red", reasons
    if slip > 0 or overdue > 0 or open_risks > 0:
        if slip > 0:
            reasons.append(f"слип {slip} дн")
        if overdue > 0:
            reasons.append(f"{overdue} просроч.")
        if open_risks > 0:
            reasons.append(f"{open_risks} откр. риск.")
        return "amber", reasons
    return "green", reasons


async def compute_health(db: AsyncSession, company_code: str, today: date) -> Optional[HealthResponse]:
    sched = await build_schedule(db, company_code, None, today)
    if sched is None:
        return None
    company = (
        await db.execute(select(Company).where(Company.code == company_code))
    ).scalar_one_or_none()
    if company is None:
        return None

    raids = (
        await db.execute(
            select(RaidItem).where(RaidItem.company_id == company.id, RaidItem.status != "closed")
        )
    ).scalars().all()

    bars = sched.bars
    project_bars = [b for b in bars if b.kind == "project"]
    task_bars = [b for b in bars if b.kind == "task"]

    def raids_for(pid: Optional[UUID]) -> list[RaidItem]:
        return [r for r in raids if (r.project_id == pid)]

    projects: list[HealthProject] = []

    def build_card(pid: Optional[UUID], title: str, prog: int, slip: int, tasks) -> HealthProject:
        overdue = sum(1 for t in tasks if t.due and t.due < today and t.status != "done")
        blocked = sum(1 for t in tasks if t.blocked)
        rs = raids_for(pid)
        open_risks = len(rs)
        high_risks = sum(1 for r in rs if r.severity in ("high", "critical"))
        rag, reasons = _project_rag(slip, blocked, overdue, len(tasks), open_risks, high_risks)
        return HealthProject(
            project_id=pid, title=title, rag=rag, progress_percent=int(prog or 0),
            slip_days=slip, overdue_count=overdue, blocked_count=blocked,
            open_risks=open_risks, high_risks=high_risks, reasons=reasons,
        )

    for pb in project_bars:
        ts = [t for t in task_bars if t.project_id == pb.id]
        slip = pb.slip_days or max((t.slip_days for t in ts), default=0)
        projects.append(build_card(pb.id, pb.title, pb.progress_percent, slip, ts))

    orphan = [t for t in task_bars if not any(t.project_id == pb.id for pb in project_bars)]
    if orphan:
        slip = max((t.slip_days for t in orphan), default=0)
        avg = round(sum(t.progress_percent for t in orphan) / len(orphan)) if orphan else 0
        projects.append(build_card(None, "Без проекта", avg, slip, orphan))

    green = sum(1 for p in projects if p.rag == "green")
    amber = sum(1 for p in projects if p.rag == "amber")
    red = sum(1 for p in projects if p.rag == "red")
    portfolio_rag = "red" if red else ("amber" if amber else "green")

    return HealthResponse(
        company_code=company_code, as_of=today, portfolio_rag=portfolio_rag,
        projects=sorted(projects, key=lambda p: -_RANK[p.rag]),
        green=green, amber=amber, red=red,
        open_risks=len(raids),
        high_risks=sum(1 for r in raids if r.severity in ("high", "critical")),
    )


def _rule_summary(h: HealthResponse, project_id: Optional[UUID]) -> str:
    lines: list[str] = []
    if project_id:
        p = next((x for x in h.projects if str(x.project_id) == str(project_id)), None)
        if p is None:
            return "Нет данных по проекту."
        lines.append(f"Статус на {h.as_of}: {p.title} — {RAG_RU[p.rag]}.")
        lines.append(f"Прогресс {p.progress_percent}%, слип {p.slip_days} дн, просрочено {p.overdue_count}, заблокировано {p.blocked_count}.")
        lines.append(f"Открытых рисков {p.open_risks} (высоких {p.high_risks}).")
        if p.reasons:
            lines.append("Сигналы: " + ", ".join(p.reasons) + ".")
        return "\n".join(lines)
    lines.append(f"Статус на {h.as_of}: портфель {RAG_RU[h.portfolio_rag]}.")
    lines.append(f"Проекты: {h.red} красных, {h.amber} жёлтых, {h.green} зелёных.")
    lines.append(f"Открытых рисков {h.open_risks} (высоких/критич. {h.high_risks}).")
    problem = [p for p in h.projects if p.rag in ("red", "amber")]
    for p in problem[:6]:
        lines.append(f"• {p.title} — {RAG_RU[p.rag]}: {', '.join(p.reasons) or '—'}.")
    return "\n".join(lines)


async def _ai_summary(rule_text: str) -> str:
    """Опц. AI-резюме поверх метрик. При любой ошибке/выключенном движке — фолбэк."""
    try:
        from app.services.ai_service import complete_once, is_enabled
        if not is_enabled():
            return rule_text
        out = await complete_once(
            system=(
                "Ты — PMO-аналитик. На основе сухих метрик статуса портфеля напиши "
                "краткое управленческое резюме на русском (3–5 предложений): общая оценка, "
                "главные риски/проблемы, что требует внимания руководства. Без воды, без эмодзи."
            ),
            prompt=rule_text,
            model=None, max_tokens=500, temperature=None, timeout=60.0,
        )
        return (out or "").strip() or rule_text
    except Exception as e:  # noqa: BLE001
        log.warning("PMO status-report AI summary failed, fallback to rules: %s", e)
        return rule_text


async def generate_status_report(
    db: AsyncSession, company_code: str, project_id: Optional[UUID],
    use_ai: bool, user_id: Optional[UUID], today: date,
) -> Optional[StatusReport]:
    h = await compute_health(db, company_code, today)
    if h is None:
        return None
    company = (
        await db.execute(select(Company).where(Company.code == company_code))
    ).scalar_one_or_none()
    if company is None:
        return None

    if project_id:
        p = next((x for x in h.projects if str(x.project_id) == str(project_id)), None)
        rag = p.rag if p else "green"
        metrics = p.model_dump(mode="json") if p else {}
    else:
        rag = h.portfolio_rag
        metrics = {
            "green": h.green, "amber": h.amber, "red": h.red,
            "open_risks": h.open_risks, "high_risks": h.high_risks,
            "projects": [p.model_dump(mode="json") for p in h.projects],
        }

    summary = _rule_summary(h, project_id)
    if use_ai:
        summary = await _ai_summary(summary)

    report = StatusReport(
        company_id=company.id, project_id=project_id, period=today,
        rag=rag, summary=summary, metrics=metrics, created_by=user_id,
    )
    db.add(report)
    await db.flush()
    await db.commit()
    await db.refresh(report)
    return report
