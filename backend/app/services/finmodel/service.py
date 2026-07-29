"""Use cases for FinModel v2.

Core services NOT touched:
- `app/services/finmodel_engine.py` — FormulaEngine (compute/balance_check)
- `app/services/finmodel_importer.py` — parse_excel, build_commit_payload
- `app/services/finmodel_validator.py` — validate()
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.core.i18n import current_locale, tr
from app.models.finmodel import (
    FinModelAuditLog,
    FinModelCellComment,
    FinModelCellValue,
    FinModelMacroCompany,
    FinModelScenario,
    FinModelYearLock,
)
from app.schemas.finmodel import (
    AuditEntry,
    AuditList,
    CellBatchWrite,
    CellValueRead,
    CellWrite,
    CommentCreate,
    CommentRead,
    ForecastRequest,
    MacroCompanyWrite,
    MacroEffective,
    MacroGlobalRead,
    ScenarioCreate,
    ScenarioRead,
    TemplateRowRead,
    ValidationIssue,
    YearDataRead,
    YearLockRead,
    YearLockUpdate,
)
from app.services.finmodel_engine import FormulaEngine
from app.services.finmodel_importer import build_commit_payload, parse_excel
from app.services.finmodel_validator import validate as run_validation
from app.uow.ports import UnitOfWorkABC

PL_INPUT_CODES_FOR_FORECAST = [
    "PL_010", "PL_020", "PL_050", "PL_060", "PL_070", "PL_080",
    "PL_120", "PL_130", "PL_140", "PL_150", "PL_160",
    "PL_180", "PL_190", "PL_200", "PL_210", "PL_230",
    "PL_250", "PL_260",
]


def _is_locked(lock: Optional[FinModelYearLock]) -> bool:
    return bool(lock and lock.status in ("locked", "approved"))


class FinModelService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── helpers (internal) ───────────────────────────────────────

    async def _ensure_company(self, company_id: UUID):
        c = await self.uow.finmodel.get_company(company_id)
        if c is None:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, f"Company {company_id} not found",
            )
        return c

    async def _resolve_macro(self, company_id: UUID, year: int) -> MacroEffective:
        co = await self.uow.finmodel.get_macro_company(company_id, year)
        gl = await self.uow.finmodel.get_macro_global(year)
        out = MacroEffective(year=year)
        for field in (
            "uz_inflation", "us_inflation", "uzs_usd_avg_rate",
            "uzs_eur_avg_rate", "uzs_rub_avg_rate", "uzs_cny_avg_rate",
        ):
            if co and getattr(co, field, None) is not None:
                setattr(out, field, getattr(co, field))
                out.source[field] = "company"
            elif gl and getattr(gl, field, None) is not None:
                setattr(out, field, getattr(gl, field))
                out.source[field] = "global"
            else:
                out.source[field] = "none"
        return out

    def _add_audit(
        self, *, company_id: UUID, year: int, row_code: str,
        value_before: Optional[Decimal], value_after: Optional[Decimal],
        actor_id: Optional[UUID], source: str,
    ) -> None:
        self.uow.finmodel.add(FinModelAuditLog(
            company_id=company_id, year=year, row_code=row_code,
            value_before=value_before, value_after=value_after,
            actor_id=actor_id, source=source,
        ))

    # ─── reads ────────────────────────────────────────────────────

    async def get_template(self) -> list[TemplateRowRead]:
        async with self.uow:
            return await self.uow.finmodel.load_template()

    async def list_macro_global(self) -> list[MacroGlobalRead]:
        async with self.uow:
            rows = await self.uow.finmodel.list_macro_global()
        return [MacroGlobalRead.model_validate(r) for r in rows]

    async def list_scenarios(self, company_id: UUID) -> list[ScenarioRead]:
        async with self.uow:
            rows = await self.uow.finmodel.list_scenarios(company_id)
        return [ScenarioRead.model_validate(s) for s in rows]

    async def list_comments(
        self, company_id: UUID, year: Optional[int],
    ) -> list[CommentRead]:
        async with self.uow:
            rows = await self.uow.finmodel.list_comments(company_id, year)
        return [CommentRead.model_validate(c) for c in rows]

    async def list_years(self, company_id: UUID) -> list[YearLockRead]:
        async with self.uow:
            await self._ensure_company(company_id)
            cell_years = await self.uow.finmodel.distinct_cell_years(company_id)
            locks_list = await self.uow.finmodel.list_year_locks(company_id)
        locks_by_year = {l.year: l for l in locks_list}
        all_years = sorted(cell_years | set(locks_by_year.keys()))
        out: list[YearLockRead] = []
        for y in all_years:
            if y in locks_by_year:
                out.append(YearLockRead.model_validate(locks_by_year[y]))
            else:
                out.append(YearLockRead(year=y, status="draft"))
        return out

    async def get_year(self, company_id: UUID, year: int) -> YearDataRead:
        async with self.uow:
            await self._ensure_company(company_id)
            cells = await self.uow.finmodel.load_year_cells(company_id, year)
            macro = await self._resolve_macro(company_id, year)
            lock = await self.uow.finmodel.get_year_lock(company_id, year)
            template = await self.uow.finmodel.load_template()

        lock_data = YearLockRead.model_validate(lock) if lock else YearLockRead(
            year=year, status="draft",
        )
        engine = FormulaEngine(template)
        input_values = {c.row_code: c.value for c in cells if c.value is not None}
        computed = engine.compute_all(input_values)
        balance = engine.balance_check(computed)
        return YearDataRead(
            company_id=company_id, year=year,
            lock=lock_data, macro=macro,
            cells=[CellValueRead.model_validate(c) for c in cells],
            balance_check=balance,
        )

    async def export_year_csv(
        self, company_id: UUID, year: int, *, include_macro: bool,
    ) -> bytes:
        async with self.uow:
            await self._ensure_company(company_id)
            template = await self.uow.finmodel.load_template()
            cells = await self.uow.finmodel.load_year_cells(company_id, year)
            macro = await self._resolve_macro(company_id, year) if include_macro else None

        engine = FormulaEngine(template)
        input_values = {c.row_code: c.value for c in cells if c.value is not None}
        computed = engine.compute_all(input_values)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["section", "code", "name_ru", "row_type", "value", "is_input", "formula"])
        for r in template:
            v = computed.get(r.code)
            v_str = "" if v is None else str(v)
            w.writerow([
                r.section, r.code, r.name_ru, r.row_type, v_str,
                "1" if r.row_type == "input" else "0",
                r.formula or "",
            ])
        if include_macro and macro:
            w.writerow([])
            w.writerow(["macro", "field", "value", "source"])
            for fld in (
                "uz_inflation", "us_inflation",
                "uzs_usd_avg_rate", "uzs_eur_avg_rate",
                "uzs_rub_avg_rate", "uzs_cny_avg_rate",
            ):
                val = getattr(macro, fld, None)
                src = macro.source.get(fld, "none") if macro.source else "none"
                w.writerow(["macro", fld, "" if val is None else str(val), src])
        return buf.getvalue().encode("utf-8-sig")

    async def get_audit(
        self, company_id: UUID, year: int, *, row_code: Optional[str], limit: int,
    ) -> AuditList:
        async with self.uow:
            items, total = await self.uow.finmodel.list_audit(
                company_id=company_id, year=year, row_code=row_code, limit=limit,
            )
        return AuditList(
            items=[AuditEntry.model_validate(x) for x in items], total=total,
        )

    async def validate_year(
        self, company_id: UUID, year: int,
    ) -> list[ValidationIssue]:
        async with self.uow:
            cells = await self.uow.finmodel.load_year_cells(company_id, year)
            template = await self.uow.finmodel.load_template()
        engine = FormulaEngine(template)
        inputs = {c.row_code: c.value for c in cells if c.value is not None}
        computed = engine.compute_all(inputs)
        return run_validation(computed)

    # ─── writes ───────────────────────────────────────────────────

    async def patch_cell(
        self, company_id: UUID, year: int, body: CellWrite, *, user_id: UUID,
    ) -> CellValueRead:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            if _is_locked(await r.get_year_lock(company_id, year)):
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    tr(
                        "Год {year} заблокирован — снимите блокировку",
                        current_locale(), year=year,
                    ),
                )
            row = await r.get_template_row(body.row_code)
            if row is None:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Unknown row_code: {body.row_code}",
                )
            if row.row_type != "input":
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Row {body.row_code} is computed ({row.row_type}), cannot edit directly",
                )
            cell = await r.get_cell(company_id, year, body.row_code)
            value_before = cell.value if cell else None
            if cell:
                cell.value = body.value
                cell.updated_by = user_id
            else:
                cell = FinModelCellValue(
                    company_id=company_id, year=year, row_code=body.row_code,
                    value=body.value, is_calculated=False, updated_by=user_id,
                )
                r.add(cell)
            self._add_audit(
                company_id=company_id, year=year, row_code=body.row_code,
                value_before=value_before, value_after=body.value,
                actor_id=user_id, source="manual",
            )
            await r.flush()
            await r.refresh(cell)
            return CellValueRead.model_validate(cell)

    async def patch_cells_batch(
        self, company_id: UUID, year: int, body: CellBatchWrite, *, user_id: UUID,
    ) -> list[CellValueRead]:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            if _is_locked(await r.get_year_lock(company_id, year)):
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    tr("Год {year} заблокирован", current_locale(), year=year),
                )
            template = await r.load_template()
            rows_by_code = {tr.code: tr for tr in template}
            for c in body.cells:
                tr = rows_by_code.get(c.row_code)
                if tr is None:
                    raise HTTPException(
                        http_status.HTTP_400_BAD_REQUEST,
                        f"Unknown row_code: {c.row_code}",
                    )
                if tr.row_type != "input":
                    raise HTTPException(
                        http_status.HTTP_400_BAD_REQUEST,
                        f"Row {c.row_code} is computed, cannot edit",
                    )
            existing = await r.get_cells_by_codes(
                company_id, year, [c.row_code for c in body.cells],
            )
            existing_by_code = {x.row_code: x for x in existing}
            out_cells: list[FinModelCellValue] = []
            for c in body.cells:
                cell = existing_by_code.get(c.row_code)
                prev = cell.value if cell else None
                if cell:
                    cell.value = c.value
                    cell.updated_by = user_id
                else:
                    cell = FinModelCellValue(
                        company_id=company_id, year=year, row_code=c.row_code,
                        value=c.value, is_calculated=False, updated_by=user_id,
                    )
                    r.add(cell)
                out_cells.append(cell)
                self._add_audit(
                    company_id=company_id, year=year, row_code=c.row_code,
                    value_before=prev, value_after=c.value,
                    actor_id=user_id, source="manual",
                )
            await r.flush()
            for c in out_cells:
                await r.refresh(c)
            return [CellValueRead.model_validate(c) for c in out_cells]

    async def get_macro(self, company_id: UUID, year: int) -> MacroEffective:
        async with self.uow:
            await self._ensure_company(company_id)
            return await self._resolve_macro(company_id, year)

    async def put_macro(
        self, company_id: UUID, year: int, body: MacroCompanyWrite, *, user_id: UUID,
    ) -> MacroEffective:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            if _is_locked(await r.get_year_lock(company_id, year)):
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    tr("Год {year} заблокирован", current_locale(), year=year),
                )
            existing = await r.get_macro_company(company_id, year)
            fields = (
                "uz_inflation", "us_inflation", "uzs_usd_avg_rate",
                "forecast_method", "manual_growth_pct", "dividend_payout_ratio",
            )
            if existing:
                for f in fields:
                    v = getattr(body, f, None)
                    if v is not None:
                        setattr(existing, f, v)
                existing.updated_by = user_id
            else:
                kwargs = {f: getattr(body, f, None) for f in fields}
                kwargs["company_id"] = company_id
                kwargs["year"] = year
                kwargs["updated_by"] = user_id
                r.add(FinModelMacroCompany(**kwargs))
            await r.flush()
            return await self._resolve_macro(company_id, year)

    # ─── year lifecycle ───────────────────────────────────────────

    async def create_year(self, company_id: UUID, year: int) -> YearLockRead:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            existing = await r.get_year_lock(company_id, year)
            if existing:
                return YearLockRead.model_validate(existing)
            lock = FinModelYearLock(company_id=company_id, year=year, status="draft")
            r.add(lock)
            await r.flush()
            await r.refresh(lock)
            return YearLockRead.model_validate(lock)

    async def delete_year(self, company_id: UUID, year: int, *, user_id: UUID) -> None:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            if _is_locked(await r.get_year_lock(company_id, year)):
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    tr(
                        "Год {year} заблокирован — снимите блокировку перед удалением",
                        current_locale(), year=year,
                    ),
                )
            await r.delete_cells_for_year(company_id, year)
            await r.delete_macro_company_for_year(company_id, year)
            await r.delete_year_lock(company_id, year)
            await r.delete_comments_for_year(company_id, year)
            self._add_audit(
                company_id=company_id, year=year, row_code="*",
                value_before=None, value_after=None,
                actor_id=user_id, source="manual_year_delete",
            )
            await r.flush()

    async def copy_year(
        self, company_id: UUID, year: int, src_year: int, *, user_id: UUID,
    ) -> YearLockRead:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            if _is_locked(await r.get_year_lock(company_id, year)):
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    tr("Год {year} заблокирован", current_locale(), year=year),
                )
            src_cells = await r.load_year_cells(company_id, src_year)
            if not src_cells:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    tr(
                        "В исходном году {year} нет данных",
                        current_locale(), year=src_year,
                    ),
                )
            await r.delete_cells_for_year(company_id, year)
            for sc in src_cells:
                if sc.value is None:
                    continue
                r.add(FinModelCellValue(
                    company_id=company_id, year=year, row_code=sc.row_code,
                    value=sc.value, is_calculated=False, updated_by=user_id,
                ))
                self._add_audit(
                    company_id=company_id, year=year, row_code=sc.row_code,
                    value_before=None, value_after=sc.value,
                    actor_id=user_id, source=f"copy_from_{src_year}",
                )
            lock = await r.get_year_lock(company_id, year)
            if not lock:
                lock = FinModelYearLock(company_id=company_id, year=year, status="draft")
                r.add(lock)
            await r.flush()
            await r.refresh(lock)
            return YearLockRead.model_validate(lock)

    async def lock_year(
        self, company_id: UUID, year: int, body: YearLockUpdate, *, user_id: UUID,
    ) -> YearLockRead:
        async with self.uow:
            r = self.uow.finmodel
            lock = await r.get_year_lock(company_id, year)
            now = datetime.utcnow()
            if not lock:
                lock = FinModelYearLock(
                    company_id=company_id, year=year, status=body.status,
                    approval_note=body.approval_note,
                    locked_at=now, locked_by=user_id,
                )
                r.add(lock)
            else:
                lock.status = body.status
                lock.approval_note = body.approval_note
                lock.locked_at = now
                lock.locked_by = user_id
            await r.flush()
            await r.refresh(lock)
            return YearLockRead.model_validate(lock)

    async def unlock_year(self, company_id: UUID, year: int) -> YearLockRead:
        async with self.uow:
            r = self.uow.finmodel
            lock = await r.get_year_lock(company_id, year)
            if not lock:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Year lock not found",
                )
            lock.status = "draft"
            lock.locked_at = None
            lock.locked_by = None
            await r.flush()
            await r.refresh(lock)
            return YearLockRead.model_validate(lock)

    # ─── scenarios ────────────────────────────────────────────────

    async def create_scenario(
        self, company_id: UUID, body: ScenarioCreate, *, user_id: UUID,
    ) -> ScenarioRead:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            cells = await r.list_all_cells_for_company(company_id)
            macros = await r.list_macro_company_for_company(company_id)
            snapshot = {
                "cells": [
                    {
                        "year": c.year, "row_code": c.row_code,
                        "value": str(c.value) if c.value is not None else None,
                    }
                    for c in cells
                ],
                "macro": [
                    {
                        "year": m.year,
                        "uz_inflation": str(m.uz_inflation) if m.uz_inflation is not None else None,
                        "us_inflation": str(m.us_inflation) if m.us_inflation is not None else None,
                        "uzs_usd_avg_rate": str(m.uzs_usd_avg_rate) if m.uzs_usd_avg_rate is not None else None,
                        "forecast_method": m.forecast_method,
                        "manual_growth_pct": str(m.manual_growth_pct) if m.manual_growth_pct is not None else None,
                        "dividend_payout_ratio": str(m.dividend_payout_ratio) if m.dividend_payout_ratio is not None else None,
                    }
                    for m in macros
                ],
            }
            s = FinModelScenario(
                company_id=company_id, name=body.name, description=body.description,
                is_active=False, snapshot_data=snapshot, created_by=user_id,
            )
            r.add(s)
            await r.flush()
            await r.refresh(s)
            return ScenarioRead.model_validate(s)

    async def activate_scenario(
        self, company_id: UUID, scenario_id: UUID, *, user_id: UUID,
    ) -> ScenarioRead:
        async with self.uow:
            r = self.uow.finmodel
            s = await r.get_scenario(company_id, scenario_id)
            if not s:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Scenario not found",
                )
            years_in_snap = {c["year"] for c in (s.snapshot_data.get("cells") or [])}
            locks = await r.list_year_locks_for_years(company_id, list(years_in_snap))
            locked_years = {
                l.year for l in locks
                if l.status in ("locked", "approved")
            }
            applicable_years = years_in_snap - locked_years

            await r.delete_cells_for_years(company_id, list(applicable_years))
            for c in s.snapshot_data.get("cells", []):
                if c["year"] not in applicable_years:
                    continue
                v = Decimal(c["value"]) if c["value"] is not None else None
                r.add(FinModelCellValue(
                    company_id=company_id, year=c["year"], row_code=c["row_code"],
                    value=v, is_calculated=False, updated_by=user_id,
                ))
                self._add_audit(
                    company_id=company_id, year=c["year"], row_code=c["row_code"],
                    value_before=None, value_after=v,
                    actor_id=user_id, source="scenario_load",
                )
            await r.delete_macro_company_for_years(company_id, list(applicable_years))
            for m in s.snapshot_data.get("macro", []):
                if m["year"] not in applicable_years:
                    continue
                kwargs = {
                    "company_id": company_id, "year": m["year"], "updated_by": user_id,
                }
                for f in (
                    "uz_inflation", "us_inflation", "uzs_usd_avg_rate",
                    "manual_growth_pct", "dividend_payout_ratio",
                ):
                    kwargs[f] = Decimal(m[f]) if m.get(f) is not None else None
                kwargs["forecast_method"] = m.get("forecast_method") or "uz_inflation"
                r.add(FinModelMacroCompany(**kwargs))
            await r.deactivate_all_scenarios(company_id)
            s.is_active = True
            await r.flush()
            await r.refresh(s)
            return ScenarioRead.model_validate(s)

    async def delete_scenario(self, company_id: UUID, scenario_id: UUID) -> None:
        async with self.uow:
            await self.uow.finmodel.delete_scenario(company_id, scenario_id)

    # ─── comments ─────────────────────────────────────────────────

    async def add_comment(
        self, company_id: UUID, year: int, body: CommentCreate, *, user_id: UUID,
    ) -> CommentRead:
        async with self.uow:
            r = self.uow.finmodel
            c = FinModelCellComment(
                company_id=company_id, year=year, row_code=body.row_code,
                comment_text=body.comment_text, source_ref=body.source_ref,
                author_id=user_id,
            )
            r.add(c)
            await r.flush()
            await r.refresh(c)
            return CommentRead.model_validate(c)

    async def delete_comment(self, company_id: UUID, comment_id: UUID) -> None:
        async with self.uow:
            await self.uow.finmodel.delete_comment(comment_id, company_id)

    # ─── Excel import ─────────────────────────────────────────────

    async def import_excel_preview(
        self, company_id: UUID, raw_bytes: bytes, *, sheet_name: Optional[str],
    ) -> dict:
        async with self.uow:
            await self._ensure_company(company_id)
            template = await self.uow.finmodel.load_template()
        known_codes = {r.code for r in template}
        try:
            return parse_excel(raw_bytes, known_codes, sheet_name=sheet_name)
        except Exception as e:
            raise HTTPException(
                http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                tr("Не удалось разобрать файл: {error}", current_locale(), error=str(e)),
            )

    async def import_excel_commit(
        self, company_id: UUID, *,
        preview: dict, selected_years: Optional[list[int]],
        skip_unmatched: bool, user_id: UUID,
    ) -> dict:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            triples = build_commit_payload(
                preview, selected_years=selected_years, skip_unmatched=skip_unmatched,
            )
            if not triples:
                return {"inserted": 0, "updated": 0, "skipped_locked_years": []}

            inserted = updated = 0
            skipped_locked: list[int] = []
            years = {y for (y, _, _) in triples}
            locked_years: set = set()
            for y in years:
                if _is_locked(await r.get_year_lock(company_id, y)):
                    locked_years.add(y)
                    skipped_locked.append(y)
                else:
                    existing_lock = await r.get_year_lock(company_id, y)
                    if not existing_lock:
                        r.add(FinModelYearLock(
                            company_id=company_id, year=y, status="draft",
                        ))

            for (year, code, value_str) in triples:
                if year in locked_years:
                    continue
                try:
                    new_v = Decimal(value_str)
                except Exception:
                    continue
                existing = await r.get_cell(company_id, year, code)
                if existing:
                    prev = existing.value
                    existing.value = new_v
                    existing.updated_by = user_id
                    existing.is_calculated = False
                    self._add_audit(
                        company_id=company_id, year=year, row_code=code,
                        value_before=prev, value_after=new_v,
                        actor_id=user_id, source="excel_import",
                    )
                    updated += 1
                else:
                    r.add(FinModelCellValue(
                        company_id=company_id, year=year, row_code=code,
                        value=new_v, is_calculated=False, updated_by=user_id,
                    ))
                    self._add_audit(
                        company_id=company_id, year=year, row_code=code,
                        value_before=None, value_after=new_v,
                        actor_id=user_id, source="excel_import",
                    )
                    inserted += 1
            await r.flush()
            return {
                "inserted": inserted, "updated": updated,
                "skipped_locked_years": sorted(set(skipped_locked)),
            }

    # ─── forecast ─────────────────────────────────────────────────

    async def regenerate_forecast(
        self, company_id: UUID, body: ForecastRequest, *, user_id: UUID,
    ) -> dict:
        async with self.uow:
            r = self.uow.finmodel
            await self._ensure_company(company_id)
            base_cells = await r.load_year_cells(company_id, body.base_year)
            base_by_code = {
                c.row_code: c.value for c in base_cells if c.value is not None
            }
            if not base_by_code:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    tr(
                        "Базовый год {year} пуст",
                        current_locale(), year=body.base_year,
                    ),
                )

            counts: dict = {"updated": 0, "skipped_locked_years": []}
            for ty in body.target_years:
                if _is_locked(await r.get_year_lock(company_id, ty)):
                    counts["skipped_locked_years"].append(ty)
                    continue
                macro = await self._resolve_macro(company_id, ty)
                if body.method == "uz_inflation":
                    growth = (macro.uz_inflation or Decimal("0")) + Decimal("1")
                elif body.method == "manual":
                    co_macro = await r.get_macro_company(company_id, ty)
                    growth = (
                        co_macro.manual_growth_pct
                        if co_macro and co_macro.manual_growth_pct
                        else Decimal("0")
                    ) + Decimal("1")
                else:  # cagr_5y — fallback no-op
                    growth = Decimal("1")

                existing = await r.get_cells_by_codes(
                    company_id, ty, PL_INPUT_CODES_FOR_FORECAST,
                )
                existing_by_code = {x.row_code: x for x in existing}
                for code in PL_INPUT_CODES_FOR_FORECAST:
                    base = base_by_code.get(code)
                    if base is None:
                        continue
                    new_v = (Decimal(base) * growth).quantize(Decimal("0.01"))
                    cell = existing_by_code.get(code)
                    prev = cell.value if cell else None
                    if cell:
                        cell.value = new_v
                        cell.updated_by = user_id
                        cell.is_calculated = True
                    else:
                        r.add(FinModelCellValue(
                            company_id=company_id, year=ty, row_code=code,
                            value=new_v, is_calculated=True, updated_by=user_id,
                        ))
                    self._add_audit(
                        company_id=company_id, year=ty, row_code=code,
                        value_before=prev, value_after=new_v,
                        actor_id=user_id, source="forecast",
                    )
                    counts["updated"] += 1
            await r.flush()
        return counts
