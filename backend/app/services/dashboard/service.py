"""Shareholder Dashboard composer + drill endpoints."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import HTTPException
from fastapi import status as http_status

from app.services.dashboard._helpers import (
    AGENCIES_CREDIT,
    AGENCIES_ESG,
    AGENCY_COLORS,
    AGENCY_ESG,
    AGENCY_LABELS,
    BUCKET_ACCENT,
    BUCKET_LABEL,
    BUCKET_TITLE,
    DDM_SECTOR_COLOR,
    DIRS,
    RECURRING_STATUSES,
    SECTOR_COLORS,
    SECTOR_LABELS,
    SECTOR_ORDER,
    STATUS_DEFS,
    best_credit_label,
    best_credit_rank,
    best_esg_score,
    is_overdue,
    item_dict_drill,
    item_sort_key,
    matches_bucket,
)
from app.uow.ports import UnitOfWorkABC


class DashboardService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── /dashboard/shareholder ───────────────────────────────────

    async def shareholder_dashboard(
        self,
        *,
        year: Optional[int],
        sector_code: Optional[str],
        direction_code: Optional[str],
        company_code: Optional[str],
        scope_company_ids: Optional[list] = None,
    ) -> dict:
        async with self.uow:
            r = self.uow.dashboard
            available_years = await r.available_task_years()

            allowed_board_ids = None
            if sector_code or company_code:
                co_ids = await r.resolve_company_ids(
                    sector_code=sector_code, company_code=company_code,
                )
                allowed_board_ids = await r.resolve_board_ids_for_companies(co_ids)

            # RBAC scope: пересекаем фильтр досок с досками разрешённых компаний.
            # Иначе счётчики (len p_rows/t_rows) считают весь портфель — баг.
            if scope_company_ids is not None:
                scope_boards = set(await r.resolve_board_ids_for_companies(list(scope_company_ids)))
                allowed_board_ids = (
                    scope_boards if allowed_board_ids is None
                    else {b for b in allowed_board_ids if b in scope_boards}
                )

            allowed_dir_ids = None
            if direction_code:
                allowed_dir_ids = await r.resolve_direction_ids(direction_code)

            p_rows = await r.filtered_projects_shareholder(
                year=year, allowed_board_ids=allowed_board_ids,
                allowed_dir_ids=allowed_dir_ids,
            )
            t_rows = await r.filtered_tasks_shareholder(
                year=year, allowed_board_ids=allowed_board_ids,
                allowed_dir_ids=allowed_dir_ids,
            )
            board_to_company = await r.board_to_company_map()
            co_meta = await r.companies_meta()
            dir_to_code = await r.direction_id_to_code()
            rating_rows = await r.list_agency_ratings_for_dashboard()

        kpis = self._build_kpis(p_rows, t_rows)
        statuses = self._build_statuses(p_rows, t_rows, kpis)
        co_buckets = self._bucket_by_company(p_rows, t_rows, board_to_company)
        companies_by_sector = self._companies_by_sector(co_buckets, co_meta)
        directions = self._directions(p_rows, t_rows, dir_to_code)
        ratings = self._build_ratings(rating_rows, co_meta)
        completion = self._build_completion(co_buckets, co_meta)

        return {
            "kpis":                kpis,
            "statuses":            statuses,
            "companies_by_sector": companies_by_sector,
            "directions":          directions,
            "ratings":             ratings,
            "completion":          completion,
            "available_years":     available_years,
            "selected_year":       year,
        }

    # ─── stage methods (shareholder) ──────────────────────────────

    @staticmethod
    def _build_kpis(p_rows, t_rows) -> dict:
        done_proj = sum(1 for r in p_rows if r.status == "done")
        active_proj = sum(1 for r in p_rows if r.status == "active")
        overdue_proj = sum(1 for r in p_rows if is_overdue(r.due_date, r.status))
        # 2026-05-26: после миграции linked_year=source. Считаем оба направления:
        # incoming (linked_year set) + outgoing (linked_*_id set без linked_year).
        # Иначе на FY-source год показывал 0, что вводит в заблуждение.
        deferred_proj = sum(
            1 for r in p_rows
            if r.linked_year is not None or getattr(r, "linked_project_id", None) is not None
        )
        done_tasks = sum(1 for r in t_rows if r.status == "done")
        active_tasks = sum(1 for r in t_rows if r.status == "active")
        overdue_tasks = sum(1 for r in t_rows if is_overdue(r.due_date, r.status))
        deferred_tasks = sum(
            1 for r in t_rows
            if r.linked_year is not None or getattr(r, "linked_task_id", None) is not None
        )
        return {
            "projects": len(p_rows), "tasks": len(t_rows),
            "done_proj": done_proj, "done_tasks": done_tasks,
            "active_proj": active_proj, "active_tasks": active_tasks,
            "overdue_proj": overdue_proj, "overdue_tasks": overdue_tasks,
            "deferred_proj": deferred_proj, "deferred_tasks": deferred_tasks,
        }

    @staticmethod
    def _build_statuses(p_rows, t_rows, kpis) -> list:
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
            "projects_count": kpis["overdue_proj"],
            "tasks_count": kpis["overdue_tasks"],
        })
        return statuses

    @staticmethod
    def _bucket_by_company(p_rows, t_rows, board_to_company) -> dict:
        co_buckets: dict[Any, dict] = {}
        for r in p_rows:
            if r.board_id is None:
                continue
            cid = board_to_company.get(r.board_id)
            if cid is None:
                continue
            b = co_buckets.setdefault(cid, {
                "projects_total": 0, "projects_done": 0,
                "tasks_total": 0, "tasks_done": 0, "tasks_sum": 0.0,
            })
            b["projects_total"] += 1
            if r.status == "done":
                b["projects_done"] += 1
        from app.core.progress import task_weight
        for r in t_rows:
            if r.board_id is None:
                continue
            cid = board_to_company.get(r.board_id)
            if cid is None:
                continue
            b = co_buckets.setdefault(cid, {
                "projects_total": 0, "projects_done": 0,
                "tasks_total": 0, "tasks_done": 0, "tasks_sum": 0.0,
            })
            # Прогресс компании = среднее по задачам по тому же правилу, что и
            # прогресс проекта: done → 1, остальные → 0, monthly/ongoing исключены,
            # quarterly = done если все 4 квартала закрыты (app.core.progress).
            w = task_weight(r.status, getattr(r, "extra", None))
            if w is None:
                continue
            b["tasks_total"] += 1
            b["tasks_sum"] += w                 # дробный вес статуса
            if w >= 1.0:
                b["tasks_done"] += 1            # полностью завершённые
        return co_buckets

    @staticmethod
    def _companies_by_sector(co_buckets, co_meta) -> list:
        sector_groups: dict[str, list] = {s: [] for s in SECTOR_ORDER}
        for cid, meta in co_meta.items():
            bucket = co_buckets.get(cid)
            if not bucket:
                continue
            sector = meta["sector"] if meta["sector"] in sector_groups else "other"
            total = bucket["tasks_total"]
            prog = round(bucket["tasks_sum"] / total * 100) if total else 0
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
        # Только секторы, в которых реально есть компании (с учётом scope). Раньше
        # эмитились все секторы из SECTOR_ORDER → ограниченный пользователь видел
        # чужие пустые секторы и в списке, и в фильтре-дропдауне.
        return [
            {
                "sector":       sec,
                "sector_label": SECTOR_LABELS[sec],
                "sector_color": SECTOR_COLORS[sec],
                "companies":    sector_groups[sec],
            }
            for sec in SECTOR_ORDER
            if sector_groups[sec]
        ]

    @staticmethod
    def _directions(p_rows, t_rows, dir_to_code) -> list:
        # 2026-05-25 fallback: legacy rows have direction in extra.direction
        # (string code) but direction_id is NULL. Backfill-aware код:
        # prefer FK, fallback to text code.
        valid_codes = set(dir_to_code.values())

        def _row_code(r):
            code = dir_to_code.get(r.direction_id)
            if code:
                return code
            extra = getattr(r, "extra", None) or {}
            fb = str(extra.get("direction") or "").lower().strip()
            return fb if fb in valid_codes else None

        dir_buckets: dict[str, dict] = {}
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
        out = []
        for d in DIRS:
            b = dir_buckets.get(d["id"])
            if not b:
                continue
            total = b["tasks_total"]
            prog = round(b["tasks_sum"] / total * 100) if total else 0
            out.append({
                "id":             d["id"],
                "label":          d["label"],
                "color":          d["color"],
                "projects_total": b["projects_total"],
                "projects_done":  b["projects_done"],
                "tasks_total":    b["tasks_total"],
                "tasks_done":     b["tasks_done"],
                "progress_pct":   prog,
            })
        out.sort(key=lambda d: -d["progress_pct"])
        return out

    @staticmethod
    def _build_ratings(rating_rows, co_meta) -> dict:
        co_to_ratings: dict[Any, dict] = {}
        for cid, agency, rating, score, rdate, is_esg in rating_rows:
            co_to_ratings.setdefault(cid, {})
            if agency not in co_to_ratings[cid]:
                co_to_ratings[cid][agency] = {
                    "rating": rating, "score": score,
                    "date": rdate.isoformat() if rdate else None,
                    "is_esg": is_esg,
                }

        total_companies = len(co_meta)
        ring_data = []
        for agency_name in AGENCIES_CREDIT:
            covered = sum(
                1 for cid in co_meta
                if co_to_ratings.get(cid, {}).get(agency_name)
            )
            pct = round(covered / total_companies * 100) if total_companies else 0
            ring_data.append({
                "agency": agency_name,
                "label": AGENCY_LABELS.get(agency_name, agency_name),
                "color": AGENCY_COLORS.get(agency_name, "#7F77DD"),
                "covered": covered, "total": total_companies,
                "pct": pct,
            })
        # ESG-кольцо = покрытие по ОБЪЕДИНЕНИЮ ESG-агентств (Sustainable Fitch /
        # S&P ESG / CDP), а не только Sustainable Fitch.
        esg_covered = sum(
            1 for cid in co_meta
            if any(co_to_ratings.get(cid, {}).get(a) for a in AGENCIES_ESG)
        )
        ring_data.append({
            "agency": AGENCY_ESG,
            "label": AGENCY_LABELS.get(AGENCY_ESG, "ESG"),
            "color": AGENCY_COLORS.get(AGENCY_ESG, "#1D9E75"),
            "covered": esg_covered, "total": total_companies,
            "pct": round(esg_covered / total_companies * 100) if total_companies else 0,
        })

        rating_groups: dict[str, list] = {s: [] for s in SECTOR_ORDER}
        for cid, meta in co_meta.items():
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
        for sec in SECTOR_ORDER:
            if not rating_groups[sec]:
                continue
            rows = rating_groups[sec]
            best_credit_idx, best_credit_score = -1, 0
            for idx, row in enumerate(rows):
                score = best_credit_rank(row)
                if score > best_credit_score:
                    best_credit_score, best_credit_idx = score, idx
            best_esg_idx, best_esg_score_val = -1, 0
            for idx, row in enumerate(rows):
                score = best_esg_score(row)
                if score > best_esg_score_val:
                    best_esg_score_val, best_esg_idx = score, idx
            best_credit = None
            best_esg = None
            for idx, row in enumerate(rows):
                row["is_best_credit"] = (idx == best_credit_idx and best_credit_score > 0)
                row["is_best_esg"] = (idx == best_esg_idx and best_esg_score_val > 0)
                if row["is_best_credit"]:
                    best_credit = {
                        "code": row["code"], "name": row["name"],
                        "rating": best_credit_label(row),
                    }
                if row["is_best_esg"]:
                    best_esg = {
                        "code": row["code"], "name": row["name"],
                        "score": int(best_esg_score_val),
                    }
            rating_table.append({
                "sector":       sec,
                "sector_label": SECTOR_LABELS[sec],
                "sector_color": SECTOR_COLORS[sec],
                "rows":         rows,
                "best_credit":  best_credit,
                "best_esg":     best_esg,
            })

        return {
            "rings":           ring_data,
            "table":           rating_table,
            "total_companies": total_companies,
        }

    @staticmethod
    def _build_completion(co_buckets, co_meta) -> dict:
        completion_chart = []
        sector_avg = {s: {"wsum": 0.0, "done": 0, "total": 0} for s in SECTOR_ORDER}
        for cid, meta in co_meta.items():
            bucket = co_buckets.get(cid)
            if not bucket:
                continue
            total = bucket["tasks_total"]
            done = bucket["tasks_done"]
            wsum = bucket.get("tasks_sum", 0.0)
            prog = round(wsum / total * 100) if total else 0
            sector = meta["sector"] if meta["sector"] in sector_avg else "other"
            sector_avg[sector]["wsum"] += wsum
            sector_avg[sector]["done"] += done
            sector_avg[sector]["total"] += total
            completion_chart.append({
                "code":         meta["code"],
                "name":         meta["name_short"] or meta["name_ru"],
                "sector":       sector,
                "sector_color": SECTOR_COLORS[sector],
                "tasks_total":  total,
                "tasks_done":   done,
                "progress_pct": prog,
                "projects_total": bucket["projects_total"],
                "projects_done":  bucket["projects_done"],
            })
        completion_chart.sort(key=lambda c: -c["progress_pct"])

        completion_by_sector = []
        for sec in SECTOR_ORDER:
            b = sector_avg.get(sec, {"wsum": 0.0, "done": 0, "total": 0})
            if b["total"] == 0:
                continue
            completion_by_sector.append({
                "sector":       sec,
                "sector_label": SECTOR_LABELS[sec],
                "sector_color": SECTOR_COLORS[sec],
                "tasks_total":  b["total"],
                "tasks_done":   b["done"],
                "progress_pct": round(b["wsum"] / b["total"] * 100) if b["total"] else 0,
            })
        completion_by_sector.sort(key=lambda c: -c["progress_pct"])

        # portfolio_avg = ВЗВЕШЕННЫЙ прогресс (Σвес/Σtotal), как by_company/by_sector
        # и /execution-summary — раньше был БИНАРНЫЙ done/total (9% против 29% у баров).
        total_done = sum(b["tasks_done"] for b in co_buckets.values())
        total_wsum = sum(b.get("tasks_sum", 0.0) for b in co_buckets.values())
        total_tasks = sum(b["tasks_total"] for b in co_buckets.values())
        portfolio_avg = round(total_wsum / total_tasks * 100) if total_tasks else 0

        return {
            "by_company":    completion_chart,
            "by_sector":     completion_by_sector,
            "portfolio_avg": portfolio_avg,
        }

    # ─── /dashboard/kpi-drill ─────────────────────────────────────

    async def kpi_drill(
        self,
        *,
        bucket: str, entity: str, year: Optional[int],
        sector_code: Optional[str],
        direction_code: Optional[str],
        company_code: Optional[str],
        scope_company_ids: Optional[list] = None,
    ) -> dict:
        today = datetime.now(UTC).date()
        async with self.uow:
            r = self.uow.dashboard
            allowed_board_ids = None
            if sector_code or company_code:
                co_ids = await r.resolve_company_ids(
                    sector_code=sector_code, company_code=company_code,
                )
                allowed_board_ids = await r.resolve_board_ids_for_companies(co_ids)
            # RBAC scope: ограниченный пользователь видит drill только своих
            # компаний. scope_company_ids=None → owner/view_all (без ограничения).
            if scope_company_ids is not None:
                scope_boards = set(await r.resolve_board_ids_for_companies(list(scope_company_ids)))
                if allowed_board_ids is None:
                    allowed_board_ids = scope_boards or {None}
                else:
                    allowed_board_ids = (set(allowed_board_ids) & scope_boards) or {None}
            allowed_dir_ids = None
            if direction_code:
                allowed_dir_ids = await r.resolve_direction_ids(direction_code)

            p_rows = await r.filtered_projects_drill(
                year=year, allowed_board_ids=allowed_board_ids,
                allowed_dir_ids=allowed_dir_ids,
            )
            t_rows = await r.filtered_tasks_drill(
                year=year, allowed_board_ids=allowed_board_ids,
                allowed_dir_ids=allowed_dir_ids,
            )
            board_to_company = await r.board_to_company_map()
            co_meta_raw = await r.companies_meta()

        co_meta = {
            cid: {"id": str(cid), "code": m["code"],
                  "name": m["name_short"] or m["name_ru"] or m["code"],
                  "sector": m["sector"]}
            for cid, m in co_meta_raw.items()
        }

        co_buckets: dict[Any, dict] = {}

        def _co_record(cid):
            rec = co_buckets.get(cid)
            if not rec:
                rec = {
                    "projects_total": 0, "tasks_total": 0,
                    "projects": [], "tasks": [],
                    "overdue_tasks": 0, "assignees": set(),
                }
                co_buckets[cid] = rec
            return rec

        for r_row in p_rows:
            cid = board_to_company.get(r_row.board_id)
            if cid is None:
                continue
            rec = _co_record(cid)
            rec["projects_total"] += 1
            is_o = (r_row.due_date is not None and r_row.due_date < today
                    and r_row.status != "done" and r_row.status not in RECURRING_STATUSES)
            # 2026-05-26: для bucket=deferred учитываем оба направления (incoming +
            # outgoing). matches_bucket видит только linked_year, поэтому подсовываем
            # суррогат: если linked_year=NULL но есть linked_project_id (source-side),
            # передаём sentinel-значение (-1), которое matches_bucket трактует как
            # "is not None" → попадёт в deferred bucket.
            ly_eff = r_row.linked_year if r_row.linked_year is not None else (
                -1 if getattr(r_row, "linked_project_id", None) is not None else None
            )
            if matches_bucket(r_row.status, r_row.due_date, ly_eff, today, bucket):
                d_over = (today - r_row.due_date).days if is_o else None
                rec["projects"].append(item_dict_drill(r_row, is_o, d_over))
                if r_row.assignee_email:
                    rec["assignees"].add(r_row.assignee_email.lower())

        for r_row in t_rows:
            cid = board_to_company.get(r_row.board_id)
            if cid is None:
                continue
            rec = _co_record(cid)
            rec["tasks_total"] += 1
            is_o = (r_row.due_date is not None and r_row.due_date < today
                    and r_row.status != "done" and r_row.status not in RECURRING_STATUSES)
            if is_o:
                rec["overdue_tasks"] += 1
            ly_eff = r_row.linked_year if r_row.linked_year is not None else (
                -1 if getattr(r_row, "linked_task_id", None) is not None else None
            )
            if matches_bucket(r_row.status, r_row.due_date, ly_eff, today, bucket):
                d_over = (today - r_row.due_date).days if is_o else None
                rec["tasks"].append(item_dict_drill(r_row, is_o, d_over))
                if r_row.assignee_email:
                    rec["assignees"].add(r_row.assignee_email.lower())

        companies_out: list[dict] = []
        total_projects_match = 0
        total_tasks_match = 0
        total_projects_all = 0
        total_tasks_all = 0
        all_assignees: set = set()

        for cid, rec in co_buckets.items():
            total_projects_all += rec["projects_total"]
            total_tasks_all += rec["tasks_total"]
            if not rec["projects"] and not rec["tasks"]:
                continue
            meta = co_meta.get(cid, {"id": str(cid), "code": None, "name": "—", "sector": "other"})
            total_projects_match += len(rec["projects"])
            total_tasks_match += len(rec["tasks"])
            all_assignees.update(rec["assignees"])
            rec["projects"].sort(key=item_sort_key)
            rec["tasks"].sort(key=item_sort_key)
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

        if entity == "projects":
            companies_out.sort(key=lambda c: (-c["projects_count"], -c["tasks_count"], c["company_name"]))
        else:
            companies_out.sort(key=lambda c: (-c["tasks_count"], -c["projects_count"], c["company_name"]))

        extra_value, extra_label = self._compute_extra_kpi(
            bucket, entity, companies_out,
        )

        return {
            "bucket":  bucket, "entity": entity, "year": year,
            "label":   BUCKET_LABEL.get(bucket, bucket.upper()),
            "title":   BUCKET_TITLE.get(bucket, bucket),
            "accent":  BUCKET_ACCENT.get(bucket, "#7F77DD"),
            "sector_color_map": DDM_SECTOR_COLOR,
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

    @staticmethod
    def _compute_extra_kpi(bucket, entity, companies_out):
        if bucket == "overdue":
            crit = sum(
                1 for c in companies_out
                for it in (c["tasks"] if entity == "tasks" else c["projects"])
                if (it["days_overdue"] or 0) >= 30
            )
            return crit, "критичных свыше 30 дней"
        elif bucket == "done":
            in_time = sum(
                1 for c in companies_out
                for it in (c["tasks"] if entity == "tasks" else c["projects"])
                if not it["is_overdue"]
            )
            return in_time, "в срок"
        elif bucket == "active":
            ov = sum(
                1 for c in companies_out
                for it in (c["tasks"] if entity == "tasks" else c["projects"])
                if it["is_overdue"]
            )
            return ov, "из них просрочено"
        # deferred + total
        return sum(c["overdue_tasks"] for c in companies_out), "просроченных задач"

    # ─── /dashboard/company-drill ─────────────────────────────────

    async def company_drill(
        self, *, company_code: str, year: Optional[int],
        scope_company_ids: Optional[list] = None,
    ) -> dict:
        today = datetime.now(UTC).date()
        async with self.uow:
            r = self.uow.dashboard
            co_row = await r.get_company_by_code(company_code)
            if not co_row:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    f"Company '{company_code}' not found",
                )
            cid, code, ns, nr, sec_code = co_row
            # RBAC scope: ограниченный пользователь не может «дрилить» чужую
            # компанию по прямому company_code.
            if scope_company_ids is not None and cid not in set(scope_company_ids):
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "No access to this company",
                )
            sec_code = sec_code or "other"
            b_ids = await r.board_ids_for_company(cid)
            if not b_ids:
                b_ids = {None}
            p_rows = await r.filtered_projects_drill(
                year=year, allowed_board_ids=b_ids, allowed_dir_ids=None,
            )
            t_rows = await r.filtered_tasks_drill(
                year=year, allowed_board_ids=b_ids, allowed_dir_ids=None,
            )

        def _item(rr) -> dict:
            # recurring (monthly/ongoing/quarterly) не «просрочены» по природе
            is_o = (rr.due_date is not None and rr.due_date < today
                    and rr.status != "done" and rr.status not in RECURRING_STATUSES)
            d_over = (today - rr.due_date).days if is_o else None
            return item_dict_drill(rr, is_o, d_over)

        projects = sorted([_item(rr) for rr in p_rows], key=item_sort_key)
        tasks = sorted([_item(rr) for rr in t_rows], key=item_sort_key)

        p_done = sum(1 for it in projects if it["status"] == "done")
        p_active = sum(1 for it in projects if it["status"] == "active")
        p_over = sum(1 for it in projects if it["is_overdue"])
        t_done = sum(1 for it in tasks if it["status"] == "done")
        t_active = sum(1 for it in tasks if it["status"] == "active")
        t_over = sum(1 for it in tasks if it["is_overdue"])
        # ВЗВЕШЕННЫЙ прогресс (core.progress), исключая monthly/ongoing — согласован
        # с главной (per-company) и /execution-summary; раньше был бинарный
        # done/len(tasks), причём len включал recurring → компания «1%» в дрилле
        # против ~30% на главной.
        from app.core.progress import task_weight
        _wsum = 0.0
        _wn = 0
        for rr in t_rows:
            w = task_weight(rr.status, getattr(rr, "extra", None))
            if w is None:
                continue
            _wn += 1
            _wsum += w
        progress_pct = round(_wsum / _wn * 100) if _wn else 0

        assignees: set = set()
        for rr in p_rows:
            if rr.assignee_email:
                assignees.add(rr.assignee_email.lower())
        for rr in t_rows:
            if rr.assignee_email:
                assignees.add(rr.assignee_email.lower())

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
                "sector_label": SECTOR_LABELS.get(sec_code, sec_code),
                "sector_color": SECTOR_COLORS.get(sec_code, "#888780"),
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
