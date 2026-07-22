"""
backend/app/services/exec_dashboard/blocks_pack4.py
Pack 4 helper functions для Executive Dashboard Row 3 (service-слой):
  - build_directions_block
  - build_governance_block
  - build_standards_block

Вызываются из services/exec_dashboard/service.py (10-layer: агрегация живёт
в сервисе, не в routes). Перенесено из api/routes/_pack4_blocks.py 2026-06-01.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.executive_dashboard import (
    ExecDirectionRow,
    ExecGovernanceBlock,
    ExecGovernanceCompany,
    ExecStandardsAttention,
    ExecStandardsBlock,
    ExecStandardsRing,
)

# ═══════════════════ DIRS константы ═══════════════════

# Совпадает с legacy DIRS array. По цвету и метке.
# В UI показываем только основные 8: pr/pmo/analytics скрываются как в легасие.
_DIRS: list[dict[str, str]] = [
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
_HIDDEN_DIRS = {"pr", "pmo", "analytics"}  # фильтрация в UI как в легасие


# ═══════════════════ Block 1: Directions ═══════════════════

def build_directions_block(
    p_rows: Iterable[Any],
    t_rows: Iterable[Any],
    dir_to_code: dict[Any, str],
) -> list[ExecDirectionRow]:
    """
    Direction aggregation — group projects + tasks по direction_id.

    Args:
        p_rows: Project rows (id, status, due_date, direction_id, board_id, ...)
        t_rows: Task rows (id, status, due_date, direction_id, ...)
        dir_to_code: { direction_uuid: code_str } mapping из БД

    Returns:
        List of ExecDirectionRow, отсортированный по progress_pct desc.
        Содержит ТОЛЬКО направления у которых есть хотя бы одна задача/проект.
        Скрытые (pr/pmo/analytics) исключены.
    """
    dir_buckets: dict[str, dict[str, int]] = {}
    # 2026-05-25: fallback к extra->>'direction' для legacy rows без direction_id
    valid_codes = set(dir_to_code.values())

    def _row_code(r):
        code = dir_to_code.get(r.direction_id)
        if code:
            return code
        extra = getattr(r, "extra", None) or {}
        fb = str(extra.get("direction") or "").lower().strip()
        return fb if fb in valid_codes else None

    for r in p_rows:
        code = _row_code(r)
        if not code:
            continue
        b = dir_buckets.setdefault(code, {
            "projects_total": 0, "projects_done": 0,
            "tasks_total": 0, "tasks_done": 0, "tasks_sum": 0.0,
        })
        b["projects_total"] += 1
        if r.status == "done":
            b["projects_done"] += 1

    from app.core.progress import task_weight as _tw
    for r in t_rows:
        code = _row_code(r)
        if not code:
            continue
        b = dir_buckets.setdefault(code, {
            "projects_total": 0, "projects_done": 0,
            "tasks_total": 0, "tasks_done": 0, "tasks_sum": 0.0,
        })
        w = _tw(r.status, getattr(r, "extra", None))
        if w is None:
            continue  # monthly/ongoing исключены
        b["tasks_total"] += 1
        b["tasks_sum"] += w
        if w >= 1.0:
            b["tasks_done"] += 1

    out: list[ExecDirectionRow] = []
    for d in _DIRS:
        if d["id"] in _HIDDEN_DIRS:
            continue
        b = dir_buckets.get(d["id"])
        if not b or (b["tasks_total"] == 0 and b["projects_total"] == 0):
            continue
        tasks_total = b["tasks_total"]
        prog = round(b["tasks_sum"] / tasks_total * 100) if tasks_total else 0
        out.append(ExecDirectionRow(
            id=d["id"],
            label=d["label"],
            color=d["color"],
            projects_total=b["projects_total"],
            projects_done=b["projects_done"],
            tasks_total=tasks_total,
            tasks_done=b["tasks_done"],
            progress_pct=prog,
        ))

    out.sort(key=lambda r: -r.progress_pct)
    return out


# ═══════════════════ Block 2: Governance ═══════════════════

def _compute_governance_score(
    board_size: Optional[int],
    indep: Optional[int],
    women: Optional[int],
    audit: Optional[bool],
    remun: Optional[bool],
    nom: Optional[bool],
    strat: Optional[bool],
    meetings: Optional[int],
    payload: Optional[dict],
) -> int:
    """
    Вычисляет score 0-1200 на основе полей governance_data.

    Если score уже хранится в payload['score'] — берём оттуда.
    Иначе вычисляем по формуле:
      base    = board_size * 30                            (max ~270 при 9 чел)
      indep   = independent_directors_count * 50           (max ~250 при 5 нез.)
      women   = women_directors_count * 25                 (max ~75 при 3 жен.)
      commit  = committees_present * 50                    (max 250, набор из 5)
      meetings= min(meetings_per_year, 24) * 10            (max 240)
    Итого: max ~1085, типично 500-900.
    """
    if payload and isinstance(payload, dict) and isinstance(payload.get("score"), int | float):
        return int(payload["score"])

    bs = board_size or 0
    ind = indep or 0
    wm = women or 0
    # Канонический набор комитетов (governance/_helpers.committees_present):
    # nomination‖remuneration = ОДИН комитет + Антикор + Введение (из payload).
    # Раньше здесь был pre-fix баг — nom+remun считались как 2, anticorr/induction
    # игнорировались → exec-балл расходился с /governance для editor-компаний без
    # хранимого payload['score'].
    pl = payload if isinstance(payload, dict) else {}
    cm = (
        (1 if audit else 0)
        + (1 if strat else 0)
        + (1 if (nom or remun) else 0)
        + (1 if pl.get("anticorr") else 0)
        + (1 if pl.get("induction") else 0)
    )
    mt = min(meetings or 0, 24)

    score = bs * 30 + ind * 50 + wm * 25 + cm * 50 + mt * 10
    return min(score, 1200)


async def build_governance_block(
    db: AsyncSession,
    year: int,
    co_id_to_name: dict[Any, str],
    co_id_to_sector: dict[Any, str],
    sector_filter: Optional[list[str]] = None,
) -> Optional[ExecGovernanceBlock]:
    """
    Загружает governance_data за год + считает summary KPI + top-7 список.

    Args:
        db: AsyncSession
        year: portfolio year
        co_id_to_name: {company_id: name} mapping (только активные компании)
        co_id_to_sector: {company_id: sector_code} mapping
        sector_filter: список кодов секторов, фильтрация после загрузки

    Returns:
        ExecGovernanceBlock или None если нет данных за год.
    """
    try:
        from app.models.governance import GovernanceData
    except ImportError:
        return None

    res = await db.execute(
        select(
            GovernanceData.company_id,
            GovernanceData.board_size,
            GovernanceData.independent_directors_count,
            GovernanceData.women_directors_count,
            GovernanceData.has_audit_committee,
            GovernanceData.has_remuneration_committee,
            GovernanceData.has_nomination_committee,
            GovernanceData.has_strategy_committee,
            GovernanceData.meetings_per_year,
            GovernanceData.payload,
        ).where(GovernanceData.year == year)
    )
    rows = res.all()

    if not rows:
        return ExecGovernanceBlock(
            total_companies=0,
            avg_score=0,
            top_score=0,
            avg_indep_pct=0,
            avg_women_pct=0,
            top_companies=[],
        )

    # Build per-company data
    companies: list[ExecGovernanceCompany] = []
    sec_set = set(sector_filter) if sector_filter else None

    for r in rows:
        co_id = r.company_id
        if co_id not in co_id_to_name:
            continue  # company не активна
        sector = co_id_to_sector.get(co_id, "other")
        if sec_set and sector not in sec_set:
            continue

        bs = r.board_size or 0
        ind = r.independent_directors_count or 0
        wm = r.women_directors_count or 0

        score = _compute_governance_score(
            r.board_size,
            r.independent_directors_count,
            r.women_directors_count,
            r.has_audit_committee,
            r.has_remuneration_committee,
            r.has_nomination_committee,
            r.has_strategy_committee,
            r.meetings_per_year,
            r.payload,
        )
        score_pct = min(100, round(score / 1200 * 100))
        indep_pct = round(ind / bs * 100) if bs > 0 else 0
        women_pct = round(wm / bs * 100) if bs > 0 else 0

        companies.append(ExecGovernanceCompany(
            company_id=co_id,
            name=co_id_to_name[co_id],
            sector=sector,
            score=score,
            score_pct=score_pct,
            board_size=bs,
            independent_count=ind,
            women_count=wm,
            indep_pct=indep_pct,
            women_pct=women_pct,
        ))

    if not companies:
        return ExecGovernanceBlock(
            total_companies=0,
            avg_score=0,
            top_score=0,
            avg_indep_pct=0,
            avg_women_pct=0,
            top_companies=[],
        )

    # Summary KPIs
    total = len(companies)
    avg_score = round(sum(c.score for c in companies) / total)
    top_score = max(c.score for c in companies)
    # «Независ.%»/«Женщин%» — среднее ПО-КОМПАНИЙНЫХ долей (как /governance
    # get_overview: mean-of-ratios по компаниям с советом), а не пул Σ/Σ — иначе
    # одинаково подписанные плитки exec и модуля расходились при разных размерах советов.
    _indep_pcts = [c.indep_pct for c in companies if c.board_size > 0]
    _women_pcts = [c.women_pct for c in companies if c.board_size > 0]
    avg_indep_pct = round(sum(_indep_pcts) / len(_indep_pcts)) if _indep_pcts else 0
    avg_women_pct = round(sum(_women_pcts) / len(_women_pcts)) if _women_pcts else 0

    # Top-7
    companies.sort(key=lambda c: -c.score)
    top_7 = companies[:7]

    return ExecGovernanceBlock(
        total_companies=total,
        avg_score=avg_score,
        top_score=top_score,
        avg_indep_pct=avg_indep_pct,
        avg_women_pct=avg_women_pct,
        top_companies=top_7,
    )


# ═══════════════════ Block 3: Standards (МСФО + Forensic) ═══════════════════

# Ключевые слова для детекции (как в легасие _buildStandardsWidget)
_IFRS_KEYWORDS = ["мсфо", "ifrs", "переход на мсфо"]
_FORENSIC_KEYWORDS = ["форензик", "forensic"]


def _matches_any(text: str, keywords: Iterable[str]) -> bool:
    """Case-insensitive поиск любого ключевого слова в тексте."""
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in keywords)


def _gap_label(status: str, kind: str) -> Optional[str]:
    """Возвращает human-readable gap label или None если статус OK."""
    if status == "done":
        return None
    if status in ("active", "review"):
        return f"{kind} в процессе"
    if status == "init" and kind == "Forensic":
        return "Forensic тендер"
    return f"{kind} не начат"


def build_standards_block(
    all_tasks: Iterable[Any],
    co_id_to_name: dict[Any, str],
    co_id_to_sector: dict[Any, str],
    co_id_to_board: dict[Any, Any],
    sector_filter: Optional[list[str]] = None,
) -> ExecStandardsBlock:
    """
    Построить standards block (МСФО + Forensic).

    Логика из легасиа _buildStandardsWidget:
      - Берём все задачи за год
      - IFRS: если task.title содержит 'мсфо'/'ifrs' AND это project — статус компании = task.status
      - Forensic: если task.title содержит 'форензик'/'forensic' — статус компании = task.status
      - Если несколько задач → приоритет project'у
      - Total = все активные компании (после фильтра)

    Args:
        all_tasks: итератор Task объектов с полями: title, status, board_id, company_id, project_id
                   ВАЖНО: tasks с project_id is None считаются projects (top-level).
        co_id_to_name: { company_id: name }
        co_id_to_sector: { company_id: sector_code }
        co_id_to_board: { company_id: board_id } — для legacy сопоставления
        sector_filter: фильтр по секторам

    Returns:
        ExecStandardsBlock с двумя ring и attention list.
    """
    # Filter companies по sector
    sec_set = set(sector_filter) if sector_filter else None
    target_co_ids = {
        cid for cid in co_id_to_name
        if not sec_set or co_id_to_sector.get(cid, "other") in sec_set
    }

    # Per-company status: { co_id: ('done'|'active'|'review'|'init'|'new'|'none', is_project_bool) }
    ifrs_by_co: dict[Any, Any] = {}  # co_id -> (status, is_project)
    forensic_by_co: dict[Any, Any] = {}

    for t in all_tasks:
        title = getattr(t, "title", None) or ""
        status = getattr(t, "status", None) or "none"
        co_id = getattr(t, "company_id", None)
        if not co_id or co_id not in target_co_ids:
            continue
        # is_project: True if task has no parent project (т.е. сам является top-level)
        is_project = getattr(t, "project_id", None) is None

        if _matches_any(title, _IFRS_KEYWORDS):
            existing = ifrs_by_co.get(co_id)
            # Prefer project, otherwise keep first found
            if existing is None or (is_project and not existing[1]):
                ifrs_by_co[co_id] = (status, is_project)

        if _matches_any(title, _FORENSIC_KEYWORDS):
            existing = forensic_by_co.get(co_id)
            if existing is None or (is_project and not existing[1]):
                forensic_by_co[co_id] = (status, is_project)

    total_companies = len(target_co_ids)

    # Aggregate status counts
    def _aggregate(by_co: dict[Any, Any]) -> ExecStandardsRing:
        done = active = review = init = 0
        for co_id in target_co_ids:
            entry = by_co.get(co_id)
            if not entry:
                continue
            st = entry[0]
            if st == "done":
                done += 1
            elif st == "active":
                active += 1
            elif st == "review":
                review += 1
            elif st == "init":
                init += 1
        not_started = total_companies - done - active - review - init
        pct = round(done / total_companies * 100) if total_companies > 0 else 0
        return ExecStandardsRing(
            done=done,
            active=active + review,  # объединяем в легасие тоже
            init=init,
            not_started=max(0, not_started),
            pct=pct,
        )

    ifrs_ring = _aggregate(ifrs_by_co)
    forensic_ring = _aggregate(forensic_by_co)

    # Attention list: компании где есть gap (не done и не review для IFRS; не done/active/review для forensic)
    attention: list[ExecStandardsAttention] = []
    for co_id in target_co_ids:
        ifrs_entry = ifrs_by_co.get(co_id)
        forensic_entry = forensic_by_co.get(co_id)
        ifrs_st = ifrs_entry[0] if ifrs_entry else "none"
        forensic_st = forensic_entry[0] if forensic_entry else "none"

        gaps: list[str] = []
        ifrs_gap = _gap_label(ifrs_st, "МСФО")
        if ifrs_gap and ifrs_st not in ("review",):  # review = почти готово, не attention
            gaps.append(ifrs_gap)
        forensic_gap = _gap_label(forensic_st, "Forensic")
        if forensic_gap and forensic_st not in ("review",):
            gaps.append(forensic_gap)

        if not gaps:
            continue

        # priority for sorting
        prio = 0
        if ifrs_st not in ("done", "active", "review"):
            prio += 3
        elif ifrs_st in ("active", "review"):
            prio += 2
        if forensic_st not in ("done", "active", "review", "init"):
            prio += 3
        elif forensic_st in ("active", "review"):
            prio += 2
        elif forensic_st == "init":
            prio += 1

        attention.append((prio, ExecStandardsAttention(
            company_id=co_id,
            name=co_id_to_name.get(co_id, "—"),
            sector=co_id_to_sector.get(co_id, "other"),
            ifrs_status=ifrs_st,
            forensic_status=forensic_st,
            gaps=gaps,
        )))

    attention.sort(key=lambda x: (-x[0], x[1].name))

    return ExecStandardsBlock(
        total_companies=total_companies,
        ifrs=ifrs_ring,
        forensic=forensic_ring,
        attention_list=[a[1] for a in attention[:10]],  # top-10
    )
