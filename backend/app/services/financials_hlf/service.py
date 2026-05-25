"""High-Level Financials use-cases (Pack 7.66/7.67).

Imports the structured 4-section XLSX (SOFP / PNL / Cash flow), parses
into normalized JSON, and persists per-company in `company.extra.hlf`.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, UploadFile, status as http_status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import has_effective_permission
from app.models.user import User
from app.repositories.financials_repository import FinancialsRepository


_SKIP_SHEET_NAMES = {
    "status of ifrs reports", "company metrics", "mapping lib",
    "company names", "x-rates", "sheet1",
}


# ─── Payload schemas ──────────────────────────────────────────────

class HlfRowPayload(BaseModel):
    type: str
    label: str
    values: list[Optional[float]]
    mapping: Optional[str] = None


class HlfSectionPayload(BaseModel):
    id: str
    title: str
    years: list[int]
    rows: list[HlfRowPayload]


class HlfSavePayload(BaseModel):
    years: list[int]
    sections: list[HlfSectionPayload]
    currency: str = "UZS"
    unit: str = "bln"


# ─── Parser helpers ───────────────────────────────────────────────

def _classify_hlf_row(label: str, has_values: bool) -> str:
    """Classify row as header/subheader/line/subtotal/total."""
    lbl = (label or "").strip()
    lbl_upper = lbl.upper()
    if not has_values:
        if lbl_upper in (
            "ASSETS", "EQUITY", "LIABILITIES", "ADJUSTMENTS:",
            "INVESTING ACTIVITIES:", "FINANCING ACTIVITIES:",
        ) or lbl_upper.endswith(":"):
            return (
                "section_header"
                if lbl_upper in ("ASSETS", "EQUITY", "LIABILITIES")
                else "subheader"
            )
        return "subheader"
    if lbl_upper.startswith("TOTAL "):
        return "total" if lbl_upper in (
            "TOTAL ASSETS", "TOTAL LIABILITIES", "TOTAL EQUITY",
            "TOTAL LIABILITIES AND EQUITY",
            "TOTAL COMPREHENSIVE INCOME FOR THE YEAR",
        ) else "subtotal"
    if lbl.startswith("Total "):
        return "subtotal"
    if lbl_upper in (
        "GROSS PROFIT", "OPERATING PROFIT", "PROFIT BEFORE INCOME TAX",
        "OPERATING CASH FLOW", "INVESTING CASH FLOW", "FINANCING CASH FLOW",
        "NET CHANGE IN CASH AND CASH EQUIVALENTS",
        "OPERATING PROFIT BEFORE WORKING CAPITAL CHANGES",
        "CASH GENERATED FROM OPERATING ACTIVITIES",
    ):
        return "subtotal"
    if lbl_upper == "PROFIT FOR THE YEAR":
        return "total"
    return "line"


_SECTION_TITLES = {
    "sofp":     "Отчёт о финансовом положении (SOFP)",
    "pnl":      "Отчёт о прибылях и убытках (P&L)",
    "cashflow": "Отчёт о движении денежных средств (Cash Flow)",
    "report":   "Финансовый отчёт",
}


def _parse_hlf_sheet(ws) -> dict:
    """Parse one company sheet from the HLF Excel file.

    Returns: {years, sections: [{id, title, years, rows: [{type, label, values}]}]}
    """
    max_row = ws.max_row
    all_rows: list[tuple[int, tuple]] = []
    for r in range(1, max_row + 1):
        row_cells = list(ws.iter_rows(min_row=r, max_row=r, values_only=True))
        if row_cells:
            all_rows.append((r, row_cells[0]))

    # Detect section markers
    section_markers: list[tuple[int, str]] = []
    for r_idx, row in all_rows:
        for cell in row:
            if isinstance(cell, str):
                cs = cell.strip().lower()
                if cs == "sofp":
                    section_markers.append((r_idx, "sofp"))
                    break
                if cs == "pnl":
                    section_markers.append((r_idx, "pnl"))
                    break
                if "cash flow" in cs and len(cs) < 18:
                    section_markers.append((r_idx, "cashflow"))
                    break
    if not section_markers:
        section_markers = [(0, "report")]

    sections: list[dict] = []
    all_years_found: set[int] = set()

    for i, (sec_start, sec_id) in enumerate(section_markers):
        sec_end = (
            section_markers[i + 1][0]
            if i + 1 < len(section_markers) else max_row + 1
        )
        year_row_idx = None
        year_cols: dict[int, int] = {}
        for r_idx, row in all_rows:
            if r_idx <= sec_start or r_idx >= sec_end:
                continue
            ycols: dict[int, int] = {}
            seen_years_in_row: set[int] = set()
            in_block = False
            for ci, val in enumerate(row):
                yr = None
                if isinstance(val, (int, float)) and 2000 < int(val) < 2035:
                    yr = int(val)
                elif isinstance(val, str):
                    s = val.strip()
                    if s.isdigit() and 2000 < int(s) < 2035:
                        yr = int(s)
                if yr is None:
                    if in_block:
                        break
                    continue
                if yr in seen_years_in_row:
                    break
                seen_years_in_row.add(yr)
                ycols[ci] = yr
                in_block = True
            if len(ycols) >= 3:
                year_row_idx = r_idx
                year_cols = ycols
                break
        if year_row_idx is None or not year_cols:
            continue
        years_sorted = sorted(year_cols.values())
        all_years_found.update(years_sorted)
        col_year_pairs = sorted(year_cols.items(), key=lambda kv: kv[1])

        rows_out: list[dict] = []
        for r_idx, row in all_rows:
            if r_idx <= year_row_idx or r_idx >= sec_end:
                continue
            label = None
            col_a = row[0] if len(row) > 0 else None
            col_b = row[1] if len(row) > 1 else None
            for candidate in (col_b, col_a):
                if isinstance(candidate, str) and candidate.strip():
                    s = candidate.strip()
                    if s.lower() in ("bln uzs", "mln uzs", "31 dec"):
                        continue
                    if s.isdigit():
                        continue
                    label = s
                    break
            if not label:
                for ci in range(2, min(5, len(row))):
                    v = row[ci]
                    if isinstance(v, str) and v.strip():
                        s = v.strip()
                        if s.lower() in (
                            "bln uzs", "mln uzs", "31 dec",
                            "sofp", "pnl", "cash flow",
                        ):
                            continue
                        if s.isdigit():
                            continue
                        label = s
                        break
            if not label:
                continue
            values: list[Optional[float]] = []
            has_any = False
            for col, _yr in col_year_pairs:
                if col < len(row):
                    cv = row[col]
                    if isinstance(cv, (int, float)) and cv != 0:
                        values.append(float(cv))
                        has_any = True
                    elif cv == 0:
                        values.append(0.0)
                    else:
                        values.append(None)
                else:
                    values.append(None)
            rows_out.append({
                "type": _classify_hlf_row(label, has_any),
                "label": label,
                "values": values,
            })
        if not rows_out:
            continue
        sections.append({
            "id": sec_id,
            "title": _SECTION_TITLES.get(sec_id, sec_id),
            "years": years_sorted,
            "rows": rows_out,
        })

    return {
        "years": sorted(all_years_found),
        "sections": sections,
    }


# ─── Service ──────────────────────────────────────────────────────

@dataclass
class FinancialsHlfService:
    async def import_file(
        self,
        file: UploadFile,
        db: AsyncSession,
        user: User,
    ) -> dict:
        if not await has_effective_permission(db, user, "financials.edit"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "Permission required",
            )
        contents = await file.read()
        if not contents:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, "Empty file",
            )
        from openpyxl import load_workbook
        try:
            wb = load_workbook(
                io.BytesIO(contents), data_only=True, read_only=True,
            )
        except Exception as e:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Cannot parse XLSX: {e}",
            )

        repo = FinancialsRepository(db)
        cos = await repo.list_all_companies()
        co_by_code = {c.code.lower(): c for c in cos}

        now_iso = datetime.utcnow().isoformat()
        summary_log: list[str] = []
        imported_count = 0
        skipped_sheets: list[str] = []

        for sheet_name in wb.sheetnames:
            sn_lower = sheet_name.lower().strip()
            if sn_lower in _SKIP_SHEET_NAMES or sn_lower.startswith("_"):
                continue
            co = co_by_code.get(sn_lower)
            if not co:
                skipped_sheets.append(f"{sheet_name} (no company)")
                continue
            ws = wb[sheet_name]
            try:
                parsed = _parse_hlf_sheet(ws)
            except Exception as e:
                summary_log.append(f"⚠ {sheet_name}: parse error — {e}")
                continue
            if not parsed["sections"]:
                summary_log.append(f"⚠ {sheet_name}: no sections detected")
                continue
            extra = dict(co.extra or {})
            extra["hlf"] = {
                "version": "v4_2024",
                "imported_at": now_iso,
                "imported_by": user.email,
                "filename": file.filename,
                "currency": "UZS",
                "unit": "bln",
                "years": parsed["years"],
                "sections": parsed["sections"],
            }
            co.extra = extra
            imported_count += 1
            sec_counts = [
                f"{s['id']}={len(s['rows'])}" for s in parsed["sections"]
            ]
            summary_log.append(
                f"✓ {sheet_name} → {co.code}: "
                f"years {parsed['years']} · {' '.join(sec_counts)}"
            )

        await db.commit()
        return {
            "imported_count": imported_count,
            "skipped_sheets": skipped_sheets,
            "log": summary_log,
            "filename": file.filename,
        }

    async def get_company_hlf(
        self, code: str, db: AsyncSession, user: User,
    ) -> dict:
        if not await has_effective_permission(db, user, "financials.view"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "Permission required",
            )
        repo = FinancialsRepository(db)
        co = await repo.find_company_by_code(code)
        if not co:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                f"Company '{code}' not found",
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and co.id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access",
            )
        hlf = (co.extra or {}).get("hlf") if co.extra else None
        return {
            "code": co.code,
            "company_name": co.name_short or co.name_ru,
            "hlf": hlf,
        }

    async def save_company_hlf(
        self,
        code: str,
        payload: HlfSavePayload,
        db: AsyncSession,
        user: User,
    ) -> dict:
        if not await has_effective_permission(db, user, "financials.edit"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "Permission required",
            )
        repo = FinancialsRepository(db)
        co = await repo.find_company_by_code(code)
        if not co:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND,
                f"Company '{code}' not found",
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and co.id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access",
            )
        now_iso = datetime.utcnow().isoformat()
        extra = dict(co.extra or {})
        existing = extra.get("hlf", {}) or {}
        extra["hlf"] = {
            **existing,
            "currency": payload.currency,
            "unit": payload.unit,
            "years": payload.years,
            "sections": [s.model_dump() for s in payload.sections],
            "updated_at": now_iso,
            "updated_by": user.email,
        }
        co.extra = extra
        await db.commit()
        total_rows = sum(len(s.rows) for s in payload.sections)
        return {
            "code": co.code,
            "saved": True,
            "years": payload.years,
            "sections_count": len(payload.sections),
            "rows_count": total_rows,
            "updated_at": now_iso,
        }
