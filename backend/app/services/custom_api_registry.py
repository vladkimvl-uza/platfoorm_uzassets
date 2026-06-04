"""Реестр источников данных для Конструктора API (custom API endpoints).

Каждый источник декларирует: ключ, человекочитаемое имя, доступные колонки,
поддерживаемые фильтры и async-функцию `fetch(...)`, которая возвращает строки
(list[dict]) из существующих моделей. Диспетчер `/api/v1/custom/{slug}`
применяет фильтры (включая RBAC-scope по компаниям) и отдаёт JSON.

Добавить источник = добавить запись в SOURCES.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency_rating import AgencyRating
from app.models.bp_kpi import KpiIndicator, KpiManager
from app.models.company import Company
from app.models.financial import FinancialLine, FinancialReport
from app.models.project import Project
from app.models.task import Task


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ──────────────────────────── KPI ────────────────────────────

async def _fetch_kpi(db: AsyncSession, *, company_ids=None, year=None, limit=2000, **_):
    q = (
        select(
            Company.code, Company.name_short, Company.name_ru,
            KpiManager.year, KpiManager.title.label("manager"),
            KpiIndicator.name, KpiIndicator.unit, KpiIndicator.weight,
            KpiIndicator.plan_year, KpiIndicator.fact_year,
        )
        .join(KpiManager, KpiManager.company_id == Company.id)
        .join(KpiIndicator, KpiIndicator.manager_id == KpiManager.id)
        .order_by(Company.code, KpiManager.year, KpiManager.sort_order, KpiIndicator.sort_order)
        .limit(limit)
    )
    if company_ids is not None:
        q = q.where(Company.id.in_(company_ids))
    if year is not None:
        q = q.where(KpiManager.year == year)
    out = []
    for r in (await db.execute(q)).all():
        m = r._mapping
        plan, fact = _num(m["plan_year"]), _num(m["fact_year"])
        out.append({
            "company": m["name_short"] or m["name_ru"], "company_code": m["code"],
            "year": m["year"], "manager": m["manager"],
            "indicator": m["name"], "unit": m["unit"],
            "weight": _num(m["weight"]), "plan": plan, "fact": fact,
            "pct": round(fact / plan * 100, 1) if plan and fact is not None and plan != 0 else None,
        })
    return out


# ──────────────────────────── Финансы ────────────────────────────

async def _fetch_financials(db: AsyncSession, *, company_ids=None, year=None, standard=None, limit=3000, **_):
    q = (
        select(
            Company.code, Company.name_short, Company.name_ru,
            FinancialReport.year, FinancialReport.standard, FinancialReport.report_type,
            FinancialReport.currency, FinancialLine.line_name, FinancialLine.value,
        )
        .join(FinancialReport, FinancialReport.company_id == Company.id)
        .join(FinancialLine, FinancialLine.report_id == FinancialReport.id)
        .order_by(Company.code, FinancialReport.year, FinancialLine.sort_order)
        .limit(limit)
    )
    if company_ids is not None:
        q = q.where(Company.id.in_(company_ids))
    if year is not None:
        q = q.where(FinancialReport.year == year)
    if standard:
        q = q.where(FinancialReport.standard == standard.upper())
    out = []
    for r in (await db.execute(q)).all():
        m = r._mapping
        out.append({
            "company": m["name_short"] or m["name_ru"], "company_code": m["code"],
            "year": m["year"], "standard": m["standard"], "report_type": m["report_type"],
            "currency": m["currency"], "article": m["line_name"], "value": _num(m["value"]),
        })
    return out


# ──────────────────────────── Проекты ────────────────────────────

async def _fetch_projects(db: AsyncSession, *, company_ids=None, year=None, limit=3000, **_):
    q = (
        select(
            Company.code, Company.name_short, Company.name_ru,
            Project.title, Project.status, Project.priority,
            Project.due_date, Project.progress_percent, Project.portfolio_year,
        )
        .join(Company, Company.id == Project.company_id)
        .where(Project.is_archived == False)  # noqa: E712
        .order_by(Company.code, Project.portfolio_year.desc())
        .limit(limit)
    )
    if company_ids is not None:
        q = q.where(Company.id.in_(company_ids))
    if year is not None:
        q = q.where(Project.portfolio_year == year)
    out = []
    for r in (await db.execute(q)).all():
        m = r._mapping
        out.append({
            "company": m["name_short"] or m["name_ru"], "company_code": m["code"],
            "title": m["title"], "status": m["status"], "priority": m["priority"],
            "due_date": m["due_date"].isoformat() if m["due_date"] else None,
            "progress_pct": _num(m["progress_percent"]), "year": m["portfolio_year"],
        })
    return out


# ──────────────────────────── Задачи ────────────────────────────

async def _fetch_tasks(db: AsyncSession, *, company_ids=None, year=None, limit=3000, **_):
    q = (
        select(
            Company.code, Company.name_short, Company.name_ru,
            Task.title, Task.status, Task.priority, Task.due_date, Task.portfolio_year,
        )
        .join(Company, Company.id == Task.company_id)
        .where(Task.is_archived == False)  # noqa: E712
        .order_by(Company.code, Task.portfolio_year.desc())
        .limit(limit)
    )
    if company_ids is not None:
        q = q.where(Company.id.in_(company_ids))
    if year is not None:
        q = q.where(Task.portfolio_year == year)
    out = []
    for r in (await db.execute(q)).all():
        m = r._mapping
        out.append({
            "company": m["name_short"] or m["name_ru"], "company_code": m["code"],
            "title": m["title"], "status": m["status"], "priority": m["priority"],
            "due_date": m["due_date"].isoformat() if m["due_date"] else None,
            "year": m["portfolio_year"],
        })
    return out


# ──────────────────────────── Рейтинги ────────────────────────────

async def _fetch_ratings(db: AsyncSession, *, company_ids=None, limit=2000, **_):
    q = (
        select(
            Company.code, Company.name_short, Company.name_ru,
            AgencyRating.agency, AgencyRating.rating, AgencyRating.outlook,
            AgencyRating.score, AgencyRating.is_esg, AgencyRating.rating_date,
        )
        .join(Company, Company.id == AgencyRating.company_id)
        .order_by(Company.code, AgencyRating.agency)
        .limit(limit)
    )
    if company_ids is not None:
        q = q.where(Company.id.in_(company_ids))
    out = []
    for r in (await db.execute(q)).all():
        m = r._mapping
        out.append({
            "company": m["name_short"] or m["name_ru"], "company_code": m["code"],
            "agency": m["agency"], "rating": m["rating"], "outlook": m["outlook"],
            "score": _num(m["score"]), "type": "ESG" if m["is_esg"] else "credit",
            "rating_date": m["rating_date"].isoformat() if m["rating_date"] else None,
        })
    return out


# ──────────────────────────── Реестр ────────────────────────────

SOURCES: dict[str, dict] = {
    "kpi": {
        "label": "KPI-метрики",
        "permission": "kpi.view",
        "columns": ["company", "company_code", "year", "manager", "indicator", "unit", "weight", "plan", "fact", "pct"],
        "filters": ["company", "year"],
        "fetch": _fetch_kpi,
    },
    "financials": {
        "label": "Финансовая отчётность",
        "permission": "financials.view",
        "columns": ["company", "company_code", "year", "standard", "report_type", "currency", "article", "value"],
        "filters": ["company", "year", "standard"],
        "fetch": _fetch_financials,
    },
    "projects": {
        "label": "Проекты",
        "permission": "tasks.view",
        "columns": ["company", "company_code", "title", "status", "priority", "due_date", "progress_pct", "year"],
        "filters": ["company", "year"],
        "fetch": _fetch_projects,
    },
    "tasks": {
        "label": "Задачи",
        "permission": "tasks.view",
        "columns": ["company", "company_code", "title", "status", "priority", "due_date", "year"],
        "filters": ["company", "year"],
        "fetch": _fetch_tasks,
    },
    "ratings": {
        "label": "Рейтинги агентств",
        "permission": "ratings.view",
        "columns": ["company", "company_code", "agency", "rating", "outlook", "score", "type", "rating_date"],
        "filters": ["company"],
        "fetch": _fetch_ratings,
    },
}


def catalog() -> list[dict]:
    """Описание источников для UI конструктора (без fetch)."""
    return [
        {"key": k, "label": s["label"], "columns": s["columns"], "filters": s["filters"], "permission": s["permission"]}
        for k, s in SOURCES.items()
    ]


async def run_source(
    db: AsyncSession, source: str, *,
    company_ids: Optional[list[UUID]] = None,
    year: Optional[int] = None,
    standard: Optional[str] = None,
    columns: Optional[list[str]] = None,
    limit: int = 2000,
) -> list[dict]:
    """Выполнить источник с фильтрами; опционально — проекция колонок."""
    src = SOURCES.get(source)
    if src is None:
        raise KeyError(source)
    rows = await src["fetch"](db, company_ids=company_ids, year=year, standard=standard, limit=limit)
    if columns:
        cols = [c for c in columns if c in src["columns"]]
        if cols:
            rows = [{c: r.get(c) for c in cols} for r in rows]
    return rows
