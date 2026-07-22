"""Use cases for Consultants — list/CRUD + dashboard overview + per-company."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.exc import IntegrityError

from app.core.progress import compute_done_total, weighted_pct
from app.models.consultant import Consultant
from app.services.consultants._helpers import (
    CODE_RE,
    DIR_ID_TO_COLOR,
    DIR_ID_TO_LABEL,
    is_overdue_task,
    serialize_consultant,
    slugify_consultant,
)
from app.uow.ports import UnitOfWorkABC


class ConsultantsService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── admin list / CRUD ────────────────────────────────────────

    async def list_consultants(self, *, include_inactive: bool) -> dict:
        async with self.uow:
            rows = await self.uow.consultants.list_all(include_inactive=include_inactive)
        return {"consultants": [serialize_consultant(c) for c in rows]}

    async def create_consultant(self, *, payload) -> dict:
        code = (payload.code or slugify_consultant(payload.name)).lower()
        if not CODE_RE.match(code):
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "code must match ^[a-z][a-z0-9_]{0,63}$",
            )
        async with self.uow:
            exists = await self.uow.consultants.get_by_code(code)
            if exists:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Consultant with code '{code}' already exists",
                )
            c = Consultant(
                code=code,
                name_ru=payload.name,
                name_en=payload.name_en,
                abbr=payload.abbr,
                color_hex=payload.color,
                is_big4=payload.is_big4,
                is_active=payload.is_active,
                sort_order=payload.sort_order,
            )
            self.uow.consultants.add(c)
            try:
                await self.uow.consultants.flush()
            except IntegrityError:
                # гонка: код заняли между get_by_code и flush → аккуратный 409,
                # а не 500 (uq на consultants.code — источник истины).
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Consultant with code '{code}' already exists",
                )
            await self.uow.consultants.refresh(c)
            return serialize_consultant(c)

    async def update_consultant(self, consultant_id: UUID, *, payload) -> dict:
        async with self.uow:
            c = await self.uow.consultants.get(consultant_id)
            if not c:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Consultant not found")
            changes = payload.model_dump(exclude_unset=True)
            if "name" in changes:
                c.name_ru = changes.pop("name")
            if "color" in changes:
                c.color_hex = changes.pop("color")
            for k, v in changes.items():
                setattr(c, k, v)
            await self.uow.consultants.flush()
            await self.uow.consultants.refresh(c)
            return serialize_consultant(c)

    async def consultant_usage(self, consultant_id: UUID) -> dict:
        async with self.uow:
            c = await self.uow.consultants.get(consultant_id)
            if not c:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Consultant not found")
            cnt = await self.uow.consultants.count_assignments(consultant_id)
        return {"assignments": cnt, "code": c.code, "name": c.name_ru}

    async def delete_consultant(self, consultant_id: UUID, *, hard: bool) -> None:
        async with self.uow:
            c = await self.uow.consultants.get(consultant_id)
            if not c:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Consultant not found")
            if hard:
                await self.uow.consultants.delete(c)
            else:
                c.is_active = False
            await self.uow.consultants.flush()

    # ─── overview dashboard ───────────────────────────────────────

    async def overview(
        self, *, year: Optional[int],
        allowed_company_ids: Optional[list] = None,
    ) -> dict[str, Any]:
        # per-company scope (P0): None → все компании; [] → нет доступа (пусто);
        # [ids] → только эти. Прокидываем в выборку задач.
        async with self.uow:
            r = self.uow.consultants
            available_years = await r.available_task_years()
            all_cons = await r.list_active()
            cons_by_id = {c.id: c for c in all_cons}

            t_rows = await r.list_active_tasks(year=year, company_ids=allowed_company_ids)
            task_by_id = {
                row[0]: {
                    "id": row[0], "num": row[1], "title": row[2], "status": row[3],
                    "due_date": row[4], "direction_id": row[5], "board_id": row[6],
                    "portfolio_year": row[7], "company_id": row[9], "extra": row[10],
                }
                for row in t_rows
            }
            ca_rows = await r.list_assignments_for_tasks(list(task_by_id.keys()))

            board_ids = {row[6] for row in t_rows if row[6]}
            b_rows = await r.boards_with_company(list(board_ids))
            co_ids = {row[2] for row in b_rows if row[2]}
            # имена/цвета компаний: прямой Task.company_id (row[9]) + через доску.
            # Раньше цвета брались только по board-компаниям → компании задач БЕЗ
            # доски рисовались серым в heatmap. Теперь по объединению.
            direct_co_ids = {row[9] for row in t_rows if row[9]}
            all_co_ids = co_ids | direct_co_ids
            co_to_sector_color = await r.company_sector_colors(list(all_co_ids))
            company_names = await r.company_names(list(all_co_ids))
            boards_data = {
                bid: {
                    "id": str(bid), "name": bname,
                    "sector_color": co_to_sector_color.get(co_id, "#888"),
                    "company_id": co_id,
                }
                for bid, bname, co_id in b_rows
            }
            dir_rows = await r.list_directions()
            inactive_co = await r.inactive_company_ids()

        # Деактивированные компании исключаем из портфельного overview: убираем
        # их задачи (компания = прямой company_id ЛИБО через доску) до подсчёта
        # покрытия/KPI/heatmap/dirs. Per-company view (by_company) не трогаем.
        if inactive_co:
            task_by_id = {
                tid: t for tid, t in task_by_id.items()
                if (t.get("company_id") or boards_data.get(t["board_id"], {}).get("company_id")) not in inactive_co
            }

        # task_id → set(consultant_ids), and reverse.
        # Назначения НЕактивных консультантов пропускаем (cons_by_id = только
        # активные): раньше они раздували tasks_covered/companies_covered/dirs,
        # но не показывались ни у одного консультанта — цифры не сходились (P1).
        task_to_cids: dict[Any, set] = {}
        cid_to_tids: dict[Any, set] = {c.id: set() for c in all_cons}
        for tid, cid in ca_rows:
            if cid not in cons_by_id:
                continue
            if tid not in task_by_id:   # задача отфильтрована (деактивир. компания)
                continue
            task_to_cids.setdefault(tid, set()).add(cid)
            cid_to_tids.setdefault(cid, set()).add(tid)
        consulted_task_ids = set(task_to_cids.keys())
        consulted_tasks = [task_by_id[tid] for tid in consulted_task_ids]

        # ── KPI bar ──
        # Компания задачи = прямой Task.company_id, иначе через доску (задачи без
        # доски раньше терялись из покрытия — P1).
        def _company_of(t: dict) -> Any:
            return t.get("company_id") or boards_data.get(t["board_id"], {}).get("company_id")
        companies_covered = len({_company_of(t) for t in consulted_tasks} - {None})
        # «Активен» по ФАКТУ работы, а не по наличию назначения (флаг≠факт):
        # хотя бы одна задача в начатом/рабочем/рекуррентном статусе (не new/deferred).
        _NOT_STARTED = {"new", "deferred"}
        consultants_active = sum(
            1 for c in all_cons
            if any(task_by_id[tid]["status"] not in _NOT_STARTED
                   for tid in cid_to_tids.get(c.id, ()))
        )
        # Взвешенный прогресс (core/progress): monthly/ongoing вне знаменателя,
        # quarterly по кварталам, active/review — частично (НЕ done/total, P0).
        avg_completion = weighted_pct((t["status"], t["extra"]) for t in consulted_tasks)
        kpis = {
            "tasks_covered": len(consulted_tasks),
            "companies_covered": companies_covered,
            "consultants_active": consultants_active,
            "avg_completion_pct": avg_completion,
        }

        # ── Per-consultant stats ──
        cons_stats: list[dict] = []
        for c in all_cons:
            tids = cid_to_tids.get(c.id, set())
            if not tids:
                continue
            items = [(task_by_id[tid]["status"], task_by_id[tid]["extra"]) for tid in tids]
            done_cnt, _elig = compute_done_total(items)
            tasks_overdue = sum(
                1 for tid in tids
                if is_overdue_task(task_by_id[tid]["status"], task_by_id[tid]["due_date"])
            )
            cons_stats.append({
                "id": str(c.id), "code": c.code, "name": c.name_ru,
                "abbr": c.abbr, "color": c.color_hex, "is_big4": c.is_big4,
                "tasks_total": len(tids), "tasks_done": done_cnt,
                "tasks_overdue": tasks_overdue,
                "completion_pct": weighted_pct(items),
            })
        cons_stats.sort(key=lambda x: (-x["is_big4"], -x["tasks_total"]))

        # ── Heatmap: КОМПАНИЯ × консультанты ──
        # Раньше строка = ДОСКА → компания с N досок давала N строк, а задачи БЕЗ
        # доски (прямой Task.company_id) вообще выпадали из heatmap. Теперь агрегируем
        # по РАЗРЕШЁННОЙ компании (_company_of: прямая ЛИБО через доску) — доски одной
        # компании сворачиваются в одну строку, задачи без доски учитываются.
        # NB: ключ строки исторически называется "board", но НЕСЁТ company-данные
        # (id/name/sector_color компании); фронт рендерит r.board.name = имя компании,
        # drill фильтрует по company_id (task.company_id уже разрешён на бэке).
        visible_cons_ids = [c["id"] for c in cons_stats]
        company_of_tid = {tid: _company_of(task_by_id[tid]) for tid in consulted_task_ids}
        heat_company_ids = sorted(
            {cid for cid in company_of_tid.values() if cid is not None},
            key=lambda cid: (company_names.get(cid) or ""),
        )
        heatmap_rows: list[dict] = []
        g_max = 0
        for co_id in heat_company_ids:
            row_counts: list[int] = []
            any_cell = False
            for cid_str in visible_cons_ids:
                try:
                    cid_uuid = UUID(cid_str)
                except Exception:
                    cid_uuid = cid_str
                count = sum(
                    1 for tid in cid_to_tids.get(cid_uuid, set())
                    if company_of_tid.get(tid) == co_id
                )
                if count > 0:
                    any_cell = True
                if count > g_max:
                    g_max = count
                row_counts.append(count)
            if any_cell:
                heatmap_rows.append({
                    "board": {
                        "id": str(co_id),
                        "name": company_names.get(co_id) or "—",
                        "sector_color": co_to_sector_color.get(co_id, "#888"),
                        "company_id": str(co_id),
                    },
                    "counts": row_counts,
                })
        heatmap = {
            "consultants": [
                {"id": c["id"], "code": c["code"], "name": c["name"],
                 "abbr": c["abbr"], "color": c["color"], "is_big4": c["is_big4"]}
                for c in cons_stats
            ],
            "rows": heatmap_rows,
            "max": g_max,
        }

        # ── Direction stats ──
        dir_id_to_meta: dict[Any, dict] = {}
        for did, dcode, dname in dir_rows:
            dir_id_to_meta[did] = {
                "id": dcode,
                "label": DIR_ID_TO_LABEL.get(dcode, dname or dcode),
                "color": DIR_ID_TO_COLOR.get(dcode, "#888"),
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
                "id": meta["id"], "label": meta["label"], "color": meta["color"],
                "tasks_total": 0, "tasks_overdue": 0,
                "items": [], "consultant_codes": set(),
            })
            bucket["tasks_total"] += 1
            bucket["items"].append((t["status"], t["extra"]))
            if is_overdue_task(t["status"], t["due_date"]):
                bucket["tasks_overdue"] += 1
            for cid in cids_set:
                c_obj = cons_by_id.get(cid)
                if c_obj:
                    bucket["consultant_codes"].add(c_obj.code)
        dirs_payload = []
        for v in dir_stats.values():
            done_cnt, _elig = compute_done_total(v["items"])
            dirs_payload.append({
                "id": v["id"], "label": v["label"], "color": v["color"],
                "tasks_total": v["tasks_total"], "tasks_done": done_cnt,
                "tasks_overdue": v["tasks_overdue"],
                "completion_pct": weighted_pct(v["items"]),
                "consultant_codes": sorted(list(v["consultant_codes"])),
            })
        dirs_payload.sort(key=lambda x: -x["completion_pct"])

        # ── All consulted tasks (sorted by due_date desc) ──
        # 2026-05-26: было capped [:20] — теперь отдаём весь список с board_id,
        # чтобы frontend мог фильтровать на drill-modal'ях (cell/direction/consultant).
        sorted_consulted = sorted(
            consulted_tasks,
            key=lambda t: (t["due_date"] or date(1970, 1, 1)),
            reverse=True,
        )
        projects_payload = []
        for t in sorted_consulted:
            b = boards_data.get(t["board_id"]) if t["board_id"] else None
            cs_in_task = []
            for cid in task_to_cids.get(t["id"], set()):
                c_obj = cons_by_id.get(cid)
                if c_obj:
                    cs_in_task.append({
                        "id": str(c_obj.id),
                        "code": c_obj.code, "abbr": c_obj.abbr,
                        "color": c_obj.color_hex,
                    })
            dir_meta = dir_id_to_meta.get(t["direction_id"]) if t["direction_id"] else None
            comp_id = _company_of(t)   # прямой Task.company_id или через доску
            projects_payload.append({
                "id": str(t["id"]),
                "num": t["num"], "title": t["title"],
                "board_id": str(t["board_id"]) if t["board_id"] else None,
                "board_name": b["name"] if b else None,
                "company_id": str(comp_id) if comp_id else None,
                "company_name": company_names.get(comp_id) if comp_id else None,
                "status": t["status"],
                "due_date": t["due_date"].isoformat() if t["due_date"] else None,
                "direction_id": dir_meta["id"] if dir_meta else None,
                "direction_label": dir_meta["label"] if dir_meta else None,
                "consultants": cs_in_task,
            })

        return {
            "kpis": kpis, "consultants": cons_stats,
            "heatmap": heatmap, "dirs": dirs_payload,
            "projects": projects_payload,
            "available_years": available_years,
            "selected_year": year,
        }

    # ─── per-company consultants ──────────────────────────────────

    async def by_company(
        self,
        company_id: UUID,
        *,
        year: Optional[int],
    ) -> dict[str, Any]:
        async with self.uow:
            co = await self.uow.consultants.get_company(company_id)
            if not co:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "company not found")
            t_rows = await self.uow.consultants.list_company_active_tasks(
                company_id, year=year,
            )
            if not t_rows:
                return {
                    "company_id": str(company_id),
                    "year": year, "consultants": [],
                    "total_assignments": 0, "total_consultants": 0,
                }
            task_by_id = {
                row[0]: {
                    "id": row[0], "num": row[1], "title": row[2],
                    "status": row[3], "due_date": row[4],
                    "portfolio_year": row[5], "extra": row[6],
                }
                for row in t_rows
            }
            ca_rows = await self.uow.consultants.list_assignments_for_tasks(
                list(task_by_id.keys()), include_source=True,
            )
            if not ca_rows:
                return {
                    "company_id": str(company_id),
                    "year": year, "consultants": [],
                    "total_assignments": 0, "total_consultants": 0,
                }

            # Group by consultant
            cid_to_data: dict[Any, dict] = {}
            for tid, cid, src in ca_rows:
                bucket = cid_to_data.setdefault(cid, {"tasks": set(), "sources": set()})
                bucket["tasks"].add(tid)
                bucket["sources"].add(src or "task")
            cons_by_id = await self.uow.consultants.get_by_ids(list(cid_to_data.keys()))

        result: list[dict] = []
        for cid, data in cid_to_data.items():
            c = cons_by_id.get(cid)
            if not c:
                continue
            tids = data["tasks"]
            task_count = len(tids)
            items = [(task_by_id[tid]["status"], task_by_id[tid]["extra"]) for tid in tids]
            task_done, _elig = compute_done_total(items)
            task_overdue = sum(
                1 for tid in tids
                if is_overdue_task(task_by_id[tid]["status"], task_by_id[tid]["due_date"])
            )
            sample_tids = sorted(
                tids,
                key=lambda tid: (task_by_id[tid]["due_date"] or date(1970, 1, 1)),
                reverse=True,
            )[:5]
            projects = [
                {
                    "id": str(task_by_id[tid]["id"]),
                    "num": task_by_id[tid]["num"],
                    "title": task_by_id[tid]["title"],
                    "status": task_by_id[tid]["status"],
                    "due_date": task_by_id[tid]["due_date"].isoformat()
                                if task_by_id[tid]["due_date"] else None,
                }
                for tid in sample_tids
            ]
            result.append({
                "id": str(c.id), "code": c.code, "name": c.name_ru,
                "abbr": c.abbr, "color": c.color_hex, "is_big4": c.is_big4,
                "task_count": task_count,
                "task_done": task_done,
                "task_overdue": task_overdue,
                "completion_pct": weighted_pct(items),
                "sources": sorted(list(data["sources"])),
                "projects": projects,
            })
        result.sort(key=lambda x: (-int(x["is_big4"]), -x["task_count"], x["name"] or ""))

        # Сводное «Выполнение задач» по компании — ВЗВЕШЕННОЕ по дедуп-объединению
        # всех консультируемых задач (не done/total на фронте, иначе цифра
        # расходилась и со своими же карточками, и с полностраничным модулем;
        # monthly/ongoing взвешивание исключает — как core/progress.py).
        consulted_tids = {tid for tid, _cid, _src in ca_rows}
        company_items = [
            (task_by_id[tid]["status"], task_by_id[tid]["extra"])
            for tid in consulted_tids
            if tid in task_by_id
        ]
        company_completion = weighted_pct(company_items)

        return {
            "company_id": str(company_id),
            "year": year,
            "consultants": result,
            "total_assignments": len(ca_rows),
            "total_consultants": len(result),
            "completion_pct": company_completion,
        }
