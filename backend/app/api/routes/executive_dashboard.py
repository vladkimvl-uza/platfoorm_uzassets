"""
backend/app/api/routes/executive_dashboard.py — Executive Dashboard endpoint.

Pack 1: Row 0 + Row 1 + bottom metrics.
Pack 2: + Row 2 — ratings (4 ring cards + table) + execution chart.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.models.company import Company, Sector
from app.models.task import Task
from app.models.user import User
from app.schemas.executive_dashboard import (
    ExecAvailableSector,
    ExecBottomMetrics,
    ExecCompanyInSector,
    ExecExecutionRow,
    ExecRatingCell,
    ExecRatingRow,
    ExecRatingsBlock,
    ExecRingCard,
    ExecSectorRow,
    ExecutiveDashboardData,
)
# Pack 4 - Row 3 helpers
from app.api.routes._pack4_blocks import (
    build_directions_block,
    build_governance_block,
    build_standards_block,
)
# Pack 5 - Row 2.55 / 2.6 / 2.7 helpers
from app.api.routes._pack5_blocks import (
    build_economic_effect_block,
    build_bp_tracker_block,
    build_tax_contribution_block,
)

# Project — опциональный
try:
    from app.models.project import Project
    _HAS_PROJECT = True
except ImportError:
    _HAS_PROJECT = False
    Project = None  # type: ignore

# Board — для company → board mapping
try:
    from app.models.board import Board
    _HAS_BOARD = True
except ImportError:
    _HAS_BOARD = False
    Board = None  # type: ignore

# AgencyRating — Pack 2. Опциональный (multi-name try chain)
_HAS_AGENCY_RATING = False
AgencyRatingModel: Any = None
for _module_name, _class_name in [
    ("app.models.agency_rating", "AgencyRating"),
    ("app.models.rating", "AgencyRating"),
    ("app.models.rating", "Rating"),
    ("app.models.ratings", "AgencyRating"),
    ("app.models.ratings", "Rating"),
]:
    try:
        _mod = __import__(_module_name, fromlist=[_class_name])
        AgencyRatingModel = getattr(_mod, _class_name)
        _HAS_AGENCY_RATING = True
        break
    except (ImportError, AttributeError):
        continue


router = APIRouter(prefix="/dashboard/executive", tags=["dashboard"])


# ─────────────────────────── Палитра ───────────────────────────
SECTOR_COLORS: Dict[str, str] = {
    "mining":    "#7F77DD",
    "oilgas":    "#1D9E75",
    "energy":    "#EF9F27",
    "transport": "#378ADD",
    "other":     "#888780",
}
SECTOR_LABEL_RU: Dict[str, str] = {
    "mining":    "Горнодобывающий",
    "oilgas":    "Нефтегазовый",
    "energy":    "Энергетика",
    "transport": "Транспорт и коммуникации",
    "other":     "Другой сектор",
}
SECTOR_ORDER: List[str] = ["mining", "oilgas", "energy", "transport", "other"]


def _sector_code(co: Optional[Company]) -> str:
    if not co or not co.sector:
        return "other"
    sec = co.sector
    code = (getattr(sec, "code", None) or "").lower().strip()
    name = (getattr(sec, "name_ru", None) or "").lower()
    if code in SECTOR_COLORS:
        return code
    if "нефт" in name or "газ" in name or "oil" in code or "gas" in code:
        return "oilgas"
    if "горн" in name or "metall" in name or "mining" in code:
        return "mining"
    if "энерг" in name or "energ" in code:
        return "energy"
    if "трансп" in name or "телек" in name or "transport" in code or "telecom" in code:
        return "transport"
    return "other"


def _sector_label(code: str, fallback: str = "") -> str:
    return SECTOR_LABEL_RU.get(code, fallback or code.title())


def _normalize_sector_code(s: str) -> str:
    """Pack 7.44: маппинг внешних кодов секторов (от frontend Dashboard.vue dropdown)
    на внутренние короткие коды backend (SECTOR_ORDER).
    
    Frontend пришлёт 'mining_metallurgy' / 'oil_gas' / 'transport_communications',
    а внутри executive_dashboard используются 'mining' / 'oilgas' / 'transport'.
    """
    if not s:
        return "other"
    if s in SECTOR_COLORS:
        return s
    low = s.lower()
    if "min" in low or "metal" in low:
        return "mining"
    if "oil" in low or "gas" in low or "нефт" in low:
        return "oilgas"
    if "energ" in low or "энерг" in low:
        return "energy"
    if "transp" in low or "comm" in low or "телек" in low or "транс" in low:
        return "transport"
    return "other"


# ─────────────────────────── Helpers Pack 2 ───────────────────────────

_MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек"]


def _format_date_short(d: Any) -> Optional[str]:
    """date | datetime → 'окт 2025' формат."""
    if not d:
        return None
    if hasattr(d, "month") and hasattr(d, "year"):
        return f"{_MONTHS_RU[d.month - 1]} {d.year}"
    return None


def _normalize_agency(name: str) -> str:
    """Нормализация имени агентства из БД к каноническому ключу."""
    s = (name or "").strip().lower()
    if "fitch" in s and ("sust" in s or "sf" in s or "esg" in s):
        return "sf"
    if "fitch" in s:
        return "fitch"
    if "moody" in s:
        return "moodys"
    if "s&p" in s and "esg" in s:
        return "sp_esg"
    if "s&p" in s or "sp" in s:
        return "sp"
    if "cdp" in s:
        return "cdp"
    return s


def _is_recent_2025_or_2026(d: Any) -> bool:
    """Был ли рейтинг получен в 2024 или ранее (для дельты)."""
    if not d or not hasattr(d, "year"):
        return False
    return d.year >= 2025


def _ring_score(rated: int, total: int) -> int:
    """Score кольца — % покрытия rounded."""
    if total <= 0:
        return 0
    return round(rated / total * 100)


# ─────────────────────────── Endpoint ───────────────────────────

# Pack 7.36 — drill modal for "По направлениям" block
# Defined BEFORE /{year} so path param matching doesn't shadow it.
from app.api.routes._pack4_drill import build_direction_drill
from app.schemas.executive_dashboard import ExecDirectionDrillResponse


@router.get(
    "/directions/{direction_code}",
    response_model=ExecDirectionDrillResponse,
)
async def direction_drill(
    direction_code: str,
    year: Optional[int] = Query(None, description="Filter by portfolio_year"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Drill-down для одного направления — список компаний с разбивкой
    проектов и задач каждой компании. Используется модалкой
    DirectionDrillModal в Executive Dashboard."""
    scope_set = None
    if not has_unrestricted_view(user):
        scope = await allowed_company_ids(db, user)
        scope_set = set(scope or [])
    try:
        return await build_direction_drill(
            db, direction_code, year=year, scope_company_ids=scope_set,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{year}", response_model=ExecutiveDashboardData)
async def executive_dashboard(
    year: int,
    sectors: Optional[List[str]] = Query(None, description="Filter: ['mining','oilgas',...]"),  # Pack 7.44: нормализуем ниже
    bp_metric: Optional[str] = Query(None, description="BP tracker metric: revenue|ebitda|profit"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Полный payload для Executive Dashboard. Pack 1 + Pack 2."""

    # ─── 1. Companies ───
    cos_q = await db.execute(
        select(Company)
        .options(selectinload(Company.sector))
        .where(Company.is_archived.is_(False) if hasattr(Company, "is_archived") else True)
    )
    all_companies: List[Company] = list(cos_q.scalars().all())

    # Scope filter: ограничиваем выдачу для юзеров без companies.view_all.
    # Применяем СРАЗУ после загрузки — все downstream-структуры строятся
    # уже на отфильтрованном списке, утечки имени/сектора чужих компаний
    # быть не может.
    if not has_unrestricted_view(user):
        scope = await allowed_company_ids(db, user)
        if not scope:
            all_companies = []
        else:
            scope_set = set(scope)
            all_companies = [co for co in all_companies if co.id in scope_set]

    total_companies = len(all_companies)
    co_sector: Dict[UUID, str] = {co.id: _sector_code(co) for co in all_companies}
    co_name: Dict[UUID, str] = {co.id: (co.name_ru or co.code or "—") for co in all_companies}

    # ─── 2. Boards ───
    co_to_board: Dict[UUID, UUID] = {}
    if _HAS_BOARD:
        try:
            boards_q = await db.execute(select(Board))
            for b in boards_q.scalars().all():
                if getattr(b, "company_id", None):
                    co_to_board[b.company_id] = b.id
        except Exception:
            co_to_board = {}

    # ─── 3. Tasks ───
    task_filters = [Task.portfolio_year == year]
    if hasattr(Task, "is_archived"):
        task_filters.append(Task.is_archived.is_(False))
    tasks_q = await db.execute(select(Task).where(*task_filters))
    tasks: List[Task] = list(tasks_q.scalars().all())

    # ─── 4. Projects ───
    projects: List[Any] = []
    if _HAS_PROJECT:
        try:
            proj_filters = []
            if hasattr(Project, "portfolio_year"):
                proj_filters.append(Project.portfolio_year == year)
            if hasattr(Project, "is_archived"):
                proj_filters.append(Project.is_archived.is_(False))
            proj_q = await db.execute(
                select(Project).where(*proj_filters) if proj_filters else select(Project)
            )
            projects = list(proj_q.scalars().all())
        except Exception:
            projects = []

    # ─── 5. Per-company task aggregates ───
    task_by_co: Dict[UUID, List[Task]] = defaultdict(list)
    for t in tasks:
        if t.company_id:
            task_by_co[t.company_id].append(t)

    co_pct: Dict[UUID, int] = {}
    co_total: Dict[UUID, int] = {}
    co_done: Dict[UUID, int] = {}
    for co_id, ts in task_by_co.items():
        total = len(ts)
        done = sum(1 for t in ts if (t.status or "").lower() == "done")
        co_pct[co_id] = round(done / total * 100) if total > 0 else 0
        co_total[co_id] = total
        co_done[co_id] = done

    # ─── 6. Sectors ───
    # Pack 7.44: нормализуем внешние коды секторов → внутренние короткие
    if sectors:
        sectors = [_normalize_sector_code(s) for s in sectors]
    sectors_out: List[ExecSectorRow] = []
    for sec_code in SECTOR_ORDER:
        if sectors and sec_code not in sectors:
            continue
        cos_in_sec = [co for co in all_companies if co_sector.get(co.id) == sec_code]
        if not cos_in_sec:
            continue
        co_rows: List[ExecCompanyInSector] = sorted(
            [
                ExecCompanyInSector(
                    company_id=co.id,
                    name=co_name[co.id],
                    pct=co_pct.get(co.id, 0),
                    board_id=co_to_board.get(co.id),
                    task_total=co_total.get(co.id, 0),
                    task_done=co_done.get(co.id, 0),
                )
                for co in cos_in_sec
            ],
            key=lambda x: (-x.pct, -x.task_done),
        )
        active_count = sum(1 for r in co_rows if r.task_total > 0)
        active_pcts = [r.pct for r in co_rows if r.task_total > 0]
        avg_pct = round(sum(active_pcts) / len(active_pcts)) if active_pcts else 0
        label_real = ""
        for co in cos_in_sec:
            if co.sector and getattr(co.sector, "name_ru", None):
                label_real = co.sector.name_ru
                break
        label = _sector_label(sec_code, label_real)
        sectors_out.append(
            ExecSectorRow(
                id=sec_code, label=label, color=SECTOR_COLORS[sec_code],
                companies_total=len(cos_in_sec), companies_active=active_count,
                avg_pct=avg_pct, companies=co_rows,
            )
        )

    # ─── 7. Bottom metrics ───
    proj_count = len(projects)
    task_count = len(tasks)
    done_proj = sum(1 for p in projects if (getattr(p, "status", "") or "").lower() == "done")
    done_tasks = sum(1 for t in tasks if (t.status or "").lower() == "done")
    deferred_proj = (sum(1 for p in projects if getattr(p, "linked_year", None) is not None)
                     if _HAS_PROJECT else 0)
    deferred_tasks = sum(1 for t in tasks if t.linked_year is not None)
    # avg_completion: status-derived (progress_percent in DB is 0 for legacy data)
    # Combines projects + tasks; excludes deferred/cancelled
    _STATUS_PCT = {"done": 100, "review": 75, "active": 50, "in_progress": 50, "init": 10, "new": 10}
    _avg_buf = []
    for _p in projects:
        _s = (getattr(_p, "status", None) or "").lower()
        if _s and _s not in ("deferred", "cancelled"):
            _avg_buf.append(_STATUS_PCT.get(_s, 0))
    for _t in tasks:
        _s = (_t.status or "").lower()
        if _s and _s not in ("deferred", "cancelled"):
            _avg_buf.append(_STATUS_PCT.get(_s, 0))
    avg_completion = round(sum(_avg_buf) / len(_avg_buf)) if _avg_buf else 0
    bottom = ExecBottomMetrics(
        proj_count=proj_count, task_count=task_count,
        done_proj=done_proj, done_tasks=done_tasks,
        deferred_proj=deferred_proj, deferred_tasks=deferred_tasks,
        avg_completion=avg_completion,
    )

    # ─── 8. Available years ───
    yrs_q = await db.execute(
        select(distinct(Task.portfolio_year)).where(Task.portfolio_year.isnot(None))
    )
    available_years = sorted(
        [int(y) for y in yrs_q.scalars().all() if y is not None], reverse=True,
    )
    if not available_years:
        from datetime import datetime
        cy = datetime.now().year
        available_years = [cy - 1, cy, cy + 1]

    # ─── 9. Available sectors ───
    available_sectors_out = [
        ExecAvailableSector(id=sec_code, label=_sector_label(sec_code), color=SECTOR_COLORS[sec_code])
        for sec_code in SECTOR_ORDER
        if any(co_sector.get(co.id) == sec_code for co in all_companies)
    ]

    # ─── 10. Title strings ───
    title_sub = f"FY {year} · REVIEW · {total_companies} КОМПАНИЙ"
    row1_subtitle = f"{task_count} задач · {done_tasks} завершено · {avg_completion}% средний прогресс"

    # ════════════════════════════════════════════════════════════
    #                    PACK 2 — RATINGS
    # ════════════════════════════════════════════════════════════
    ratings_block: Optional[ExecRatingsBlock] = None
    if _HAS_AGENCY_RATING:
        try:
            r_q = await db.execute(select(AgencyRatingModel))
            all_ratings = list(r_q.scalars().all())

            # Group by company_id → {agency_key: ExecRatingCell}
            by_co: Dict[UUID, Dict[str, ExecRatingCell]] = defaultdict(dict)
            for r in all_ratings:
                co_id = getattr(r, "company_id", None)
                if not co_id:
                    continue
                agency_raw = getattr(r, "agency", None) or getattr(r, "agency_name", None) or ""
                key = _normalize_agency(agency_raw)
                if key not in {"fitch", "sp", "moodys", "sf", "sp_esg", "cdp"}:
                    continue
                cell = ExecRatingCell(
                    rating=getattr(r, "rating", None) or None,
                    outlook=getattr(r, "outlook", None) or None,
                    score=(str(getattr(r, "score", "") or "").strip() or None),
                    rated_at=_format_date_short(
                        getattr(r, "rated_at", None) or getattr(r, "published_at", None)
                    ),
                    report_url=getattr(r, "report_url", None) or getattr(r, "url", None) or None,
                )
                # Если уже есть ячейка — берём более свежую
                existing = by_co[co_id].get(key)
                if existing:
                    new_dt = getattr(r, "rated_at", None) or getattr(r, "published_at", None)
                    old_dt = None
                    for prev_r in all_ratings:
                        if (getattr(prev_r, "company_id", None) == co_id and
                                _normalize_agency(getattr(prev_r, "agency", "") or "") == key):
                            old_dt = getattr(prev_r, "rated_at", None) or getattr(prev_r, "published_at", None)
                            break
                    if new_dt and old_dt and new_dt < old_dt:
                        continue  # старее — пропускаем
                by_co[co_id][key] = cell

            # 4 ring cards: Fitch / S&P / Moody's / ESG
            esg_keys = {"sf", "sp_esg", "cdp"}
            rated_fitch = sum(1 for cells in by_co.values() if "fitch" in cells)
            rated_sp = sum(1 for cells in by_co.values() if "sp" in cells)
            rated_moodys = sum(1 for cells in by_co.values() if "moodys" in cells)
            rated_esg = sum(1 for cells in by_co.values() if cells.keys() & esg_keys)

            # Delta vs 2024 — сколько новых в 2025/2026
            def _delta_for_agency(key: str) -> int:
                count_recent = 0
                for r in all_ratings:
                    if _normalize_agency(getattr(r, "agency", "") or "") == key:
                        rd = getattr(r, "rated_at", None) or getattr(r, "published_at", None)
                        if _is_recent_2025_or_2026(rd):
                            count_recent += 1
                return count_recent

            def _delta_for_esg() -> int:
                count_recent = 0
                cos_seen: set = set()
                for r in all_ratings:
                    if _normalize_agency(getattr(r, "agency", "") or "") in esg_keys:
                        rd = getattr(r, "rated_at", None) or getattr(r, "published_at", None)
                        co_id = getattr(r, "company_id", None)
                        if _is_recent_2025_or_2026(rd) and co_id not in cos_seen:
                            cos_seen.add(co_id)
                            count_recent += 1
                return count_recent

            ring_cards = [
                ExecRingCard(
                    label="FITCH RATINGS", rated_count=rated_fitch, total=total_companies,
                    not_covered=max(0, total_companies - rated_fitch),
                    accent="#1D9E75", score=_ring_score(rated_fitch, total_companies),
                    delta_2024=_delta_for_agency("fitch"),
                ),
                ExecRingCard(
                    label="S&P GLOBAL", rated_count=rated_sp, total=total_companies,
                    not_covered=max(0, total_companies - rated_sp),
                    accent="#EF9F27", score=_ring_score(rated_sp, total_companies),
                    delta_2024=_delta_for_agency("sp"),
                ),
                ExecRingCard(
                    label="MOODY'S", rated_count=rated_moodys, total=total_companies,
                    not_covered=max(0, total_companies - rated_moodys),
                    accent="#7F77DD", score=_ring_score(rated_moodys, total_companies),
                    delta_2024=_delta_for_agency("moodys"),
                ),
                ExecRingCard(
                    label="ESG-РЕЙТИНГИ", rated_count=rated_esg, total=total_companies,
                    not_covered=max(0, total_companies - rated_esg),
                    accent="#378ADD", score=_ring_score(rated_esg, total_companies),
                    delta_2024=_delta_for_esg(),
                ),
            ]

            # Table rows: только компании с хотя бы одним рейтингом, отсортированы по name_ru
            rated_co_ids = list(by_co.keys())
            rated_co_ids.sort(key=lambda cid: co_name.get(cid, ""))
            rows: List[ExecRatingRow] = []
            for cid in rated_co_ids:
                cells = by_co[cid]
                rows.append(ExecRatingRow(
                    company_id=cid,
                    name=co_name.get(cid, "—"),
                    fitch=cells.get("fitch"),
                    sp=cells.get("sp"),
                    moodys=cells.get("moodys"),
                    sf=cells.get("sf"),
                    sp_esg=cells.get("sp_esg"),
                    cdp=cells.get("cdp"),
                ))

            ratings_block = ExecRatingsBlock(
                ring_cards=ring_cards,
                rows=rows,
                rated_total_unique=len(rated_co_ids),
                overall_total=total_companies,
            )
        except Exception as e:  # noqa: BLE001
            # Если что-то не так со схемой — оставляем None, dashboard работает без ratings
            import logging
            logging.getLogger(__name__).warning(
                "[exec_dashboard] ratings load failed: %s", e
            )
            ratings_block = None

    # ════════════════════════════════════════════════════════════
    #                PACK 2 — EXECUTION CHART
    # ════════════════════════════════════════════════════════════
    # Flat list всех компаний (с задачами), отсортированы по pct desc
    execution_chart: List[ExecExecutionRow] = []
    for co in all_companies:
        if co_total.get(co.id, 0) == 0:
            continue  # пропускаем компании без задач
        co_sec = co_sector.get(co.id, "other")
        # Pack 7.44: применить sectors фильтр и к execution_chart
        if sectors and co_sec not in sectors:
            continue
        execution_chart.append(ExecExecutionRow(
            company_id=co.id,
            name=co_name[co.id],
            pct=co_pct.get(co.id, 0),
            sector=co_sec,
        ))
    execution_chart.sort(key=lambda r: -r.pct)

    avg_execution_pct = (
        round(sum(r.pct for r in execution_chart) / len(execution_chart))
        if execution_chart else 0
    )

    # ================================================================
    #                     PACK 4 - ROW 3
    # ================================================================
    directions_out = []
    governance_out = None
    standards_out = None
    try:
        from app.models.company import Direction
        dir_q = await db.execute(select(Direction.id, Direction.code))
        dir_to_code = {did: dcode for did, dcode in dir_q.all()}
        directions_out = build_directions_block(projects, tasks, dir_to_code)
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "[exec_dashboard] directions block failed: %s", e
        )

    try:
        governance_out = await build_governance_block(
            db=db,
            year=year,
            co_id_to_name=co_name,
            co_id_to_sector=co_sector,
            sector_filter=sectors,
        )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "[exec_dashboard] governance block failed: %s", e
        )

    try:
        standards_out = build_standards_block(
            all_tasks=tasks,
            co_id_to_name=co_name,
            co_id_to_sector=co_sector,
            co_id_to_board=co_to_board,
            sector_filter=sectors,
        )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "[exec_dashboard] standards block failed: %s", e
        )

    # ================================================================
    #                  PACK 5 - ROWS 2.55 / 2.6 / 2.7
    # ================================================================
    economic_effect_out = None
    bp_tracker_out = None
    tax_contribution_out = None

    # Block 1: Economic Effect (reads from projects.extra.economicEffect)
    try:
        economic_effect_out = build_economic_effect_block(
            projects=projects,
            year=year,
            co_id_to_name=co_name,
            co_id_to_sector=co_sector,
        )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "[exec_dashboard] economic_effect block failed: %s", e
        )

    # Block 2: BP Tracker (reads from financial_lines IFRS PL)
    try:
        bp_tracker_out = await build_bp_tracker_block(
            db=db,
            year=year,
            metric=(bp_metric or "revenue"),
            co_id_to_name=co_name,
            co_id_to_sector=co_sector,
            sector_filter=sectors,
        )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "[exec_dashboard] bp_tracker block failed: %s", e
        )

    # Block 3: Tax Contribution (reads from financial_lines tax + revenue)
    try:
        tax_contribution_out = await build_tax_contribution_block(
            db=db,
            year=year,
            co_id_to_name=co_name,
            co_id_to_sector=co_sector,
            sector_filter=sectors,
        )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "[exec_dashboard] tax_contribution block failed: %s", e
        )

    # ─── Final return ───
    return ExecutiveDashboardData(
        year=year,
        total_companies=total_companies,
        title_sub=title_sub,
        row1_subtitle=row1_subtitle,
        sectors=sectors_out,
        bottom_metrics=bottom,
        ratings=ratings_block,
        execution_chart=execution_chart,
        avg_execution_pct=avg_execution_pct,
        # Pack 4 - Row 3
        directions=directions_out,
        governance=governance_out,
        standards=standards_out,
        # Pack 5 - Rows 2.55 / 2.6 / 2.7
        economic_effect=economic_effect_out,
        bp_tracker=bp_tracker_out,
        tax_contribution=tax_contribution_out,
        available_years=available_years,
        available_sectors=available_sectors_out,
    )
