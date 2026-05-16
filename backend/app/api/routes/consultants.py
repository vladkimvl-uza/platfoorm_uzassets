"""Consultants & Big-4 dashboard endpoint.

Mirrors monolith showConsultantsView(): 5 sections in a single payload.

  GET /api/consultants/overview?year=2025         → full dashboard data
  GET /api/consultants                            → list of all consultancy firms
                                                    (admin/edit page support)

Source data:
  - consultants table (17 firms, 4 Big4 flagged)
  - consultant_assignments table (M:N task ↔ consultant)
  - tasks (joined for status, due_date, board, direction, portfolio_year)
  - boards / companies / sectors / directions

Permissions: requires `tasks.view`.
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.core.security import _has_permission
from app.models.board import Board
from app.models.company import Company, Direction, Sector
from app.models.consultant import Consultant, ConsultantAssignment
from app.models.task import Task
from app.models.user import User


log = logging.getLogger(__name__)
router = APIRouter(prefix="/consultants", tags=["consultants"])


# Direction labels — mirrors monolith DIRS array
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

_DIR_ID_TO_LABEL = {d["id"]: d["label"] for d in _DIRS}
_DIR_ID_TO_COLOR = {d["id"]: d["color"] for d in _DIRS}


def _is_overdue(due: Optional[date]) -> bool:
    """Match monolith isOverdue(): due is in the past."""
    if not due:
        return False
    today = datetime.now(timezone.utc).date()
    return due < today


# =====================================================================
# GET /consultants — admin list (all 17 firms)
# =====================================================================

@router.get("")
async def list_consultants(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Returns all consultancy firms ordered by sort_order then name."""
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")

    res = await db.execute(
        select(Consultant)
        .where(Consultant.is_active == True)  # noqa: E712
        .order_by(Consultant.sort_order, Consultant.name_ru)
    )
    cons = res.scalars().all()
    return {
        "consultants": [
            {
                "id": str(c.id),
                "code": c.code,
                "name": c.name_ru,
                "abbr": c.abbr,
                "color": c.color_hex,
                "is_big4": c.is_big4,
                "is_active": c.is_active,
                "sort_order": c.sort_order,
            }
            for c in cons
        ]
    }


# =====================================================================
# GET /consultants/overview — full dashboard payload
# =====================================================================

