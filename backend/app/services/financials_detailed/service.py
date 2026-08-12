"""Detailed Excel financials use-cases.

8 endpoints encapsulated:
  POST   /detailed/import-excel               one-shot Excel import (multi-sheet/section)
  GET    /detailed/{company_code}             wide grid: rows × years
  PUT    /detailed/{company_code}/cell        inline cell edit
  GET    /detailed/canonical/catalog          canonical line schema for editor
  POST   /detailed/parse-preview              parse Excel WITHOUT writing (preview modal)
  POST   /detailed/import-confirm             commit (potentially edited) preview structure
  PUT    /detailed/{company_code}/line/mapping   change canonical mapping (+ optional label)
  DELETE /detailed/{company_code}/line        delete line across all years

Excel parsing delegates to `app.services.excel_financial_parser.parse_workbook`
(core helper, untouched). Canonical lookup uses `CANONICAL` from
`app.services.financial_canonical` (also untouched).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile
from fastapi import status as http_status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.audit_chain import append_audit_entry
from app.core.security import has_effective_permission
from app.models.financial import FinancialLine, FinancialReport
from app.models.user import User
from app.repositories.financials_repository import FinancialsRepository
from app.services.excel_financial_parser import parse_workbook
from app.services.financial_canonical import CANONICAL


def _serialize_parsed_section(sec) -> dict:
    """Convert a ParsedSection (incl. canonical mapping) to JSON-safe dict."""
    return {
        "report_type": sec.report_type,
        "years": sec.years,
        "warnings": sec.warnings,
        "rows": [
            {
                "code": r.code,
                "label": r.label,
                "indent_level": r.indent_level,
                "section_label": r.section_label,
                "is_subtotal": r.is_subtotal,
                "values": {str(y): v for y, v in r.values.items()},
                "canonical_code": r.canonical_code,
                "is_unmapped": r.is_unmapped,
            }
            for r in sec.rows
        ],
    }


@dataclass
class FinancialsDetailedService:
    async def canonical_catalog(self, _user: User) -> dict:
        out: dict[str, list[dict]] = {}
        for rtyp, lines in CANONICAL.items():
            out[rtyp] = [
                {
                    "code": cl.code,
                    "label": cl.label,
                    "label_ru": cl.label_ru,
                    "section": cl.section,
                    "is_subtotal": cl.is_subtotal,
                    "indent": cl.indent,
                }
                for cl in lines
            ]
        return out

    async def import_excel(
        self,
        db: AsyncSession,
        user: User,
        *,
        file: UploadFile,
        standard: str,
        is_audited: bool,
        company_code: Optional[str],
        report_type: Optional[str],
        sheet_name: Optional[str],
    ) -> dict:
        if not await has_effective_permission(db, user, "financials.edit"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.edit",
            )
        if standard not in ("IFRS", "NSBU"):
            raise HTTPException(422, "standard must be IFRS or NSBU")
        if report_type is not None and report_type not in ("PL", "BS", "CF"):
            raise HTTPException(422, "report_type must be PL, BS, or CF")

        try:
            file_bytes = await file.read()
        except Exception as e:
            raise HTTPException(400, f"Failed to read uploaded file: {e}")
        if len(file_bytes) > 25 * 1024 * 1024:
            raise HTTPException(413, "File too large (max 25 MB)")

        repo = FinancialsRepository(db)
        all_companies = {
            c.code.lower(): c for c in await repo.list_all_companies()
        }
        if not all_companies:
            raise HTTPException(500, "No companies in database")

        scope_ids = await allowed_company_ids(db, user)

        # Parse Excel
        if company_code:
            co = all_companies.get(company_code.lower())
            if not co:
                raise HTTPException(
                    404, f"Company '{company_code}' not found"
                )
            if scope_ids is not None and co.id not in scope_ids:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "No access to this company",
                )
            try:
                parsed_sheets = parse_workbook(
                    file_bytes, sheet_name,
                    company_codes={co.code.lower()},
                )
            except Exception as e:
                raise HTTPException(
                    400, f"Failed to parse Excel: {type(e).__name__}: {e}"
                )
            if not parsed_sheets:
                # Fallback: try without company filter (single-sheet workbook
                # with arbitrary name)
                try:
                    parsed_sheets = parse_workbook(file_bytes, sheet_name)
                except Exception as e:
                    raise HTTPException(
                        400,
                        f"Failed to parse Excel: {type(e).__name__}: {e}",
                    )
                if not parsed_sheets:
                    raise HTTPException(
                        400, "No valid financial sheets found"
                    )
                # Force the company match
                for ps in parsed_sheets:
                    for sec in ps.sections:
                        sec.company_hint = co.code.lower()
        else:
            try:
                parsed_sheets = parse_workbook(
                    file_bytes, sheet_name,
                    company_codes=set(all_companies.keys()),
                )
            except Exception as e:
                raise HTTPException(
                    400, f"Failed to parse Excel: {type(e).__name__}: {e}"
                )
            if not parsed_sheets:
                raise HTTPException(
                    400,
                    "No sheets matched company codes. Sheet names must "
                    "match a company code (case-insensitive). "
                    f"Known codes: {sorted(all_companies.keys())[:5]}…",
                )

        # Apply scope filter
        if scope_ids is not None:
            parsed_sheets = [
                ps for ps in parsed_sheets
                if (all_companies.get(ps.sheet_name.lower())
                    and all_companies[ps.sheet_name.lower()].id in scope_ids)
            ]
            if not parsed_sheets:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "No access to any company in this Excel",
                )

        # Apply report_type override
        if company_code and report_type:
            all_sections = [
                sec for ps in parsed_sheets for sec in ps.sections
            ]
            if len(all_sections) == 1:
                all_sections[0].report_type = report_type

        sheet_results: list[dict] = []
        total_reports = 0
        total_lines = 0
        skipped_sheets: list[str] = []

        # Wipe existing detailed reports per (company, standard, report_type)
        wipe_keys: set[tuple] = set()
        for ps in parsed_sheets:
            co = all_companies.get(ps.sheet_name.lower())
            if not co:
                skipped_sheets.append(f"{ps.sheet_name} (no matching company)")
                continue
            for sec in ps.sections:
                wipe_keys.add((co.id, standard, sec.report_type))

        if wipe_keys:
            for (cid, std, rtyp) in wipe_keys:
                existing_q = await db.execute(
                    select(FinancialReport).where(
                        FinancialReport.company_id == cid,
                        FinancialReport.standard == std,
                        FinancialReport.report_type == rtyp,
                        FinancialReport.is_detailed == True,  # noqa: E712
                    )
                )
                for old in existing_q.scalars().all():
                    await db.delete(old)
            await db.flush()

        # Insert new reports
        for ps in parsed_sheets:
            co = all_companies.get(ps.sheet_name.lower())
            if not co:
                continue
            sheet_summary = {
                "sheet_name": ps.sheet_name,
                "company_code": co.code,
                "company_name": co.name_short,
                "sections": [],
                "warnings": list(ps.warnings),
            }
            for sec in ps.sections:
                for year in sec.years:
                    rep = FinancialReport(
                        company_id=co.id,
                        year=year, quarter=None,
                        standard=standard, report_type=sec.report_type,
                        currency="UZS", unit_scale=1_000_000_000,
                        source=f"excel:{file.filename or 'upload'}#{ps.sheet_name}",
                        is_audited=is_audited,
                        is_detailed=True,
                        extra={
                            "imported_at": datetime.now(UTC).isoformat(),
                            "imported_by": user.email,
                            "source_sheet": ps.sheet_name,
                            "source_filename": file.filename,
                            "warnings": sec.warnings,
                        },
                    )
                    db.add(rep)
                    await db.flush()
                    total_reports += 1
                    for sort_idx, prow in enumerate(sec.rows):
                        v = prow.values.get(year)
                        if v is None:
                            continue
                        db.add(FinancialLine(
                            report_id=rep.id,
                            line_code=prow.code,
                            line_name=prow.label,
                            parent_code=prow.parent_code,
                            section_label=prow.section_label,
                            indent_level=prow.indent_level,
                            value=Decimal(str(v)),
                            is_subtotal=prow.is_subtotal,
                            is_calculated=False,
                            sort_order=sort_idx,
                        ))
                        total_lines += 1
                sheet_summary["sections"].append({
                    "report_type": sec.report_type,
                    "years": sec.years,
                    "rows": len(sec.rows),
                    "warnings": sec.warnings,
                })
            sheet_results.append(sheet_summary)

        await db.commit()

        co_codes = sorted({r["company_code"] for r in sheet_results})
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="financials.detailed.import",
            entity_type="batch", entity_id=str(file.filename or "upload")[:80],
            notes=(
                f"{standard}: {len(co_codes)} companies, "
                f"{total_reports} reports, {total_lines} lines "
                f"from {file.filename}"
            ),
        )
        await db.commit()

        return {
            "standard": standard,
            "companies_imported": len(co_codes),
            "company_codes": co_codes,
            "reports_created": total_reports,
            "lines_created": total_lines,
            "skipped_sheets": skipped_sheets,
            "results": sheet_results,
        }

    async def get_detailed(
        self,
        company_code: str,
        db: AsyncSession,
        user: User,
        *,
        standard: str,
        report_type: str,
    ) -> dict:
        repo = FinancialsRepository(db)
        co = await repo.find_company_by_code(company_code)
        if not co:
            raise HTTPException(404, f"Company '{company_code}' not found")
        if not await has_effective_permission(
            db, user, "financials.view", company_id=co.id,
        ):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.view",
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and co.id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access to this company"
            )

        rep_q = await db.execute(
            select(FinancialReport).where(
                FinancialReport.company_id == co.id,
                FinancialReport.standard == standard,
                FinancialReport.report_type == report_type,
                FinancialReport.is_detailed == True,  # noqa: E712
            ).order_by(FinancialReport.year.asc())
        )
        reports = list(rep_q.scalars().all())
        if not reports:
            return {
                "company_code": co.code, "company_name": co.name_short,
                "standard": standard, "report_type": report_type,
                "years": [], "rows": [], "has_data": False,
            }

        years = [r.year for r in reports]
        line_meta: dict[str, dict] = {}
        cells: dict[tuple[str, int], Optional[float]] = {}

        for rep in reports:
            ln_q = await db.execute(
                select(FinancialLine)
                .where(FinancialLine.report_id == rep.id)
                .order_by(FinancialLine.sort_order.asc())
            )
            for ln in ln_q.scalars().all():
                cells[(ln.line_code, rep.year)] = (
                    float(ln.value) if ln.value is not None else None
                )
                if ln.line_code not in line_meta:
                    line_meta[ln.line_code] = {
                        "code": ln.line_code,
                        "label": ln.line_name,
                        "section": ln.section_label,
                        "indent": ln.indent_level,
                        "is_subtotal": ln.is_subtotal,
                        "sort_order": ln.sort_order,
                        "canonical_code": ln.parent_code,
                        "is_unmapped": ln.parent_code is None,
                    }
                elif ln.sort_order < line_meta[ln.line_code]["sort_order"]:
                    line_meta[ln.line_code]["sort_order"] = ln.sort_order

        rows = sorted(line_meta.values(), key=lambda r: r["sort_order"])
        for row in rows:
            row["values"] = {
                y: cells.get((row["code"], y)) for y in years
            }

        return {
            "company_code": co.code, "company_name": co.name_short,
            "standard": standard, "report_type": report_type,
            "years": years, "rows": rows, "has_data": True,
            "imported_at": (
                (reports[0].extra or {}).get("imported_at")
                if reports else None
            ),
            "source_filename": (
                (reports[0].extra or {}).get("source_filename")
                if reports else None
            ),
        }

    async def update_cell(
        self,
        company_code: str,
        db: AsyncSession,
        user: User,
        *,
        standard: str,
        report_type: str,
        year: int,
        line_code: str,
        value: Optional[float],
    ) -> tuple[Optional[dict], Optional[dict]]:
        repo = FinancialsRepository(db)
        co = await repo.find_company_by_code(company_code)
        if not co:
            raise HTTPException(404, f"Company '{company_code}' not found")
        if not await has_effective_permission(
            db, user, "financials.edit", company_id=co.id,
        ):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.edit",
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and co.id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access to this company"
            )

        # Moderation gate (deny-by-default; OFF unless admin enables 'financials').
        # Mirrors financials_reports.save_report: gate AFTER perm + scope checks
        # and BEFORE any DB mutation. Returns a 2-tuple; route turns queued→202.
        from app.services.moderation_service import gate_or_apply
        queued, sub = await gate_or_apply(
            db, user=user,
            module="financials", action="detailed_cell",
            entity_id=f"{co.code}:{standard}:{report_type}:{year}:{line_code}",
            entity_label=f"Детальная отчётность — {co.name_short}",
            company_id=co.id, sector_id=None, year=year,
            payload={
                "company_code": co.code, "standard": standard,
                "report_type": report_type, "year": year,
                "line_code": line_code, "value": value,
            },
            editor_token=None,
            diff_summary=f"Ячейка {standard} {report_type} {year} · {line_code}",
        )
        if queued:
            return None, {
                "queued": True, "submission_id": str(sub.id),
                "status": sub.status,
                "message": "Изменение отправлено на модерацию",
            }

        res = await _apply_detailed_cell_core(
            db, co=co, standard=standard, report_type=report_type,
            year=year, line_code=line_code, value=value, user=user,
        )
        return res, None

    async def parse_preview(
        self,
        db: AsyncSession,
        user: User,
        *,
        file: UploadFile,
        standard: str,
        company_code: Optional[str],
        sheet_name: Optional[str],
    ) -> dict:
        if not await has_effective_permission(db, user, "financials.edit"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.edit",
            )
        if standard not in ("IFRS", "NSBU"):
            raise HTTPException(422, "standard must be IFRS or NSBU")

        try:
            file_bytes = await file.read()
        except Exception as e:
            raise HTTPException(400, f"Failed to read file: {e}")
        if len(file_bytes) > 25 * 1024 * 1024:
            raise HTTPException(413, "File too large (max 25 MB)")

        repo = FinancialsRepository(db)
        all_companies = {
            c.code.lower(): {
                "id": str(c.id), "code": c.code, "name": c.name_short,
            }
            for c in await repo.list_all_companies()
        }
        if not all_companies:
            raise HTTPException(500, "No companies in database")

        scope_ids = await allowed_company_ids(db, user)

        if company_code:
            if company_code.lower() not in all_companies:
                raise HTTPException(404, f"Company '{company_code}' not found")
            filter_codes = {company_code.lower()}
        else:
            filter_codes = set(all_companies.keys())

        try:
            parsed_sheets = parse_workbook(
                file_bytes, sheet_name, company_codes=filter_codes,
            )
        except Exception as e:
            raise HTTPException(
                400, f"Failed to parse Excel: {type(e).__name__}: {e}"
            )
        if not parsed_sheets:
            raise HTTPException(
                400,
                "No sheets matched company codes. "
                f"Sheet names must match one of the {len(all_companies)} "
                "company codes.",
            )

        if scope_ids is not None:
            scope_codes_lc = {
                code for code, info in all_companies.items()
                if UUID(info["id"]) in scope_ids
            }
            parsed_sheets = [
                ps for ps in parsed_sheets
                if ps.sheet_name.lower() in scope_codes_lc
            ]

        sheets_out: list[dict] = []
        for ps in parsed_sheets:
            co_info = all_companies.get(ps.sheet_name.lower())
            if not co_info:
                continue
            sections_out: list[dict] = []
            for sec in ps.sections:
                sec_dict = _serialize_parsed_section(sec)
                canonical_set = {
                    cl.code for cl in CANONICAL.get(sec.report_type, [])
                }
                present_canonical = {
                    r.canonical_code for r in sec.rows if r.canonical_code
                }
                sec_dict["missing_canonical_codes"] = sorted(
                    canonical_set - present_canonical
                )
                sec_dict["unmapped_count"] = sum(
                    1 for r in sec.rows if r.is_unmapped
                )
                sections_out.append(sec_dict)
            sheets_out.append({
                "sheet_name": ps.sheet_name,
                "company_code": co_info["code"],
                "company_name": co_info["name"],
                "warnings": ps.warnings,
                "sections": sections_out,
            })

        return {
            "standard": standard,
            "filename": file.filename,
            "sheets": sheets_out,
            "summary": {
                "sheets": len(sheets_out),
                "sections": sum(len(s["sections"]) for s in sheets_out),
                "rows": sum(
                    len(sec["rows"])
                    for s in sheets_out for sec in s["sections"]
                ),
                "unmapped_rows": sum(
                    sec["unmapped_count"]
                    for s in sheets_out for sec in s["sections"]
                ),
            },
        }

    async def import_confirm(
        self,
        payload: dict,
        db: AsyncSession,
        user: User,
    ) -> tuple[Optional[dict], Optional[dict]]:
        if not await has_effective_permission(db, user, "financials.edit"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.edit",
            )
        standard = payload.get("standard", "IFRS")
        if standard not in ("IFRS", "NSBU"):
            raise HTTPException(422, "standard must be IFRS or NSBU")
        sheets_in = payload.get("sheets") or []
        if not sheets_in:
            raise HTTPException(422, "No sheets in payload")

        # Per-company scope pre-check (BEFORE the moderation gate; convention
        # requires perm + scope checks before any queue/mutation). Also decides
        # the single company_id / entity_id carried onto the submission.
        repo = FinancialsRepository(db)
        all_co = {c.code.lower(): c for c in await repo.list_all_companies()}
        scope_ids = await allowed_company_ids(db, user)
        target_ids: set = set()
        target_codes: list[str] = []
        for sh in sheets_in:
            co = all_co.get((sh.get("company_code") or "").lower())
            if not co:
                continue
            if scope_ids is not None and co.id not in scope_ids:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    f"No access to company '{co.code}'",
                )
            target_ids.add(co.id)
            if co.code not in target_codes:
                target_codes.append(co.code)

        gate_company_id = next(iter(target_ids)) if len(target_ids) == 1 else None
        entity_id = (
            target_codes[0] if len(target_codes) == 1
            else f"multi:{payload.get('filename', 'preview')}"
        )

        # Moderation gate (deny-by-default; OFF unless admin enables 'financials').
        # Bulk create/replace of is_detailed lines → 'detailed_import_confirm'.
        from app.services.moderation_service import gate_or_apply
        queued, sub = await gate_or_apply(
            db, user=user,
            module="financials", action="detailed_import_confirm",
            entity_id=entity_id,
            entity_label=f"Импорт детальной отчётности ({standard})",
            company_id=gate_company_id, sector_id=None, year=None,
            payload=payload,
            editor_token=None,
            diff_summary=(
                f"Импорт детальной отчётности ({standard}) · "
                f"{len(target_codes)} комп."
            ),
        )
        if queued:
            return None, {
                "queued": True, "submission_id": str(sub.id),
                "status": sub.status,
                "message": "Изменение отправлено на модерацию",
            }

        res = await _apply_detailed_import_confirm_core(db, payload=payload, user=user)
        return res, None

    async def update_line_mapping(
        self,
        company_code: str,
        db: AsyncSession,
        user: User,
        *,
        standard: str,
        report_type: str,
        line_code: str,
        canonical_code: Optional[str],
        new_label: Optional[str],
    ) -> tuple[Optional[dict], Optional[dict]]:
        repo = FinancialsRepository(db)
        co = await repo.find_company_by_code(company_code)
        if not co:
            raise HTTPException(404, f"Company '{company_code}' not found")
        if not await has_effective_permission(
            db, user, "financials.edit", company_id=co.id,
        ):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.edit",
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and co.id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access to this company"
            )
        # Moderation gate (deny-by-default; OFF unless admin enables 'financials').
        from app.services.moderation_service import gate_or_apply
        queued, sub = await gate_or_apply(
            db, user=user,
            module="financials", action="detailed_mapping",
            entity_id=f"{co.code}:{standard}:{report_type}:{line_code}",
            entity_label=f"Детальная отчётность — {co.name_short}",
            company_id=co.id, sector_id=None, year=None,
            payload={
                "company_code": co.code, "standard": standard,
                "report_type": report_type, "line_code": line_code,
                "canonical_code": canonical_code, "new_label": new_label,
            },
            editor_token=None,
            diff_summary=f"Переназначение строки {line_code}",
        )
        if queued:
            return None, {
                "queued": True, "submission_id": str(sub.id),
                "status": sub.status,
                "message": "Изменение отправлено на модерацию",
            }

        res = await _apply_detailed_mapping_core(
            db, co=co, standard=standard, report_type=report_type,
            line_code=line_code, canonical_code=canonical_code,
            new_label=new_label, user=user,
        )
        return res, None

    async def delete_line(
        self,
        company_code: str,
        db: AsyncSession,
        user: User,
        *,
        standard: str,
        report_type: str,
        line_code: str,
    ) -> tuple[Optional[dict], Optional[dict]]:
        repo = FinancialsRepository(db)
        co = await repo.find_company_by_code(company_code)
        if not co:
            raise HTTPException(404, f"Company '{company_code}' not found")
        if not await has_effective_permission(
            db, user, "financials.edit", company_id=co.id,
        ):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.edit",
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and co.id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access to this company"
            )
        # Moderation gate (deny-by-default; OFF unless admin enables 'financials').
        from app.services.moderation_service import gate_or_apply
        queued, sub = await gate_or_apply(
            db, user=user,
            module="financials", action="detailed_delete_line",
            entity_id=f"{co.code}:{standard}:{report_type}:{line_code}",
            entity_label=f"Детальная отчётность — {co.name_short}",
            company_id=co.id, sector_id=None, year=None,
            payload={
                "company_code": co.code, "standard": standard,
                "report_type": report_type, "line_code": line_code,
            },
            editor_token=None,
            diff_summary=f"Удаление строки {line_code}",
        )
        if queued:
            return None, {
                "queued": True, "submission_id": str(sub.id),
                "status": sub.status,
                "message": "Изменение отправлено на модерацию",
            }

        res = await _apply_detailed_delete_core(
            db, co=co, standard=standard, report_type=report_type,
            line_code=line_code, user=user,
        )
        return res, None


# ════════════════════════════════════════════════════════════════════
#   WRITE CORES + apply_submission (deny-by-default moderation)
# ════════════════════════════════════════════════════════════════════
# Each detailed write op is factored into a module-level async core so the
# LIVE path (service method, after perm+scope+gate) and the APPLY path
# (moderation approve → moderation_apply/financials.py → apply_submission)
# call the SAME code — no drift. Cores perform the DB mutation and commit,
# mirroring the pre-moderation behavior exactly. editor-token re-validation
# is not applicable here (this editor never issued one); the queue itself is
# the merge point. Writes are attributed to whoever `user` is passed —
# the live editor on the direct path, the PROPOSER on the apply path.


async def _apply_detailed_cell_core(
    db: AsyncSession, *, co, standard: str, report_type: str, year: int,
    line_code: str, value: Optional[float], user: User,
) -> dict:
    """Single-cell UPSERT on an is_detailed FinancialReport (update_cell core)."""
    rep = (await db.execute(
        select(FinancialReport).where(
            FinancialReport.company_id == co.id,
            FinancialReport.year == year,
            FinancialReport.standard == standard,
            FinancialReport.report_type == report_type,
            FinancialReport.is_detailed == True,  # noqa: E712
        )
    )).scalar_one_or_none()
    if not rep:
        raise HTTPException(
            404,
            f"No detailed report for {co.code}/{year}/{standard}/{report_type}",
        )
    line = (await db.execute(
        select(FinancialLine).where(
            FinancialLine.report_id == rep.id,
            FinancialLine.line_code == line_code,
        )
    )).scalar_one_or_none()
    if not line:
        raise HTTPException(
            404, f"Line '{line_code}' not found in this report"
        )
    line.value = Decimal(str(value)) if value is not None else None
    await db.commit()
    return {
        "updated": True,
        "line_code": line_code,
        "year": year,
        "value": value,
    }


async def _apply_detailed_mapping_core(
    db: AsyncSession, *, co, standard: str, report_type: str,
    line_code: str, canonical_code: Optional[str], new_label: Optional[str],
    user: User,
) -> dict:
    """Re-map parent_code / relabel a line across all years (update_line_mapping core)."""
    reports = list((await db.execute(
        select(FinancialReport).where(
            FinancialReport.company_id == co.id,
            FinancialReport.standard == standard,
            FinancialReport.report_type == report_type,
            FinancialReport.is_detailed == True,  # noqa: E712
        )
    )).scalars().all())
    if not reports:
        raise HTTPException(404, "No detailed reports found")
    updated = 0
    for rep in reports:
        ln_q = await db.execute(
            select(FinancialLine).where(
                FinancialLine.report_id == rep.id,
                FinancialLine.line_code == line_code,
            )
        )
        for ln in ln_q.scalars().all():
            ln.parent_code = canonical_code if canonical_code else None
            if new_label:
                ln.line_name = new_label[:255]
            updated += 1
    await db.commit()
    return {
        "updated": updated,
        "canonical_code": canonical_code,
        "new_label": new_label,
    }


async def _apply_detailed_delete_core(
    db: AsyncSession, *, co, standard: str, report_type: str,
    line_code: str, user: User,
) -> dict:
    """Keyed DELETE of a line across all years (delete_line core)."""
    rep_q = await db.execute(
        select(FinancialReport).where(
            FinancialReport.company_id == co.id,
            FinancialReport.standard == standard,
            FinancialReport.report_type == report_type,
            FinancialReport.is_detailed == True,  # noqa: E712
        )
    )
    deleted = 0
    for rep in rep_q.scalars().all():
        r = await db.execute(
            delete(FinancialLine).where(
                FinancialLine.report_id == rep.id,
                FinancialLine.line_code == line_code,
            )
        )
        deleted += int(r.rowcount or 0)
    await db.commit()
    return {"deleted": deleted, "line_code": line_code}


async def _apply_detailed_import_confirm_core(
    db: AsyncSession, *, payload: dict, user: User,
) -> dict:
    """Bulk create/replace of is_detailed financial_lines (import_confirm core).

    Full-blob-ish last-writer-wins per (company, standard, report_type): wipes
    matching detailed reports then re-inserts from the (possibly edited) preview
    structure. The live path applied no checksum/token guard, so neither does
    this — parity is preserved (see concern in report re: intervening-edit
    clobber). Per-company scope is re-checked here against `user` (the proposer
    on the apply path) so the core is self-sufficient on both paths.
    """
    standard = payload.get("standard", "IFRS")
    if standard not in ("IFRS", "NSBU"):
        raise HTTPException(422, "standard must be IFRS or NSBU")
    is_audited = bool(payload.get("is_audited", True))
    filename = payload.get("filename", "preview")
    sheets_in = payload.get("sheets") or []
    if not sheets_in:
        raise HTTPException(422, "No sheets in payload")

    repo = FinancialsRepository(db)
    all_co = {
        c.code.lower(): c for c in await repo.list_all_companies()
    }
    scope_ids = await allowed_company_ids(db, user)

    # Wipe matching existing detailed reports first
    wipe_keys: set[tuple] = set()
    for sh in sheets_in:
        co_code = (sh.get("company_code") or "").lower()
        co = all_co.get(co_code)
        if not co:
            continue
        if scope_ids is not None and co.id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                f"No access to company '{co.code}'",
            )
        for sec in sh.get("sections") or []:
            rtyp = sec.get("report_type")
            if rtyp not in ("BS", "PL", "CF"):
                continue
            wipe_keys.add((co.id, standard, rtyp))

    for (cid, std, rtyp) in wipe_keys:
        existing_q = await db.execute(
            select(FinancialReport).where(
                FinancialReport.company_id == cid,
                FinancialReport.standard == std,
                FinancialReport.report_type == rtyp,
                FinancialReport.is_detailed == True,  # noqa: E712
            )
        )
        for old in existing_q.scalars().all():
            await db.delete(old)
    await db.flush()

    total_reports = 0
    total_lines = 0
    co_codes_done: set[str] = set()
    skipped: list[str] = []

    for sh in sheets_in:
        co_code = (sh.get("company_code") or "").lower()
        co = all_co.get(co_code)
        if not co:
            skipped.append(f"{co_code} (unknown)")
            continue
        for sec in sh.get("sections") or []:
            rtyp = sec.get("report_type")
            if rtyp not in ("BS", "PL", "CF"):
                continue
            years = sec.get("years") or []
            rows = sec.get("rows") or []
            if not years or not rows:
                continue
            for year in years:
                rep = FinancialReport(
                    company_id=co.id,
                    year=int(year), quarter=None,
                    standard=standard, report_type=rtyp,
                    currency="UZS", unit_scale=1_000_000_000,
                    source=f"excel-confirm:{filename}",
                    is_audited=is_audited,
                    is_detailed=True,
                    extra={
                        "imported_at": datetime.now(UTC).isoformat(),
                        "imported_by": user.email,
                        "source_filename": filename,
                        "via": "preview-confirm",
                    },
                )
                db.add(rep)
                await db.flush()
                total_reports += 1
                for sort_idx, prow in enumerate(rows):
                    yk = str(year)
                    raw_v = (prow.get("values") or {}).get(yk)
                    if raw_v is None:
                        raw_v = (prow.get("values") or {}).get(year)
                    if raw_v is None or raw_v == "":
                        continue
                    try:
                        v = Decimal(str(raw_v))
                    except Exception:
                        continue
                    code = (prow.get("code") or "").strip() or f"line_{sort_idx}"
                    label = (prow.get("label") or "").strip() or code
                    canonical_code = prow.get("canonical_code") or None
                    indent = int(prow.get("indent_level") or 0)
                    section_label = prow.get("section_label") or None
                    is_subtotal = bool(prow.get("is_subtotal", False))
                    db.add(FinancialLine(
                        report_id=rep.id,
                        line_code=code[:32],
                        line_name=label[:255],
                        parent_code=(
                            canonical_code[:32]
                            if canonical_code else None
                        ),
                        section_label=section_label,
                        indent_level=indent,
                        value=v,
                        is_subtotal=is_subtotal,
                        is_calculated=False,
                        sort_order=sort_idx,
                    ))
                    total_lines += 1
        co_codes_done.add(co.code)

    await db.commit()
    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="financials.detailed.import.confirm",
        entity_type="batch", entity_id=str(filename)[:80],
        notes=(
            f"{standard}: {len(co_codes_done)} co, "
            f"{total_reports} reports, {total_lines} lines "
            "(via preview-confirm)"
        ),
    )
    await db.commit()

    return {
        "standard": standard,
        "companies_imported": len(co_codes_done),
        "company_codes": sorted(co_codes_done),
        "reports_created": total_reports,
        "lines_created": total_lines,
        "skipped": skipped,
    }


async def apply_submission(db: AsyncSession, *, sub, user: User) -> dict:
    """Apply an approved detailed-editor submission (moderation apply path).

    Dispatched from `moderation_apply/financials.py` on sub.action (the op
    discriminator the orchestrator preserves):
        detailed_cell · detailed_mapping · detailed_delete_line ·
        detailed_import_confirm

    Resolves the company by the code carried in sub.proposed_value, loads the
    PROPOSER for attribution (fallback to the approving moderator), validates
    the payload, and calls the SAME write core the live path uses.
    """
    pv = dict(sub.proposed_value or {})
    if not pv:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()

    # Attribute writes to the proposer (fallback to the approving moderator).
    proposer = user
    if getattr(sub, "proposer_user_id", None):
        p = (await db.execute(
            select(User).where(User.id == sub.proposer_user_id)
        )).scalar_one_or_none()
        if p is not None:
            proposer = p

    if action == "detailed_import_confirm":
        return await _apply_detailed_import_confirm_core(
            db, payload=pv, user=proposer,
        )

    # Single-company ops resolve the company by the code in proposed_value.
    repo = FinancialsRepository(db)
    co = await repo.find_company_by_code(pv.get("company_code") or "")
    if not co:
        raise ValueError(f"company '{pv.get('company_code')}' not found")
    standard = pv.get("standard")
    report_type = pv.get("report_type")
    line_code = pv.get("line_code")
    if standard not in ("IFRS", "NSBU"):
        raise ValueError(f"invalid standard: {standard!r}")
    if report_type not in ("PL", "BS", "CF"):
        raise ValueError(f"invalid report_type: {report_type!r}")
    if not line_code:
        raise ValueError("missing line_code in proposed_value")

    if action == "detailed_cell":
        year_raw = pv.get("year")
        try:
            year = int(year_raw)
        except (TypeError, ValueError) as e:
            raise ValueError(f"invalid year: {year_raw!r}") from e
        return await _apply_detailed_cell_core(
            db, co=co, standard=standard, report_type=report_type,
            year=year, line_code=line_code, value=pv.get("value"),
            user=proposer,
        )
    if action == "detailed_mapping":
        return await _apply_detailed_mapping_core(
            db, co=co, standard=standard, report_type=report_type,
            line_code=line_code, canonical_code=pv.get("canonical_code"),
            new_label=pv.get("new_label"), user=proposer,
        )
    if action == "detailed_delete_line":
        return await _apply_detailed_delete_core(
            db, co=co, standard=standard, report_type=report_type,
            line_code=line_code, user=proposer,
        )
    raise ValueError(f"unknown detailed action: {action!r}")
