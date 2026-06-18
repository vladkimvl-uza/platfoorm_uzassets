"""Executive Dashboard composer (refactored from 480-LOC legacy).

The original `executive_dashboard` route function inlined 12+ stages.
Here each stage is its own named method <80 LOC, called from the
top-level `build_dashboard` in linear order so the data flow stays
readable.

Sub-block builders (Pack 4: directions/governance/standards, Pack 5:
economic_effect/bp_tracker/tax_contribution) live in
`app/services/exec_dashboard/blocks_pack4.py`, `blocks_pack5.py` и
`drill_pack4.py` (перенесены из api/routes 2026-06-01 — агрегация в сервисе).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.company import Company
from app.models.task import Task
from app.schemas.executive_dashboard import (
    ExecAvailableSector,
    ExecBottomMetrics,
    ExecCompanyInSector,
    ExecDirectionDrillResponse,
    ExecExecutionRow,
    ExecRatingCell,
    ExecRatingRow,
    ExecRatingsBlock,
    ExecRingCard,
    ExecSectorRow,
    ExecutiveDashboardData,
)
from app.services.exec_dashboard._helpers import (
    SECTOR_COLORS,
    SECTOR_ORDER,
    format_date_short,
    is_recent_2025_or_2026,
    normalize_agency,
    normalize_sector_code,
    ring_score,
)
from app.services.exec_dashboard._helpers import (
    sector_code as _sector_code,
)
from app.services.exec_dashboard._helpers import (
    sector_label as _sector_label,
)
from app.uow.ports import UnitOfWorkABC

log = logging.getLogger(__name__)


class ExecDashboardService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── top-level orchestration ──────────────────────────────────

    async def build_dashboard(
        self,
        year: int,
        *,
        sectors: Optional[list[str]],
        bp_metric: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ExecutiveDashboardData:
        # Normalize incoming sector filter
        if sectors:
            sectors = [normalize_sector_code(s) for s in sectors]

        async with self.uow:
            all_companies = await self.uow.exec_dashboard.list_companies(
                scope_company_ids=scope_company_ids,
                hidden_for_year=year,
            )
            co_to_board = await self.uow.exec_dashboard.boards_by_company()
            tasks = await self.uow.exec_dashboard.list_tasks_for_year(year)
            projects = await self.uow.exec_dashboard.list_projects_for_year(year)
            # RBAC scope: list_tasks/projects_for_year НЕ скоупятся в репозитории —
            # фильтруем по разрешённым компаниям, иначе счётчики (len) показывают
            # ВЕСЬ портфель скоупленному пользователю (баг: общее число задач/проектов).
            if scope_company_ids is not None:
                _allowed = set(scope_company_ids)
                tasks = [t for t in tasks if t.company_id in _allowed]
                projects = [p for p in projects if getattr(p, "company_id", None) in _allowed]
            agency_ratings = await self.uow.exec_dashboard.list_agency_ratings()
            # RBAC scope: список агентских рейтингов НЕ скоупится в репозитории —
            # без фильтра скоупленный пользователь видит рейтинги ЧУЖИХ компаний
            # (строки «—» в блоке «Рейтинги компаний»). Оставляем только свои.
            if scope_company_ids is not None:
                _allowed_co = set(scope_company_ids)
                agency_ratings = [
                    ar for ar in agency_ratings
                    if getattr(ar, "company_id", None) in _allowed_co
                ]
            dir_to_code = await self.uow.exec_dashboard.direction_id_to_code()
            available_years = await self.uow.exec_dashboard.available_task_years()

            # Need the raw session for the pack4/pack5 helpers
            session = self.uow._session  # type: ignore[attr-defined]

            total_companies = len(all_companies)
            co_sector: dict[UUID, str] = {co.id: _sector_code(co) for co in all_companies}
            co_name: dict[UUID, str] = {
                co.id: (co.name_ru or co.code or "—") for co in all_companies
            }

            co_pct, co_total, co_done, co_plan = self._compute_task_aggregates(tasks)

            sectors_out, all_active_co_pcts = self._build_sectors(
                all_companies=all_companies,
                sectors_filter=sectors,
                co_sector=co_sector, co_name=co_name,
                co_pct=co_pct, co_total=co_total, co_done=co_done,
                co_to_board=co_to_board,
            )

            bottom = self._build_bottom_metrics(
                projects=projects, tasks=tasks,
                all_active_co_pcts=all_active_co_pcts,
            )

            available_sectors_out = self._build_available_sectors(
                all_companies=all_companies, co_sector=co_sector,
            )

            if not available_years:
                cy = datetime.now().year
                available_years = [cy - 1, cy, cy + 1]

            ratings_block = self._build_ratings_block(
                agency_ratings=agency_ratings,
                total_companies=total_companies, co_name=co_name,
            )

            execution_chart = self._build_execution_chart(
                all_companies=all_companies,
                co_total=co_total, co_pct=co_pct, co_plan=co_plan,
                co_name=co_name, co_sector=co_sector,
                sectors_filter=sectors,
            )
            avg_execution_pct = (
                round(sum(r.pct for r in execution_chart) / len(execution_chart))
                if execution_chart else 0
            )

            # + sub-blocks
            directions_out, governance_out, standards_out = await self._build_pack4_blocks(
                session=session, year=year,
                projects=projects, tasks=tasks,
                dir_to_code=dir_to_code,
                co_name=co_name, co_sector=co_sector,
                co_to_board=co_to_board, sectors_filter=sectors,
            )
            # Year-fallback для направлений: если за запрошенный год нет задач/
            # проектов с direction_id — показываем самый свежий ДОСТУПНЫЙ год с
            # данными (сначала ближайший прошлый, затем будущий), чтобы вместо
            # пустой карточки «Нет данных о направлениях за FY {year}» был
            # релевантный срез. directions_year несёт фактический год для бейджа.
            directions_year = year if directions_out else None
            if not directions_out:
                from app.services.exec_dashboard.blocks_pack4 import (
                    build_directions_block as _bd,
                )
                _scope = set(scope_company_ids) if scope_company_ids is not None else None
                _past = [y for y in available_years if y < year]          # уже desc
                _future = sorted(y for y in available_years if y > year)  # asc
                for cand in _past + _future:
                    c_tasks = await self.uow.exec_dashboard.list_tasks_for_year(cand)
                    c_projs = await self.uow.exec_dashboard.list_projects_for_year(cand)
                    if _scope is not None:
                        c_tasks = [t for t in c_tasks if t.company_id in _scope]
                        c_projs = [
                            p for p in c_projs
                            if getattr(p, "company_id", None) in _scope
                        ]
                    try:
                        cand_dirs = _bd(c_projs, c_tasks, dir_to_code)
                    except Exception:
                        cand_dirs = []
                    if cand_dirs:
                        directions_out = cand_dirs
                        directions_year = cand
                        break

            economic_effect_out, bp_tracker_out, tax_contribution_out = \
                await self._build_pack5_blocks(
                    session=session, year=year, bp_metric=bp_metric,
                    projects=projects, co_name=co_name,
                    co_sector=co_sector, sectors_filter=sectors,
                )

        title_sub = f"FY {year} · REVIEW · {total_companies} КОМПАНИЙ"
        row1_subtitle = (
            f"{len(tasks)} задач · "
            f"{sum(1 for t in tasks if (t.status or '').lower() == 'done')} завершено · "
            f"{bottom.avg_completion}% средний прогресс"
        )

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
            directions=directions_out,
            directions_year=directions_year,
            governance=governance_out,
            standards=standards_out,
            economic_effect=economic_effect_out,
            bp_tracker=bp_tracker_out,
            tax_contribution=tax_contribution_out,
            available_years=available_years,
            available_sectors=available_sectors_out,
        )

    async def direction_drill(
        self,
        direction_code: str,
        *,
        year: Optional[int],
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ExecDirectionDrillResponse:
        from app.services.exec_dashboard.drill_pack4 import build_direction_drill
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            try:
                return await build_direction_drill(
                    session, direction_code, year=year,
                    scope_company_ids=(set(scope_company_ids) if scope_company_ids is not None else None),
                )
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))

    # ─── stage methods (each <80 LOC) ─────────────────────────────

    @staticmethod
    def _compute_task_aggregates(tasks: list[Task]):
        """Факт + план по компаниям.

        Факт (co_pct) = среднее по задачам по единому правилу (app.core.progress):
        done → 1, остальные → 0, monthly/ongoing исключены, quarterly = done если
        все 4 квартала закрыты.

        План (co_plan) = доля задач, чей дедлайн уже наступил (due_date ≤ сегодня)
        от того же знаменателя. Показывает, сколько задач ДОЛЖНО быть завершено к
        текущей дате исходя из дедлайнов.
        """
        from app.core.progress import task_weight
        today = datetime.now().date()
        task_by_co: dict[UUID, list[Task]] = defaultdict(list)
        for t in tasks:
            if t.company_id:
                task_by_co[t.company_id].append(t)
        co_pct: dict[UUID, int] = {}
        co_total: dict[UUID, int] = {}
        co_done: dict[UUID, int] = {}
        co_plan: dict[UUID, int] = {}
        for co_id, ts in task_by_co.items():
            total = 0
            done = 0
            plan = 0
            for t in ts:
                w = task_weight(t.status, getattr(t, "extra", None))
                if w is None:
                    continue  # monthly/ongoing — в счёт не идут
                total += 1
                if w == 1:
                    done += 1
                due = getattr(t, "due_date", None)
                if due is not None and due <= today:
                    plan += 1
            co_pct[co_id] = round(done / total * 100) if total > 0 else 0
            co_plan[co_id] = round(plan / total * 100) if total > 0 else 0
            co_total[co_id] = total
            co_done[co_id] = done
        return co_pct, co_total, co_done, co_plan

    @staticmethod
    def _build_sectors(
        *,
        all_companies: list[Company],
        sectors_filter: Optional[list[str]],
        co_sector: dict[UUID, str],
        co_name: dict[UUID, str],
        co_pct: dict[UUID, int], co_total: dict[UUID, int], co_done: dict[UUID, int],
        co_to_board: dict[UUID, UUID],
    ):
        sectors_out: list[ExecSectorRow] = []
        all_active_co_pcts: list[float] = []
        for sec_code in SECTOR_ORDER:
            if sectors_filter and sec_code not in sectors_filter:
                continue
            cos_in_sec = [co for co in all_companies if co_sector.get(co.id) == sec_code]
            if not cos_in_sec:
                continue
            co_rows = sorted(
                [
                    ExecCompanyInSector(
                        company_id=co.id, name=co_name[co.id],
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
            avg_pct_raw = (sum(active_pcts) / len(active_pcts)) if active_pcts else 0.0
            label_real = ""
            for co in cos_in_sec:
                if co.sector and getattr(co.sector, "name_ru", None):
                    label_real = co.sector.name_ru
                    break
            sectors_out.append(ExecSectorRow(
                id=sec_code, label=_sector_label(sec_code, label_real),
                color=SECTOR_COLORS[sec_code],
                companies_total=len(cos_in_sec),
                companies_active=active_count,
                avg_pct=round(avg_pct_raw),
                companies=co_rows,
            ))
            if active_count > 0:
                all_active_co_pcts.extend(active_pcts)
        return sectors_out, all_active_co_pcts

    @staticmethod
    def _build_bottom_metrics(
        *, projects, tasks, all_active_co_pcts,
    ) -> ExecBottomMetrics:
        proj_count = len(projects)
        task_count = len(tasks)
        done_proj = sum(1 for p in projects if (getattr(p, "status", "") or "").lower() == "done")
        done_tasks = sum(1 for t in tasks if (t.status or "").lower() == "done")
        try:
            deferred_proj = sum(1 for p in projects if getattr(p, "linked_year", None) is not None)
        except Exception:
            deferred_proj = 0
        deferred_tasks = sum(1 for t in tasks if t.linked_year is not None)
        # Средний прогресс = ПРОСТОЕ среднее процентов прогресса по компаниям
        # (с задачами), по запросу — каждая компания весит одинаково, независимо
        # от числа задач (а не взвешенное done/total по всему портфелю).
        avg_completion = (
            round(sum(all_active_co_pcts) / len(all_active_co_pcts))
            if all_active_co_pcts else 0
        )
        return ExecBottomMetrics(
            proj_count=proj_count, task_count=task_count,
            done_proj=done_proj, done_tasks=done_tasks,
            deferred_proj=deferred_proj, deferred_tasks=deferred_tasks,
            avg_completion=avg_completion,
        )

    @staticmethod
    def _build_available_sectors(
        *, all_companies, co_sector,
    ) -> list[ExecAvailableSector]:
        return [
            ExecAvailableSector(id=sec_code, label=_sector_label(sec_code), color=SECTOR_COLORS[sec_code])
            for sec_code in SECTOR_ORDER
            if any(co_sector.get(co.id) == sec_code for co in all_companies)
        ]

    @staticmethod
    def _build_ratings_block(
        *, agency_ratings, total_companies: int, co_name: dict[UUID, str],
    ) -> Optional[ExecRatingsBlock]:
        if not agency_ratings:
            return None
        try:
            by_co: dict[UUID, dict[str, ExecRatingCell]] = defaultdict(dict)
            for r in agency_ratings:
                co_id = getattr(r, "company_id", None)
                if not co_id:
                    continue
                agency_raw = getattr(r, "agency", None) or getattr(r, "agency_name", None) or ""
                key = normalize_agency(agency_raw)
                if key not in {"fitch", "sp", "moodys", "sf", "sp_esg", "cdp"}:
                    continue
                cell = ExecRatingCell(
                    rating=getattr(r, "rating", None) or None,
                    outlook=getattr(r, "outlook", None) or None,
                    score=(str(getattr(r, "score", "") or "").strip() or None),
                    rated_at=format_date_short(
                        getattr(r, "rated_at", None) or getattr(r, "published_at", None)
                    ),
                    report_url=getattr(r, "report_url", None) or getattr(r, "url", None) or None,
                )
                if by_co[co_id].get(key):
                    new_dt = getattr(r, "rated_at", None) or getattr(r, "published_at", None)
                    old_dt = None
                    for prev_r in agency_ratings:
                        if (getattr(prev_r, "company_id", None) == co_id and
                                normalize_agency(getattr(prev_r, "agency", "") or "") == key):
                            old_dt = getattr(prev_r, "rated_at", None) or getattr(prev_r, "published_at", None)
                            break
                    if new_dt and old_dt and new_dt < old_dt:
                        continue
                by_co[co_id][key] = cell

            esg_keys = {"sf", "sp_esg", "cdp"}
            rated_fitch  = sum(1 for cells in by_co.values() if "fitch" in cells)
            rated_sp     = sum(1 for cells in by_co.values() if "sp" in cells)
            rated_moodys = sum(1 for cells in by_co.values() if "moodys" in cells)
            rated_esg    = sum(1 for cells in by_co.values() if cells.keys() & esg_keys)

            def _delta_for_agency(key: str) -> int:
                return sum(
                    1 for r in agency_ratings
                    if normalize_agency(getattr(r, "agency", "") or "") == key
                    and is_recent_2025_or_2026(
                        getattr(r, "rated_at", None) or getattr(r, "published_at", None)
                    )
                )

            def _delta_for_esg() -> int:
                count_recent = 0
                cos_seen: set = set()
                for r in agency_ratings:
                    if normalize_agency(getattr(r, "agency", "") or "") in esg_keys:
                        rd = getattr(r, "rated_at", None) or getattr(r, "published_at", None)
                        co_id = getattr(r, "company_id", None)
                        if is_recent_2025_or_2026(rd) and co_id not in cos_seen:
                            cos_seen.add(co_id)
                            count_recent += 1
                return count_recent

            ring_cards = [
                ExecRingCard(
                    label="FITCH RATINGS", rated_count=rated_fitch, total=total_companies,
                    not_covered=max(0, total_companies - rated_fitch),
                    accent="#1D9E75", score=ring_score(rated_fitch, total_companies),
                    delta_2024=_delta_for_agency("fitch"),
                ),
                ExecRingCard(
                    label="S&P GLOBAL", rated_count=rated_sp, total=total_companies,
                    not_covered=max(0, total_companies - rated_sp),
                    accent="#EF9F27", score=ring_score(rated_sp, total_companies),
                    delta_2024=_delta_for_agency("sp"),
                ),
                ExecRingCard(
                    label="MOODY'S", rated_count=rated_moodys, total=total_companies,
                    not_covered=max(0, total_companies - rated_moodys),
                    accent="#7F77DD", score=ring_score(rated_moodys, total_companies),
                    delta_2024=_delta_for_agency("moodys"),
                ),
                ExecRingCard(
                    label="ESG-РЕЙТИНГИ", rated_count=rated_esg, total=total_companies,
                    not_covered=max(0, total_companies - rated_esg),
                    accent="#378ADD", score=ring_score(rated_esg, total_companies),
                    delta_2024=_delta_for_esg(),
                ),
            ]

            rated_co_ids = list(by_co.keys())
            rated_co_ids.sort(key=lambda cid: co_name.get(cid, ""))
            rows = [
                ExecRatingRow(
                    company_id=cid, name=co_name.get(cid, "—"),
                    fitch=by_co[cid].get("fitch"), sp=by_co[cid].get("sp"),
                    moodys=by_co[cid].get("moodys"), sf=by_co[cid].get("sf"),
                    sp_esg=by_co[cid].get("sp_esg"), cdp=by_co[cid].get("cdp"),
                )
                for cid in rated_co_ids
            ]
            return ExecRatingsBlock(
                ring_cards=ring_cards, rows=rows,
                rated_total_unique=len(rated_co_ids),
                overall_total=total_companies,
            )
        except Exception as e:
            log.warning("[exec_dashboard] ratings load failed: %s", e)
            return None

    @staticmethod
    def _build_execution_chart(
        *,
        all_companies, co_total, co_pct, co_plan, co_name, co_sector,
        sectors_filter,
    ) -> list[ExecExecutionRow]:
        out: list[ExecExecutionRow] = []
        for co in all_companies:
            if co_total.get(co.id, 0) == 0:
                continue
            co_sec = co_sector.get(co.id, "other")
            if sectors_filter and co_sec not in sectors_filter:
                continue
            out.append(ExecExecutionRow(
                company_id=co.id, name=co_name[co.id],
                pct=co_pct.get(co.id, 0),
                plan_pct=co_plan.get(co.id, 0),
                sector=co_sec,
            ))
        out.sort(key=lambda r: -r.pct)
        return out

    @staticmethod
    async def _build_pack4_blocks(
        *,
        session, year, projects, tasks, dir_to_code,
        co_name, co_sector, co_to_board, sectors_filter,
    ):
        from app.services.exec_dashboard.blocks_pack4 import (
            build_directions_block,
            build_governance_block,
            build_standards_block,
        )
        directions_out = []
        governance_out = None
        standards_out = None
        try:
            directions_out = build_directions_block(projects, tasks, dir_to_code)
        except Exception as e:
            log.warning("[exec_dashboard] directions block failed: %s", e)
        try:
            governance_out = await build_governance_block(
                db=session, year=year,
                co_id_to_name=co_name, co_id_to_sector=co_sector,
                sector_filter=sectors_filter,
            )
        except Exception as e:
            log.warning("[exec_dashboard] governance block failed: %s", e)
        try:
            standards_out = build_standards_block(
                all_tasks=tasks,
                co_id_to_name=co_name, co_id_to_sector=co_sector,
                co_id_to_board=co_to_board,
                sector_filter=sectors_filter,
            )
        except Exception as e:
            log.warning("[exec_dashboard] standards block failed: %s", e)
        return directions_out, governance_out, standards_out

    @staticmethod
    async def _build_pack5_blocks(
        *,
        session, year, bp_metric, projects, co_name, co_sector, sectors_filter,
    ):
        from app.services.exec_dashboard.blocks_pack5 import (
            build_bp_tracker_block,
            build_economic_effect_block,
            build_tax_contribution_block,
        )
        economic_effect_out = None
        bp_tracker_out = None
        tax_contribution_out = None
        try:
            economic_effect_out = build_economic_effect_block(
                projects=projects, year=year,
                co_id_to_name=co_name, co_id_to_sector=co_sector,
            )
        except Exception as e:
            log.warning("[exec_dashboard] economic_effect block failed: %s", e)
        # Year-fallback: если за выбранный год данных нет — берём последний
        # год с данными (до 4 лет назад) и помечаем requested_year.
        async def _bp_for(y):
            return await build_bp_tracker_block(
                db=session, year=y, metric=(bp_metric or "revenue"),
                co_id_to_name=co_name, co_id_to_sector=co_sector,
                sector_filter=sectors_filter,
            )

        async def _tax_for(y):
            return await build_tax_contribution_block(
                db=session, year=y,
                co_id_to_name=co_name, co_id_to_sector=co_sector,
                sector_filter=sectors_filter,
            )

        async def _with_fallback(builder, has_data_fn, max_back=4):
            out = await builder(year)
            if out is not None and has_data_fn(out):
                return out
            for back in range(1, max_back + 1):
                cand = await builder(year - back)
                if cand is not None and has_data_fn(cand):
                    try:
                        cand.requested_year = year
                    except Exception:
                        pass
                    return cand
            return out  # ничего не нашли — отдаём пустой за исходный год

        def _bp_has_data(o) -> bool:
            # mode='plan-fact' ещё не значит «есть данные»: блок может вернуться
            # с нулевыми план/факт и 0 сравнимых компаний. Считаем данными только
            # если есть ненулевые суммы ИЛИ реальные строки performance-шкалы.
            if getattr(o, "mode", "empty") == "empty":
                return False
            return bool(
                getattr(o, "plan_total", 0) or getattr(o, "fact_total", 0)
                or getattr(o, "sum_fact_ll", 0) or getattr(o, "sum_plan_ll", 0)
                or len(getattr(o, "rows", []) or [])
            )

        try:
            bp_tracker_out = await _with_fallback(_bp_for, _bp_has_data)
        except Exception as e:
            log.warning("[exec_dashboard] bp_tracker block failed: %s", e)
        try:
            tax_contribution_out = await _with_fallback(
                _tax_for, lambda o: bool(getattr(o, "has_data", False)),
            )
        except Exception as e:
            log.warning("[exec_dashboard] tax_contribution block failed: %s", e)
        return economic_effect_out, bp_tracker_out, tax_contribution_out