@router.get("/overview")
async def consultants_overview(
    year: Optional[int] = Query(None, description="Portfolio year filter; default = all"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Returns the full data needed to render the Consultants dashboard.

    Response shape:
      {
        "kpis": {tasks_covered, companies_covered, consultants_active, avg_completion_pct},
        "consultants": [
          {id, code, name, abbr, color, is_big4,
           tasks_total, tasks_done, tasks_overdue, completion_pct}, ...
        ],
        "heatmap": {
          "consultants": [{id, code, name, abbr, color, is_big4}, ...]    # cols
          "boards":      [{id, name, sector_color, sector_code}, ...]      # rows
          "cells":       [[count, count, ...], ...]                        # rows × cols
          "max":         <int — global max for color scale>
        },
        "dirs": [
          {id, label, color, tasks_total, tasks_done, tasks_overdue,
           completion_pct, consultant_codes: [...]}, ...
        ],
        "projects": [
          {id, num, title, board_name, status, due_date, direction_id,
           consultants: [{code, abbr, color}]}, ...
        ],
        "available_years": [2024, 2025, 2026, ...]
      }
    """
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")

    # ─── 1. Available years (for filter dropdown) ────────────────────
    yrs_q = await db.execute(
        select(Task.portfolio_year).distinct().where(Task.portfolio_year.is_not(None))
    )
    available_years = sorted({r[0] for r in yrs_q.all() if r[0]}, reverse=True)

    # ─── 2. Load all consultants ─────────────────────────────────────
    cons_q = await db.execute(
        select(Consultant)
        .where(Consultant.is_active == True)  # noqa: E712
        .order_by(Consultant.sort_order, Consultant.name_ru)
    )
    all_cons = cons_q.scalars().all()
    cons_by_id: dict[Any, Consultant] = {c.id: c for c in all_cons}
    cons_by_code: dict[str, Consultant] = {c.code: c for c in all_cons}

    # ─── 3. Load tasks WITH consultant assignments (year-filtered) ───
    t_q = (
        select(
            Task.id, Task.num, Task.title, Task.status, Task.due_date,
            Task.direction_id, Task.board_id, Task.portfolio_year,
            Task.is_archived,
        )
        .where(Task.is_archived == False)  # noqa: E712
    )
    if year:
        t_q = t_q.where(Task.portfolio_year == year)
    t_rows = (await db.execute(t_q)).all()
    task_by_id: dict[Any, dict] = {}
    for r in t_rows:
        task_by_id[r[0]] = {
            "id": r[0], "num": r[1], "title": r[2], "status": r[3],
            "due_date": r[4], "direction_id": r[5], "board_id": r[6],
            "portfolio_year": r[7],
        }

    # ─── 4. Load consultant_assignments for these tasks ──────────────
    if task_by_id:
        ca_q = await db.execute(
            select(ConsultantAssignment.task_id, ConsultantAssignment.consultant_id)
            .where(ConsultantAssignment.task_id.in_(list(task_by_id.keys())))
        )
        ca_rows = ca_q.all()
    else:
        ca_rows = []

    # task_id → set of consultant_ids
    task_to_cids: dict[Any, set] = {}
    # consultant_id → set of task_ids (reverse)
    cid_to_tids: dict[Any, set] = {c.id: set() for c in all_cons}
    for tid, cid in ca_rows:
        task_to_cids.setdefault(tid, set()).add(cid)
        cid_to_tids.setdefault(cid, set()).add(tid)

    # Tasks that have at least one consultant assigned
    consulted_task_ids = set(task_to_cids.keys())

    # ─── 5. Boards + companies (for heat map sector colours) ─────────
    if t_rows:
        board_ids = {r[6] for r in t_rows if r[6]}
    else:
        board_ids = set()
    boards_data: dict[Any, dict] = {}
    if board_ids:
        b_q = await db.execute(
            select(Board.id, Board.name, Board.company_id)
            .where(Board.id.in_(list(board_ids)))
        )
        b_rows = b_q.all()
        # sector colour via company → sector
        co_ids = {r[2] for r in b_rows if r[2]}
        co_to_sector_color: dict[Any, str] = {}
        if co_ids:
            co_q = await db.execute(
                select(Company.id, Sector.code, Sector.color_hex)
                .join(Sector, Sector.id == Company.sector_id)
                .where(Company.id.in_(list(co_ids)))
            )
            for cid, scode, scolor in co_q.all():
                co_to_sector_color[cid] = scolor or "#888"
        for bid, bname, co_id in b_rows:
            boards_data[bid] = {
                "id": str(bid),
                "name": bname,
                "sector_color": co_to_sector_color.get(co_id, "#888"),
                "company_id": co_id,
            }

    # ─── 6. KPI bar ──────────────────────────────────────────────────
    consulted_tasks = [task_by_id[tid] for tid in consulted_task_ids]
    companies_covered = len({
        boards_data.get(t["board_id"], {}).get("company_id")
        for t in consulted_tasks
        if t["board_id"]
    } - {None})

    consultants_active = sum(1 for c in all_cons if cid_to_tids.get(c.id))

    if consulted_tasks:
        done = sum(1 for t in consulted_tasks if t["status"] == "done")
        avg_completion = round(done / len(consulted_tasks) * 100)
    else:
        avg_completion = 0

    kpis = {
        "tasks_covered": len(consulted_tasks),
        "companies_covered": companies_covered,
        "consultants_active": consultants_active,
        "avg_completion_pct": avg_completion,
    }

    # ─── 7. Per-consultant stats (sorted by tasks desc, only those with >0) ─
    cons_stats: list[dict] = []
    for c in all_cons:
        tids = cid_to_tids.get(c.id, set())
        if not tids:
            continue
        tasks_total = len(tids)
        tasks_done = sum(1 for tid in tids if task_by_id[tid]["status"] == "done")
        tasks_overdue = sum(
            1 for tid in tids
            if _is_overdue(task_by_id[tid]["due_date"])
            and task_by_id[tid]["status"] != "done"
        )
        cons_stats.append({
            "id": str(c.id),
            "code": c.code,
            "name": c.name_ru,
            "abbr": c.abbr,
            "color": c.color_hex,
            "is_big4": c.is_big4,
            "tasks_total": tasks_total,
            "tasks_done": tasks_done,
            "tasks_overdue": tasks_overdue,
            "completion_pct": round(tasks_done / tasks_total * 100) if tasks_total else 0,
        })
    cons_stats.sort(key=lambda x: (-x["is_big4"], -x["tasks_total"]))

    # ─── 8. Heat map: boards × consultants (count of tasks) ──────────
    visible_cons_ids = [c["id"] for c in cons_stats]
    visible_cons_meta = cons_stats  # same order
    sorted_boards = sorted(
        boards_data.values(), key=lambda b: b["name"]
    )
    # Filter boards that actually have at least one task with consultant
    board_has_cons: dict[Any, dict] = {}
    cells: list[list[int]] = []
    g_max = 0
    for b in sorted_boards:
        b_id_obj = b["id"]
        # Find which b["id"] corresponds to UUID — heatmap key is task.board_id
        # b["id"] is str — we need original UUID for matching
        pass

    # Rebuild with UUID keys
    heatmap_rows: list[dict] = []
    for board_uuid, b_data in boards_data.items():
        row_counts: list[int] = []
        any_cell = False
        for cid_str in visible_cons_ids:
            # cid_str is str; we need consultant_id UUID
            count = 0
            try:
                cid_uuid = UUID(cid_str)
            except Exception:
                cid_uuid = cid_str
            for tid in cid_to_tids.get(cid_uuid, set()):
                if task_by_id[tid]["board_id"] == board_uuid:
                    count += 1
            if count > 0:
                any_cell = True
            if count > g_max:
                g_max = count
            row_counts.append(count)
        if any_cell:
            heatmap_rows.append({
                "board": b_data,
                "counts": row_counts,
            })
    # Sort by board name
    heatmap_rows.sort(key=lambda r: r["board"]["name"])

    heatmap = {
        "consultants": [
            {"id": c["id"], "code": c["code"], "name": c["name"],
             "abbr": c["abbr"], "color": c["color"], "is_big4": c["is_big4"]}
            for c in visible_cons_meta
        ],
        "rows": heatmap_rows,
        "max": g_max,
    }

    # ─── 9. Stats by direction ───────────────────────────────────────
    # For each DIR: count tasks (with consultant), done, overdue, distinct consultants
    dirs_q = await db.execute(select(Direction.id, Direction.code, Direction.name_ru))
    dir_rows = dirs_q.all()
    dir_id_to_meta: dict[Any, dict] = {}
    for did, dcode, dname in dir_rows:
        # Match against monolith DIRS by code
        dir_id_to_meta[did] = {
            "id": dcode,
            "label": _DIR_ID_TO_LABEL.get(dcode, dname or dcode),
            "color": _DIR_ID_TO_COLOR.get(dcode, "#888"),
        }

    dir_stats: dict[Any, dict] = {}
    for tid, cids_set in task_to_cids.items():
        t = task_by_id.get(tid)
        if not t or not t["direction_id"]:
            continue
        meta = dir_id_to_meta.get(t["direction_id"])
        if not meta:
            continue
        bucket = dir_stats.setdefault(t["direction_id"], {
            "id": meta["id"],
            "label": meta["label"],
            "color": meta["color"],
            "tasks_total": 0,
            "tasks_done": 0,
            "tasks_overdue": 0,
            "consultant_codes": set(),
        })
        bucket["tasks_total"] += 1
        if t["status"] == "done":
            bucket["tasks_done"] += 1
        if _is_overdue(t["due_date"]) and t["status"] != "done":
            bucket["tasks_overdue"] += 1
        for cid in cids_set:
            c_obj = cons_by_id.get(cid)
            if c_obj:
                bucket["consultant_codes"].add(c_obj.code)

    dirs_payload: list[dict] = []
    for v in dir_stats.values():
        dirs_payload.append({
            "id": v["id"],
            "label": v["label"],
            "color": v["color"],
            "tasks_total": v["tasks_total"],
            "tasks_done": v["tasks_done"],
            "tasks_overdue": v["tasks_overdue"],
            "completion_pct": round(v["tasks_done"] / v["tasks_total"] * 100)
                              if v["tasks_total"] else 0,
            "consultant_codes": sorted(list(v["consultant_codes"])),
        })
    dirs_payload.sort(key=lambda x: -x["completion_pct"])

    # ─── 10. Project list (last 8 tasks with consultants) ────────────
    projects_payload: list[dict] = []
    # Sort by due_date desc (or status priority)
    sorted_consulted = sorted(
        consulted_tasks,
        key=lambda t: (t["due_date"] or date(1970, 1, 1)),
        reverse=True,
    )[:20]
    for t in sorted_consulted:
        b = boards_data.get(t["board_id"]) if t["board_id"] else None
        cs_in_task = []
        for cid in task_to_cids.get(t["id"], set()):
            c_obj = cons_by_id.get(cid)
            if c_obj:
                cs_in_task.append({
                    "code": c_obj.code,
                    "abbr": c_obj.abbr,
                    "color": c_obj.color_hex,
                })
        # Resolve direction
        dir_meta = dir_id_to_meta.get(t["direction_id"]) if t["direction_id"] else None
        projects_payload.append({
            "id": str(t["id"]),
            "num": t["num"],
            "title": t["title"],
            "board_name": b["name"] if b else None,
            "status": t["status"],
            "due_date": t["due_date"].isoformat() if t["due_date"] else None,
            "direction_id": dir_meta["id"] if dir_meta else None,
            "direction_label": dir_meta["label"] if dir_meta else None,
            "consultants": cs_in_task,
        })

    return {
        "kpis": kpis,
        "consultants": cons_stats,
        "heatmap": heatmap,
        "dirs": dirs_payload,
        "projects": projects_payload,
        "available_years": available_years,
        "selected_year": year,
    }


# =====================================================================
# GET /consultants/by-company/{company_id} вЂ” per-company consultants
# Connection chain: consultants в†ђ consultant_assignments в†’ tasks (company_id)
# Added in Sprint: company workspace inline integration
# =====================================================================

@router.get("/by-company/{company_id}")
async def consultants_by_company(
    company_id: UUID,
    year: Optional[int] = Query(None, description="Portfolio year filter; default = all"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Returns consultants who work with this company through its tasks.

    A consultant is "working with" a company if any of the company's tasks
    (matched by Task.company_id) has a consultant_assignments row pointing
    to them.

    Response shape:
      {
        "company_id": "...",
        "year": 2026 | null,
        "consultants": [
          {
            "id", "code", "name", "abbr", "color", "is_big4",
            "task_count", "task_done", "task_overdue", "completion_pct",
            "sources": ["task" | "manual" | "lookup", ...],
            "projects": [{id, num, title, status, due_date}, ...]   # up to 5 sample
          }, ...
        ],
        "total_assignments": int,
        "total_consultants": int
      }

    Sort: is_big4 first, then task_count desc, then name.
    """
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    await ensure_company_access(db, user, company_id)

    # 1. Validate company exists
    co_q = await db.execute(select(Company.id).where(Company.id == company_id))
    if not co_q.scalar_one_or_none():
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "company not found")

    # 2. Tasks for this company (optionally filtered by year)
    t_q = (
        select(
            Task.id, Task.num, Task.title, Task.status, Task.due_date,
            Task.portfolio_year,
        )
        .where(Task.company_id == company_id)
        .where(Task.is_archived == False)  # noqa: E712
    )
    if year:
        t_q = t_q.where(Task.portfolio_year == year)
    t_rows = (await db.execute(t_q)).all()

    if not t_rows:
        return {
            "company_id": str(company_id),
            "year": year,
            "consultants": [],
            "total_assignments": 0,
            "total_consultants": 0,
        }

    task_by_id: dict[Any, dict] = {}
    for r in t_rows:
        task_by_id[r[0]] = {
            "id": r[0], "num": r[1], "title": r[2], "status": r[3],
            "due_date": r[4], "portfolio_year": r[5],
        }

    # 3. Get assignments for these tasks
    ca_q = await db.execute(
        select(
            ConsultantAssignment.task_id,
            ConsultantAssignment.consultant_id,
            ConsultantAssignment.source,
        )
        .where(ConsultantAssignment.task_id.in_(list(task_by_id.keys())))
    )
    ca_rows = ca_q.all()

    if not ca_rows:
        return {
            "company_id": str(company_id),
            "year": year,
            "consultants": [],
            "total_assignments": 0,
            "total_consultants": 0,
        }

    # 4. Group by consultant_id: collect tasks + sources
    cid_to_data: dict[Any, dict] = {}
    for tid, cid, src in ca_rows:
        bucket = cid_to_data.setdefault(cid, {"tasks": set(), "sources": set()})
        bucket["tasks"].add(tid)
        bucket["sources"].add(src or "task")

    # 5. Load consultant info
    cons_q = await db.execute(
        select(Consultant).where(Consultant.id.in_(list(cid_to_data.keys())))
    )
    cons_by_id: dict[Any, Consultant] = {c.id: c for c in cons_q.scalars().all()}

    # 6. Build response вЂ” per-consultant stats + sample projects
    result_list: list[dict] = []
    for cid, data in cid_to_data.items():
        c = cons_by_id.get(cid)
        if not c:
            continue
        tids = data["tasks"]
        task_count = len(tids)
        task_done = sum(
            1 for tid in tids if task_by_id[tid]["status"] == "done"
        )
        task_overdue = sum(
            1 for tid in tids
            if _is_overdue(task_by_id[tid]["due_date"])
            and task_by_id[tid]["status"] != "done"
        )
        completion_pct = round(task_done / task_count * 100) if task_count else 0

        # Sample of projects: 5 most recent by due_date
        sample_tids = sorted(
            tids,
            key=lambda tid: (task_by_id[tid]["due_date"] or date(1970, 1, 1)),
            reverse=True,
        )[:5]
        projects = []
        for tid in sample_tids:
            t = task_by_id[tid]
            projects.append({
                "id": str(t["id"]),
                "num": t["num"],
                "title": t["title"],
                "status": t["status"],
                "due_date": t["due_date"].isoformat() if t["due_date"] else None,
            })

        result_list.append({
            "id": str(c.id),
            "code": c.code,
            "name": c.name_ru,
            "abbr": c.abbr,
            "color": c.color_hex,
            "is_big4": c.is_big4,
            "task_count": task_count,
            "task_done": task_done,
            "task_overdue": task_overdue,
            "completion_pct": completion_pct,
            "sources": sorted(list(data["sources"])),
            "projects": projects,
        })

    # 7. Sort: big4 desc, task_count desc, name asc
    result_list.sort(key=lambda x: (-int(x["is_big4"]), -x["task_count"], x["name"] or ""))

    return {
        "company_id": str(company_id),
        "year": year,
        "consultants": result_list,
        "total_assignments": len(ca_rows),
        "total_consultants": len(result_list),
    }

