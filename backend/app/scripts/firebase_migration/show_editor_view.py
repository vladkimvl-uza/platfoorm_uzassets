"""Show the exact data that FinancialsEdit.vue receives from the backend
for a given company × standard.

This bypasses the Vue UI and queries the same endpoints (list + get-each)
that the frontend uses, then prints a wide table.

Usage:
  python -m app.scripts.firebase_migration.show_editor_view ngmk
  python -m app.scripts.firebase_migration.show_editor_view ngmk --standard NSBU
  python -m app.scripts.firebase_migration.show_editor_view agmk --standard IFRS

Helps tell apart 3 distinct failure modes:
  1. Migration didn't import any reports for this (company, standard)
  2. Reports exist but contain zero financial_lines
  3. Reports + lines exist with values that just aren't what you expect
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.financial import FinancialReport, FinancialLine


async def show(db: AsyncSession, code: str, standard: str):
    co_q = await db.execute(select(Company).where(func.lower(Company.code) == code.lower()))
    co = co_q.scalar_one_or_none()
    if not co:
        print(f"⚠ no company with code='{code}'")
        return

    print(f"Company:  {co.code} ({co.name_short})  id={co.id}")
    print(f"Standard: {standard}")
    print()

    # === 1. list_reports as the API does ===
    list_q = (select(FinancialReport, func.count(FinancialLine.id).label("lc"))
              .outerjoin(FinancialLine, FinancialLine.report_id == FinancialReport.id)
              .where(FinancialReport.company_id == co.id,
                     FinancialReport.standard == standard)
              .group_by(FinancialReport.id)
              .order_by(desc(FinancialReport.year)))
    rows = (await db.execute(list_q)).all()

    if not rows:
        print(f"⚠ NO reports in DB for {co.code} × {standard}")
        print()
        print("Possible causes:")
        print("  · Migration was never run for this company")
        print("  · Firebase had no /pf/financials entry under any company-name variant")
        print("  · Migration ran in --dry-run mode")
        print()
        print(f"Try:  docker compose exec backend python -m app.scripts.firebase_migration.diff_company_financials {code} --standard {standard}")
        return

    print(f"Found {len(rows)} report(s):")
    for r in rows:
        rep = r.FinancialReport
        print(f"  · year={rep.year}  type={rep.report_type}  lines={r.lc}  "
              f"unit_scale={rep.unit_scale}  source={rep.source!r}")

    # === 2. Per-year × code grid (what cellValues looks like in the editor) ===
    grid: dict[int, dict[str, float | None]] = defaultdict(dict)
    all_codes: set[str] = set()
    for r in rows:
        rep = r.FinancialReport
        ln_q = await db.execute(
            select(FinancialLine).where(FinancialLine.report_id == rep.id)
            .order_by(FinancialLine.sort_order, FinancialLine.line_code)
        )
        for ln in ln_q.scalars().all():
            grid[rep.year][ln.line_code] = float(ln.value) if ln.value is not None else None
            all_codes.add(ln.line_code)

    if not all_codes:
        print()
        print("⚠ Reports exist but contain NO financial_lines")
        print("   → migration created the report headers but no values were imported")
        return

    years = sorted(grid.keys())
    codes = sorted(all_codes)

    # Wide table — code as rows, years as columns
    print()
    col_w = 14
    print(f"{'CODE':<22} | " + " ".join(f"{y:>{col_w}}" for y in years))
    print("-" * (24 + (col_w + 1) * len(years)))
    for code_ in codes:
        cells = []
        for y in years:
            v = grid[y].get(code_)
            cells.append(f"{v:>{col_w}.2f}" if v is not None else f"{'—':>{col_w}}")
        print(f"{code_:<22} | " + " ".join(cells))

    print()
    total_cells = sum(1 for y in years for c in codes if grid[y].get(c) is not None)
    empty_cells = (len(years) * len(codes)) - total_cells
    print(f"Total: {len(codes)} codes × {len(years)} years = {len(codes) * len(years)} cells; "
          f"{total_cells} filled, {empty_cells} empty")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("code", help="Company code (e.g. ngmk, agmk, umk)")
    parser.add_argument("--standard", choices=["IFRS", "NSBU"], default="IFRS")
    args = parser.parse_args()
    async with AsyncSessionLocal() as db:
        await show(db, args.code, args.standard)


if __name__ == "__main__":
    asyncio.run(main())
