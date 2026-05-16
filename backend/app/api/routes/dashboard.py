"""Shareholder Dashboard — Phase 14 stage 2: ratings + completion chart.

Extends the previous /dashboard/shareholder endpoint with two new sections:
  - ratings: 4 agency rings (Fitch / S&P / Moody's / Sustainable ESG)
             + per-company table rows
  - completion_chart: per-company progress for the bar chart
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timezone
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import _has_permission, has_effective_permission
from app.models.agency_rating import AgencyRating
from app.models.board import Board
from app.models.company import Company, Direction, Sector
from app.models.project import Project
from app.models.task import Task
from app.models.user import User


log = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ─── Static labels ──────────────────────────────────────────────────
_DIRS = [
    {"id": "strategy",    "label": "Стратегическое управление",  "color": "#1e2787"},
    {"id": "finance",     "label": "Финансы / риски / аудит",    "color": "#D97706"},
    {"id": "procurement", "label": "Система закупок",            "color": "#3B6D11"},
    {"id": "orgdev",      "label": "Организационное развитие",   "color": "#534AB7"},
    {"id": "digital",     "label": "Цифровизация",               "color": "#1D9E75"},
    {"id": "operations",  "label": "Операционная эффективность", "color": "#EF4444"},
    {"id": "governance",  "label": "Корпоративное управление",   "color": "#72243E"},
    {"id": "esg",         "label": "ESG",                        "color": "#1D9E75"},
    {"id": "pr",          "label": "Связи с общественностью",    "color": "#D4537E"},
    {"id": "pmo",         "label": "PMO",                        "color": "#2563EB"},
    {"id": "analytics",   "label": "Сводный отдел",              "color": "#7C3AED"},
]

_SECTOR_ORDER = ["mining_metallurgy", "oil_gas", "energy", "transport_communications", "other"]
_SECTOR_LABELS = {
    "mining_metallurgy":    "Горнодобывающий",
    "oil_gas":    "Нефтегазовый",
    "energy":    "Энергетика",
    "transport_communications": "Транспорт и коммуникации",
    "other":     "Другой сектор",
}
_SECTOR_COLORS = {
    "mining_metallurgy":    "#9B8EC4",
    "oil_gas":    "#0A7B5E",
    "energy":    "#EF9F27",
    "transport_communications": "#378ADD",
    "other":     "#888780",
}

# Rating agencies — names match what's in DB and what the dashboard displays
_AGENCIES_CREDIT = ["Fitch", "S&P", "Moody's"]
_AGENCY_ESG = "Sustainable Fitch"  # primary ESG ring
_AGENCY_LABELS = {
    "Fitch":             "FITCH RATINGS",
    "S&P":               "S&P GLOBAL",
    "Moody's":           "MOODY'S",
    "Sustainable Fitch": "ESG",
}
_AGENCY_COLORS = {
    "Fitch":             "#1D9E75",
    "S&P":               "#E24B4A",
    "Moody's":           "#7F77DD",
    "Sustainable Fitch": "#1D9E75",
}


def _is_overdue(due: Optional[date], status: str) -> bool:
    if not due or status == "done":
        return False
    return due < datetime.now(timezone.utc).date()


# ─── Endpoint ────────────────────────────────────────────────────────

@router.get("/shareholder")
async def shareholder_dashboard(
    year: Optional[int] = Query(None),
    sector_code: Optional[str] = Query(None),
    direction_code: Optional[str] = Query(None),
    company_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")

    # ─── Available years ─────────────────────────────────────────
    yrs_q = await db.execute(
        select(Task.portfolio_year).distinct()
        .where(Task.portfolio_year.is_not(None))
    )
    available_years = sorted({y for (y,) in yrs_q.all() if y}, reverse=True)

    # ─── Load projects + tasks (year-filtered) ───────────────────
    p_q = (select(
            Project.id, Project.status, Project.due_date, Project.direction_id,
            Project.board_id, Project.linked_year, Project.portfolio_year,
        ).where(Project.is_archived == False))  # noqa: E712
    t_q = (select(
            Task.id, Task.status, Task.due_date, Task.direction_id,
            Task.board_id, Task.linked_year, Task.portfolio_year,
        ).where(Task.is_archived == False))  # noqa: E712
    if year:
        p_q = p_q.where(Project.portfolio_year == year)
        t_q = t_q.where(Task.portfolio_year == year)

    # === Filter: sector_code / company_code -> filter by company_id via boards ===
    allowed_company_ids: Optional[set] = None
    if sector_code or company_code:
        co_filter_q = select(Company.id).outerjoin(Sector, Sector.id == Company.sector_id)
        if sector_code:
            co_filter_q = co_filter_q.where(Sector.code == sector_code)
        if company_code:
            co_filter_q = co_filter_q.where(Company.code == company_code)
        co_filter_rows = (await db.execute(co_filter_q)).all()
        allowed_company_ids = {row[0] for row in co_filter_rows}
        if not allowed_company_ids:
            allowed_company_ids = {None}  # impossible match -> empty result

        # board_ids matching allowed_company_ids
        b_filter_q = select(Board.id).where(Board.company_id.in_(allowed_company_ids))
        b_filter_rows = (await db.execute(b_filter_q)).all()
        allowed_board_ids = {row[0] for row in b_filter_rows} or {None}

        p_q = p_q.where(Project.board_id.in_(allowed_board_ids))
        t_q = t_q.where(Task.board_id.in_(allowed_board_ids))

    # === Filter: direction_code -> filter by direction_id ===
    if direction_code:
        dir_filter_q = select(Direction.id).where(Direction.code == direction_code)
        dir_filter_rows = (await db.execute(dir_filter_q)).all()
        allowed_dir_ids = {row[0] for row in dir_filter_rows} or {None}
        p_q = p_q.where(Project.direction_id.in_(allowed_dir_ids))
        t_q = t_q.where(Task.direction_id.in_(allowed_dir_ids))

    p_rows = (await db.execute(p_q)).all()
    t_rows = (await db.execute(t_q)).all()

    # Boards → company → sector lookup
    b_q = (select(Board.id, Board.name, Board.company_id))
    b_rows = (await db.execute(b_q)).all()
    board_to_company: dict[Any, Any] = {bid: cid for bid, _, cid in b_rows}

    co_q = await db.execute(
        select(Company.id, Company.code, Company.name_short, Company.name_ru, Sector.code)
        .outerjoin(Sector, Sector.id == Company.sector_id)
    )
    co_rows = co_q.all()
    co_to_meta: dict[Any, dict] = {
        cid: {"code": code, "name_short": ns, "name_ru": nr,
              "sector": sec or "other", "id": cid}
        for cid, code, ns, nr, sec in co_rows
    }

    # ─── KPIs ────────────────────────────────────────────────────
    done_proj = sum(1 for r in p_rows if r.status == "done")
    active_proj = sum(1 for r in p_rows if r.status == "active")
    overdue_proj = sum(1 for r in p_rows if _is_overdue(r.due_date, r.status))
    deferred_proj = sum(1 for r in p_rows if r.linked_year is not None)
    done_tasks = sum(1 for r in t_rows if r.status == "done")
    active_tasks = sum(1 for r in t_rows if r.status == "active")
    overdue_tasks = sum(1 for r in t_rows if _is_overdue(r.due_date, r.status))
    deferred_tasks = sum(1 for r in t_rows if r.linked_year is not None)

    kpis = {
        "projects":       len(p_rows),
        "tasks":          len(t_rows),
        "done_proj":      done_proj,
        "done_tasks":     done_tasks,
        "active_proj":    active_proj,
        "active_tasks":   active_tasks,
        "overdue_proj":   overdue_proj,
        "overdue_tasks":  overdue_tasks,
        "deferred_proj":  deferred_proj,
        "deferred_tasks": deferred_tasks,
    }

    # ─── Status distribution ─────────────────────────────────────
    STATUS_DEFS = [
        ("init",      "Инициирование",    "#7F77DD"),
        ("new",       "Не начато",        "#CBD5E1"),
        ("active",    "В процессе",       "#378ADD"),
        ("review",    "На согласовании",  "#EF9F27"),
        ("done",      "Завершено",        "#1D9E75"),
        ("quarterly", "Ежеквартально",    "#A855F7"),
        ("monthly",   "Ежемесячно",       "#A855F7"),
        ("ongoing",   "Постоянно",        "#A855F7"),
    ]
    statuses = []
    for sid, label, color in STATUS_DEFS:
        pc = sum(1 for r in p_rows if r.status == sid)
        tc = sum(1 for r in t_rows if r.status == sid)
        if pc == 0 and tc == 0:
            continue
        statuses.append({
            "id": sid, "label": label, "color": color,
            "projects_count": pc, "tasks_count": tc,
        })
    statuses.append({
        "id": "overdue", "label": "Просрочено", "color": "#E24B4A",
        "projects_count": overdue_proj, "tasks_count": overdue_tasks,
    })

    # ─── Companies × sectors ─────────────────────────────────────
    co_buckets: dict[Any, dict] = {}
    for r in p_rows:
        if r.board_id is None: continue
        cid = board_to_company.get(r.board_id)
        if cid is None: continue
        b = co_buckets.setdefault(cid, {
            "projects_total": 0, "projects_done": 0,
            "tasks_total": 0, "tasks_done": 0,
        })
        b["projects_total"] += 1
        if r.status == "done": b["projects_done"] += 1
    for r in t_rows:
        if r.board_id is None: continue
        cid = board_to_company.get(r.board_id)
        if cid is None: continue
        b = co_buckets.setdefault(cid, {
            "projects_total": 0, "projects_done": 0,
            "tasks_total": 0, "tasks_done": 0,
        })
        b["tasks_total"] += 1
        if r.status == "done": b["tasks_done"] += 1

    sector_groups: dict[str, list] = {s: [] for s in _SECTOR_ORDER}
    for cid, meta in co_to_meta.items():
        bucket = co_buckets.get(cid)
        if not bucket: continue
        sector = meta["sector"] if meta["sector"] in sector_groups else "other"
        total = bucket["tasks_total"]
        prog = round(bucket["tasks_done"] / total * 100) if total else 0
        sector_groups[sector].append({
            "code":           meta["code"],
            "name":           meta["name_short"] or meta["name_ru"],
            "company_id":     str(meta["id"]),
            "projects_total": bucket["projects_total"],
            "projects_done":  bucket["projects_done"],
            "tasks_total":    bucket["tasks_total"],
            "tasks_done":     bucket["tasks_done"],
            "progress_pct":   prog,
        })
    for sec in sector_groups:
        sector_groups[sec].sort(key=lambda c: -c["progress_pct"])

    companies_by_sector = []
    for sec in _SECTOR_ORDER:
        # show all sectors even if empty
        companies_by_sector.append({
            "sector":       sec,
            "sector_label": _SECTOR_LABELS[sec],
            "sector_color": _SECTOR_COLORS[sec],
            "companies":    sector_groups[sec],
        })

    # ─── Directions ──────────────────────────────────────────────
    dir_q = await db.execute(select(Direction.id, Direction.code))
    dir_to_code: dict[Any, str] = {did: dcode for did, dcode in dir_q.all()}

    dir_buckets: dict[str, dict] = {}
    for r in p_rows:
        code = dir_to_code.get(r.direction_id)
        if not code: continue
        b = dir_buckets.setdefault(code, {
            "projects_total": 0, "projects_done": 0,
            "tasks_total": 0, "tasks_done": 0,
        })
        b["projects_total"] += 1
        if r.status == "done": b["projects_done"] += 1
    for r in t_rows:
        code = dir_to_code.get(r.direction_id)
        if not code: continue
        b = dir_buckets.setdefault(code, {
            "projects_total": 0, "projects_done": 0,
            "tasks_total": 0, "tasks_done": 0,
        })
        b["tasks_total"] += 1
        if r.status == "done": b["tasks_done"] += 1

    directions = []
    for d in _DIRS:
        b = dir_buckets.get(d["id"])
        if not b: continue
        total = b["tasks_total"]
        prog = round(b["tasks_done"] / total * 100) if total else 0
        directions.append({
            "id":             d["id"],
            "label":          d["label"],
            "color":          d["color"],
            "projects_total": b["projects_total"],
            "projects_done":  b["projects_done"],
            "tasks_total":    b["tasks_total"],
            "tasks_done":     b["tasks_done"],
            "progress_pct":   prog,
        })
    directions.sort(key=lambda d: -d["progress_pct"])

    # ─── Ratings (Phase 14b) ─────────────────────────────────────
    # Load all ratings — group by company × agency, taking latest
    r_q = await db.execute(
        select(AgencyRating.company_id, AgencyRating.agency,
               AgencyRating.rating, AgencyRating.score,
               AgencyRating.rating_date, AgencyRating.is_esg)
        .order_by(AgencyRating.rating_date.desc().nullslast())
    )
    rating_rows = r_q.all()

    # company_id → { agency: {rating, score, date, is_esg} }
    co_to_ratings: dict[Any, dict] = {}
    for cid, agency, rating, score, rdate, is_esg in rating_rows:
        co_to_ratings.setdefault(cid, {})
        if agency not in co_to_ratings[cid]:  # take first (latest) per agency
            co_to_ratings[cid][agency] = {
                "rating": rating, "score": score, "date": rdate.isoformat() if rdate else None,
                "is_esg": is_esg,
            }

    # Build 4 agency rings: Fitch / S&P / Moody's / Sustainable Fitch (or first ESG)
    total_companies = len(co_to_meta)
    ring_data = []
    for agency_name in [*_AGENCIES_CREDIT, _AGENCY_ESG]:
        covered = sum(1 for cid in co_to_meta if co_to_ratings.get(cid, {}).get(agency_name))
        pct = round(covered / total_companies * 100) if total_companies else 0
        ring_data.append({
            "agency":    agency_name,
            "label":     _AGENCY_LABELS.get(agency_name, agency_name),
            "color":     _AGENCY_COLORS.get(agency_name, "#7F77DD"),
            "covered":   covered,
            "total":     total_companies,
            "pct":       pct,
        })

    # Credit rating numeric scale (higher = better)
    CREDIT_SCALE = {
        "AAA": 22, "AA+": 21, "AA": 20, "AA-": 19,
        "A+": 18, "A": 17, "A-": 16,
        "BBB+": 15, "BBB": 14, "BBB-": 13,
        "BB+": 12, "BB": 11, "BB-": 10,
        "B+": 9, "B": 8, "B-": 7,
        "CCC+": 6, "CCC": 5, "CCC-": 4,
        "CC": 3, "C": 2, "D": 1,
    }
    def _credit_rank(rating_obj):
        if not rating_obj or not rating_obj.get("rating"):
            return 0
        r = rating_obj["rating"].strip()
        return CREDIT_SCALE.get(r, 0)

    def _best_credit_rank(row):
        return max(
            _credit_rank(row.get("fitch")),
            _credit_rank(row.get("sp")),
            _credit_rank(row.get("moody")),
        )

    def _best_esg_score(row):
        scores = []
        for k in ("sf", "sp_esg", "cdp"):
            v = row.get(k)
            if v and v.get("score") is not None:
                try:
                    scores.append(float(v["score"]))
                except (ValueError, TypeError):
                    pass
        return max(scores) if scores else 0

    def _best_credit_label(row):
        # Return rating label of the highest-rank agency
        best_r = 0
        best_label = None
        for ag_key in ("fitch", "sp", "moody"):
            v = row.get(ag_key)
            r = _credit_rank(v)
            if r > best_r:
                best_r = r
                best_label = v["rating"]
        return best_label

    # Build per-company table rows (grouped by sector)
    rating_groups: dict[str, list] = {s: [] for s in _SECTOR_ORDER}
    for cid, meta in co_to_meta.items():
        ratings_for_co = co_to_ratings.get(cid, {})
        sector = meta["sector"] if meta["sector"] in rating_groups else "other"
        rating_groups[sector].append({
            "code":    meta["code"],
            "name":    meta["name_short"] or meta["name_ru"],
            "fitch":   ratings_for_co.get("Fitch"),
            "sp":      ratings_for_co.get("S&P"),
            "moody":   ratings_for_co.get("Moody's"),
            "sf":      ratings_for_co.get("Sustainable Fitch"),
            "sp_esg":  ratings_for_co.get("S&P ESG"),
            "cdp":     ratings_for_co.get("CDP"),
        })

    rating_table = []
    for sec in _SECTOR_ORDER:
        if not rating_groups[sec]: continue
        rows = rating_groups[sec]

        # Best by credit (max rank, tie-break by code)
        best_credit_idx = -1
        best_credit_score = 0
        for idx, row in enumerate(rows):
            score = _best_credit_rank(row)
            if score > best_credit_score:
                best_credit_score = score
                best_credit_idx = idx

        # Best by ESG (max score)
        best_esg_idx = -1
        best_esg_score = 0
        for idx, row in enumerate(rows):
            score = _best_esg_score(row)
            if score > best_esg_score:
                best_esg_score = score
                best_esg_idx = idx

        # Mark rows
        best_credit = None
        best_esg = None
        for idx, row in enumerate(rows):
            row["is_best_credit"] = (idx == best_credit_idx and best_credit_score > 0)
            row["is_best_esg"] = (idx == best_esg_idx and best_esg_score > 0)
            if row["is_best_credit"]:
                best_credit = {
                    "code": row["code"],
                    "name": row["name"],
                    "rating": _best_credit_label(row),
                }
            if row["is_best_esg"]:
                best_esg = {
                    "code": row["code"],
                    "name": row["name"],
                    "score": int(best_esg_score),
                }

        rating_table.append({
            "sector":       sec,
            "sector_label": _SECTOR_LABELS[sec],
            "sector_color": _SECTOR_COLORS[sec],
            "rows":         rows,
            "best_credit":  best_credit,
            "best_esg":     best_esg,
        })

    ratings = {
        "rings":         ring_data,
        "table":         rating_table,
        "total_companies": total_companies,
    }

    # ─── Completion chart per company (Phase 14b) ────────────────
    # Re-use co_buckets + co_to_meta to build sortable chart series
    completion_chart = []
    sector_avg_buckets: dict[str, dict] = {s: {"done": 0, "total": 0} for s in _SECTOR_ORDER}
    for cid, meta in co_to_meta.items():
        bucket = co_buckets.get(cid)
        if not bucket: continue
        total = bucket["tasks_total"]
        done = bucket["tasks_done"]
        prog = round(done / total * 100) if total else 0
        sector = meta["sector"] if meta["sector"] in sector_avg_buckets else "other"
        sector_avg_buckets[sector]["done"] += done
        sector_avg_buckets[sector]["total"] += total
        completion_chart.append({
            "code":         meta["code"],
            "name":         meta["name_short"] or meta["name_ru"],
            "sector":       sector,
            "sector_color": _SECTOR_COLORS[sector],
            "tasks_total":  total,
            "tasks_done":   done,
            "progress_pct": prog,
            "projects_total": bucket["projects_total"],
            "projects_done":  bucket["projects_done"],
        })
    completion_chart.sort(key=lambda c: -c["progress_pct"])

    # Sector averages for "By sector" view
    completion_by_sector = []
    for sec in _SECTOR_ORDER:
        b = sector_avg_buckets.get(sec, {"done": 0, "total": 0})
        if b["total"] == 0: continue
        completion_by_sector.append({
            "sector":       sec,
            "sector_label": _SECTOR_LABELS[sec],
            "sector_color": _SECTOR_COLORS[sec],
            "tasks_total":  b["total"],
            "tasks_done":   b["done"],
            "progress_pct": round(b["done"] / b["total"] * 100) if b["total"] else 0,
        })
    completion_by_sector.sort(key=lambda c: -c["progress_pct"])

    # Overall portfolio average
    total_done = sum(b["tasks_done"] for b in co_buckets.values())
    total_tasks = sum(b["tasks_total"] for b in co_buckets.values())
    portfolio_avg = round(total_done / total_tasks * 100) if total_tasks else 0

    return {
        "kpis":                kpis,
        "statuses":            statuses,
        "companies_by_sector": companies_by_sector,
        "directions":          directions,
        "ratings":             ratings,
        "completion": {
            "by_company":    completion_chart,
            "by_sector":     completion_by_sector,
            "portfolio_avg": portfolio_avg,
        },
        "available_years":     available_years,
        "selected_year":       year,
    }


# ════════════════════════════════════════════════════════════════════════
# Pack 7.46 — KPI tile drill-down (DirectionDrillModal-style nested response)
# ════════════════════════════════════════════════════════════════════════
#
# GET /dashboard/kpi-drill
#   bucket  = total | done | active | overdue | deferred
#   entity  = projects | tasks   (affects hero number + sort order)
#   year    = portfolio year filter (optional)
#   sector_code, direction_code, company_code = optional filters
#
# Returns nested structure grouping items by company:
#   {
#     bucket, entity, year, label, title,
#     summary: {
#       projects_count, tasks_count,         # matching bucket
#       projects_total_all, tasks_total_all, # grand totals
#       companies_count, assignees_count,
#       extra_value, extra_label             # bucket-specific 4th KPI
#     },
#     companies: [ {
#       company_id, company_code, company_name, sector,
#       projects_count, tasks_count,         # matching bucket
#       projects_total, tasks_total,         # company grand totals
#       overdue_tasks,                        # always shown
#       projects: [ {id, title, status, due_date, is_overdue,
#                    days_overdue, progress_percent, assignee_name, num} ],
#       tasks:    [ ... same shape ... ]
#     } ]
#   }

_BUCKET_LABEL = {
    "total":    "ВСЕГО",
    "done":     "ЗАВЕРШЕНО",
    "active":   "В ПРОЦЕССЕ",
    "overdue":  "ПРОСРОЧЕНО",
    "deferred": "ПЕРЕНЕСЕНО",
}
_BUCKET_TITLE = {
    "total":    "Все элементы портфеля",
    "done":     "Завершённые элементы",
    "active":   "Элементы в процессе исполнения",
    "overdue":  "Просроченные элементы",
    "deferred": "Перенесённые элементы",
}
_BUCKET_ACCENT = {
    "total":    "#7F77DD",
    "done":     "#1D9E75",
    "active":   "#EF9F27",
    "overdue":  "#E24B4A",
    "deferred": "#7F77DD",
}

# Sector color map (matches DirectionDrillModal)
_DDM_SECTOR_COLOR = {
    "mining_metallurgy":         "#7F77DD",
    "oil_gas":                   "#1D9E75",
    "energy":                    "#EF9F27",
    "transport_communications":  "#378ADD",
    "other":                     "#888780",
}


def _matches_bucket(status: str, due_date, linked_year, today: date, bucket: str) -> bool:
    if bucket == "total":
        return True
    if bucket == "done":
        return status == "done"
    if bucket == "active":
        return status == "active"
    if bucket == "overdue":
        return due_date is not None and due_date < today and status != "done"
    if bucket == "deferred":
        return linked_year is not None
    return False


@router.get("/kpi-drill")
async def kpi_tile_drill(
    bucket: str = Query(..., regex="^(total|done|active|overdue|deferred)$"),
    entity: str = Query("tasks", regex="^(projects|tasks)$"),
    year: Optional[int] = Query(None),
    sector_code: Optional[str] = Query(None),
    direction_code: Optional[str] = Query(None),
    company_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """KPI-tile drill-down: nested response grouped by company.
    Mirrors DirectionDrillModal data shape (Pack 7.46)."""
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")

    today = datetime.now(timezone.utc).date()

    # ─── Load all projects + tasks (year-filtered) ───────────────
    p_q = (select(
        Project.id, Project.num, Project.title, Project.status, Project.priority,
        Project.due_date, Project.linked_year, Project.portfolio_year,
        Project.progress_percent, Project.assignee_name, Project.assignee_email,
        Project.board_id, Project.direction_id,
    ).where(Project.is_archived == False))  # noqa: E712
    t_q = (select(
        Task.id, Task.num, Task.title, Task.status, Task.priority,
        Task.due_date, Task.linked_year, Task.portfolio_year,
        Task.progress_percent, Task.assignee_name, Task.assignee_email,
        Task.board_id, Task.direction_id,
    ).where(Task.is_archived == False))  # noqa: E712
    if year:
        p_q = p_q.where(Project.portfolio_year == year)
        t_q = t_q.where(Task.portfolio_year == year)

    # ─── Company / sector / direction filters (pre-apply) ─────────
    if sector_code or company_code:
        co_filter_q = select(Company.id).outerjoin(Sector, Sector.id == Company.sector_id)
        if sector_code:
            co_filter_q = co_filter_q.where(Sector.code == sector_code)
        if company_code:
            co_filter_q = co_filter_q.where(Company.code == company_code)
        co_rows = (await db.execute(co_filter_q)).all()
        co_ids = {r[0] for r in co_rows} or {None}
        b_rows = (await db.execute(
            select(Board.id).where(Board.company_id.in_(co_ids))
        )).all()
        b_ids = {r[0] for r in b_rows} or {None}
        p_q = p_q.where(Project.board_id.in_(b_ids))
        t_q = t_q.where(Task.board_id.in_(b_ids))

    if direction_code:
        dir_rows = (await db.execute(
            select(Direction.id).where(Direction.code == direction_code)
        )).all()
        d_ids = {r[0] for r in dir_rows} or {None}
        p_q = p_q.where(Project.direction_id.in_(d_ids))
        t_q = t_q.where(Task.direction_id.in_(d_ids))

    p_rows = (await db.execute(p_q)).all()
    t_rows = (await db.execute(t_q)).all()

    # boards → company_id lookup
    b_q = (await db.execute(select(Board.id, Board.company_id))).all()
    board_to_company: dict[Any, Any] = {bid: cid for bid, cid in b_q}

    # companies meta
    co_q = (await db.execute(
        select(Company.id, Company.code, Company.name_short, Company.name_ru, Sector.code)
        .outerjoin(Sector, Sector.id == Company.sector_id)
    )).all()
    co_meta: dict[Any, dict] = {}
    for cid, code, ns, nr, sec in co_q:
        co_meta[cid] = {
            "id":           str(cid),
            "code":         code,
            "name":         ns or nr or code,
            "sector":       sec or "other",
        }

    # ─── Group items by company ──────────────────────────────────
    # cid → { projects_total, tasks_total, projects: [], tasks: [], overdue_tasks }
    co_buckets: dict[Any, dict] = {}

    def _co_record(cid):
        rec = co_buckets.get(cid)
        if not rec:
            rec = {
                "projects_total": 0,
                "tasks_total":    0,
                "projects":       [],
                "tasks":          [],
                "overdue_tasks":  0,
                "assignees":      set(),
            }
            co_buckets[cid] = rec
        return rec

    def _item_dict(r, is_overdue: bool, days_overdue: Optional[int]) -> dict:
        return {
            "id":                str(r.id),
            "num":               r.num,
            "title":             r.title,
            "status":            r.status,
            "priority":          r.priority,
            "due_date":          r.due_date.isoformat() if r.due_date else None,
            "is_overdue":        is_overdue,
            "days_overdue":      days_overdue,
            "progress_percent":  int(r.progress_percent or 0),
            "assignee_name":     r.assignee_name,
        }

    # Project loop
    for r in p_rows:
        cid = board_to_company.get(r.board_id)
        if cid is None:
            continue
        rec = _co_record(cid)
        rec["projects_total"] += 1
        is_overdue = (r.due_date is not None and r.due_date < today and r.status != "done")
        if _matches_bucket(r.status, r.due_date, r.linked_year, today, bucket):
            d_over = (today - r.due_date).days if is_overdue else None
            rec["projects"].append(_item_dict(r, is_overdue, d_over))
            if r.assignee_email:
                rec["assignees"].add(r.assignee_email.lower())

    # Task loop
    for r in t_rows:
        cid = board_to_company.get(r.board_id)
        if cid is None:
            continue
        rec = _co_record(cid)
        rec["tasks_total"] += 1
        is_overdue = (r.due_date is not None and r.due_date < today and r.status != "done")
        if is_overdue:
            rec["overdue_tasks"] += 1
        if _matches_bucket(r.status, r.due_date, r.linked_year, today, bucket):
            d_over = (today - r.due_date).days if is_overdue else None
            rec["tasks"].append(_item_dict(r, is_overdue, d_over))
            if r.assignee_email:
                rec["assignees"].add(r.assignee_email.lower())

    # ─── Build companies array ────────────────────────────────────
    companies_out: list[dict] = []
    total_projects_match = 0
    total_tasks_match = 0
    total_projects_all = 0
    total_tasks_all = 0
    all_assignees: set = set()

    for cid, rec in co_buckets.items():
        total_projects_all += rec["projects_total"]
        total_tasks_all += rec["tasks_total"]
        # Only include companies with at least one matching item
        if not rec["projects"] and not rec["tasks"]:
            continue
        meta = co_meta.get(cid, {"id": str(cid), "code": None, "name": "—", "sector": "other"})
        total_projects_match += len(rec["projects"])
        total_tasks_match += len(rec["tasks"])
        all_assignees.update(rec["assignees"])

        # Sort items: overdue first, then by due_date asc, then by progress desc
        def _item_sort(it):
            ov = 0 if it["is_overdue"] else 1
            due = it["due_date"] or "9999-99-99"
            return (ov, due, -(it["progress_percent"] or 0))
        rec["projects"].sort(key=_item_sort)
        rec["tasks"].sort(key=_item_sort)

        companies_out.append({
            "company_id":     meta["id"],
            "company_code":   meta["code"],
            "company_name":   meta["name"],
            "sector":         meta["sector"],
            "projects_count": len(rec["projects"]),
            "tasks_count":    len(rec["tasks"]),
            "projects_total": rec["projects_total"],
            "tasks_total":    rec["tasks_total"],
            "overdue_tasks":  rec["overdue_tasks"],
            "projects":       rec["projects"],
            "tasks":          rec["tasks"],
        })

    # ─── Sort companies ───────────────────────────────────────────
    # entity=projects → by projects_count desc, tasks_count desc as tiebreaker
    # entity=tasks    → by tasks_count desc, projects_count desc as tiebreaker
    if entity == "projects":
        companies_out.sort(key=lambda c: (-c["projects_count"], -c["tasks_count"], c["company_name"]))
    else:
        companies_out.sort(key=lambda c: (-c["tasks_count"], -c["projects_count"], c["company_name"]))

    # ─── 4th KPI (bucket-specific) ────────────────────────────────
    extra_value: int = 0
    extra_label: str = ""
    if bucket == "overdue":
        # Critical = days_overdue >= 30
        crit = sum(
            1 for c in companies_out
            for it in (c["tasks"] if entity == "tasks" else c["projects"])
            if (it["days_overdue"] or 0) >= 30
        )
        extra_value = crit
        extra_label = "критичных свыше 30 дней"
    elif bucket == "done":
        # In-time = done items whose due_date >= completed_at-equivalent; we approximate as not-overdue
        in_time = sum(
            1 for c in companies_out
            for it in (c["tasks"] if entity == "tasks" else c["projects"])
            if not it["is_overdue"]
        )
        extra_value = in_time
        extra_label = "в срок"
    elif bucket == "active":
        # Active items that are also overdue
        ov = sum(
            1 for c in companies_out
            for it in (c["tasks"] if entity == "tasks" else c["projects"])
            if it["is_overdue"]
        )
        extra_value = ov
        extra_label = "из них просрочено"
    elif bucket == "deferred":
        # Items linked to future year (linked_year > current)
        # We don't have linked_year in item dict; approximate as count of overdue
        extra_value = sum(c["overdue_tasks"] for c in companies_out)
        extra_label = "просроченных задач"
    else:  # total
        extra_value = sum(c["overdue_tasks"] for c in companies_out)
        extra_label = "просроченных задач"

    return {
        "bucket":  bucket,
        "entity":  entity,
        "year":    year,
        "label":   _BUCKET_LABEL.get(bucket, bucket.upper()),
        "title":   _BUCKET_TITLE.get(bucket, bucket),
        "accent":  _BUCKET_ACCENT.get(bucket, "#7F77DD"),
        "sector_color_map": _DDM_SECTOR_COLOR,
        "summary": {
            "projects_count":     total_projects_match,
            "tasks_count":        total_tasks_match,
            "projects_total_all": total_projects_all,
            "tasks_total_all":    total_tasks_all,
            "companies_count":    len(companies_out),
            "assignees_count":    len(all_assignees),
            "extra_value":        extra_value,
            "extra_label":        extra_label,
        },
        "companies": companies_out,
    }


# ════════════════════════════════════════════════════════════════════════
# Pack 7.47 — Company tile drill-down ("Проекты по компаниям" block)
# ════════════════════════════════════════════════════════════════════════
#
# GET /dashboard/company-drill
#   company_code = required — short code of the company (e.g. "NUR")
#   year         = portfolio year filter (optional)
#
# Returns:
#   {
#     company:  { code, name, sector, sector_label, sector_color },
#     year, accent,
#     summary: {
#       progress_pct, projects_total, projects_done, projects_active,
#       projects_overdue, tasks_total, tasks_done, tasks_active,
#       tasks_overdue, assignees_count
#     },
#     projects: [ { id, num, title, status, priority, due_date, is_overdue,
#                   days_overdue, progress_percent, assignee_name } ],
#     tasks:    [ ... same shape ... ]
#   }
#
# Used by CompanyTileDrillModal.vue (clicks on company rows in
# "Проекты по компаниям" block of main Dashboard).

@router.get("/company-drill")
async def company_tile_drill(
    company_code: str = Query(...),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Single-company drill: flat projects + tasks with summary + status counts."""
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")

    today = datetime.now(timezone.utc).date()

    # ─── Resolve company by code ───────────────────────────────────
    co_q = await db.execute(
        select(
            Company.id, Company.code, Company.name_short, Company.name_ru,
            Sector.code,
        )
        .outerjoin(Sector, Sector.id == Company.sector_id)
        .where(Company.code == company_code)
    )
    co_row = co_q.first()
    if not co_row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Company '{company_code}' not found")

    cid, code, ns, nr, sec_code = co_row
    sec_code = sec_code or "other"

    # ─── Boards of this company ────────────────────────────────────
    b_rows = (await db.execute(
        select(Board.id).where(Board.company_id == cid)
    )).all()
    b_ids = {r[0] for r in b_rows}
    if not b_ids:
        b_ids = {None}  # impossible match -> empty result

    # ─── Load projects + tasks ─────────────────────────────────────
    p_q = (select(
        Project.id, Project.num, Project.title, Project.status, Project.priority,
        Project.due_date, Project.linked_year, Project.portfolio_year,
        Project.progress_percent, Project.assignee_name, Project.assignee_email,
        Project.board_id, Project.direction_id,
    ).where(Project.is_archived == False, Project.board_id.in_(b_ids)))  # noqa: E712
    t_q = (select(
        Task.id, Task.num, Task.title, Task.status, Task.priority,
        Task.due_date, Task.linked_year, Task.portfolio_year,
        Task.progress_percent, Task.assignee_name, Task.assignee_email,
        Task.board_id, Task.direction_id,
    ).where(Task.is_archived == False, Task.board_id.in_(b_ids)))  # noqa: E712
    if year:
        p_q = p_q.where(Project.portfolio_year == year)
        t_q = t_q.where(Task.portfolio_year == year)

    p_rows = (await db.execute(p_q)).all()
    t_rows = (await db.execute(t_q)).all()

    def _item(r) -> dict:
        is_over = (r.due_date is not None and r.due_date < today and r.status != "done")
        d_over = (today - r.due_date).days if is_over else None
        return {
            "id":                str(r.id),
            "num":                r.num,
            "title":              r.title,
            "status":             r.status,
            "priority":           r.priority,
            "due_date":           r.due_date.isoformat() if r.due_date else None,
            "is_overdue":         is_over,
            "days_overdue":       d_over,
            "progress_percent":   int(r.progress_percent or 0),
            "assignee_name":      r.assignee_name,
        }

    def _sort_key(it):
        ov = 0 if it["is_overdue"] else 1
        due = it["due_date"] or "9999-99-99"
        return (ov, due, -(it["progress_percent"] or 0))

    projects = [_item(r) for r in p_rows]
    tasks    = [_item(r) for r in t_rows]
    projects.sort(key=_sort_key)
    tasks.sort(key=_sort_key)

    # ─── Summary ──────────────────────────────────────────────────
    p_done    = sum(1 for it in projects if it["status"] == "done")
    p_active  = sum(1 for it in projects if it["status"] == "active")
    p_over    = sum(1 for it in projects if it["is_overdue"])
    t_done    = sum(1 for it in tasks if it["status"] == "done")
    t_active  = sum(1 for it in tasks if it["status"] == "active")
    t_over    = sum(1 for it in tasks if it["is_overdue"])
    progress_pct = round(t_done / len(tasks) * 100) if tasks else 0

    assignees: set = set()
    for r in p_rows:
        if r.assignee_email:
            assignees.add(r.assignee_email.lower())
    for r in t_rows:
        if r.assignee_email:
            assignees.add(r.assignee_email.lower())

    # Choose accent by progress band
    if progress_pct >= 100:  accent = "#1D9E75"
    elif progress_pct >= 90: accent = "#7F77DD"
    elif progress_pct >= 75: accent = "#EF9F27"
    elif progress_pct >= 1:  accent = "#E24B4A"
    else:                    accent = "#94a3b8"

    return {
        "company": {
            "code":         code,
            "name":         ns or nr or code,
            "sector":       sec_code,
            "sector_label": _SECTOR_LABELS.get(sec_code, sec_code),
            "sector_color": _SECTOR_COLORS.get(sec_code, "#888780"),
        },
        "year":   year,
        "accent": accent,
        "summary": {
            "progress_pct":     progress_pct,
            "projects_total":   len(projects),
            "projects_done":    p_done,
            "projects_active":  p_active,
            "projects_overdue": p_over,
            "tasks_total":      len(tasks),
            "tasks_done":       t_done,
            "tasks_active":     t_active,
            "tasks_overdue":    t_over,
            "assignees_count":  len(assignees),
        },
        "projects": projects,
        "tasks":    tasks,
    }
