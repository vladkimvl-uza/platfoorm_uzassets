"""Force re-import of /pf/financials with verbose per-company logging.

Why this exists:
  TasksMigrator + the regular `--only financials` pass uses an UPSERT-style
  flow that keeps existing rows. If a previous migration only got partway
  through (network drop, transient DB error, transactional partial commit),
  the existing rows can be missing fields and a normal re-run won't fill them.

  This script does the safe thing:
    1. Wipe ALL financial_reports + financial_lines
    2. Run the FinancialsMigrator against the same Firebase tree
    3. Print every step — companies seen, fields per company,
       any per-company error in detail (not buried in a summary).

  After this finishes, the DB will hold exactly what Firebase has.
  Running this script does NOT touch tasks/projects/companies/etc.

Usage:
  python -m app.scripts.firebase_migration.force_reimport_financials
  python -m app.scripts.firebase_migration.force_reimport_financials --no-wipe
  python -m app.scripts.firebase_migration.force_reimport_financials --only-company ngmk
"""
from __future__ import annotations

import argparse
import asyncio
import traceback

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.financial import FinancialReport, FinancialLine
from app.scripts.firebase_migration.base import (
    FirebaseClient, MigrationContext, MigrationReport, normalize_array, safe_str, safe_int, safe_decimal,
)


META_FIELDS = {
    "name", "source", "years", "lastUpdated", "_note", "_meta",
    "unitScale", "currency", "notes", "status",
}


async def wipe_all_financials(db: AsyncSession) -> tuple[int, int]:
    """Delete ALL financial_lines and financial_reports. Returns (lines_deleted, reports_deleted)."""
    lc = (await db.execute(select(func.count(FinancialLine.id)))).scalar()
    rc = (await db.execute(select(func.count(FinancialReport.id)))).scalar()
    await db.execute(delete(FinancialLine))
    await db.execute(delete(FinancialReport))
    await db.commit()
    return lc, rc


async def build_company_lookup(db: AsyncSession) -> dict:
    """Multi-form company lookup like FinancialsMigrator uses, plus aggressive normalisation."""
    import re
    def _agg(s): return re.sub(r"[^a-zа-яё0-9]", "", (s or "").lower())

    res = await db.execute(select(Company))
    lookup = {}
    for c in res.scalars().all():
        for v in [c.code, c.name_short, c.name_ru, c.name_uz, c.name_en]:
            if v:
                lookup[str(v).strip().lower()] = c
                lookup[_agg(v)] = c
        if c.name_ru:
            stripped = (c.name_ru.replace("АО ", "").replace("«", "").replace("»", "")
                        .strip().lower())
            if stripped:
                lookup[stripped] = c
    return lookup


def _classify_report_type(code: str) -> str:
    """Map line code → PL/BS/CF based on monolith FDE editor sections."""
    PL = {"revenue", "cogs", "grossProfit", "depreciation", "opProfit",
          "finIncome", "finCost", "forex", "pbt", "tax", "profit"}
    BS = {"ppe", "totalNCA", "totalCA", "cash", "totalAssets", "equity",
          "ltBorrowings", "stBorrowings", "totalLiabilities",
          "ltBankLoans", "ltOtherLoans", "stBankLoans", "stOtherLoans", "debt"}
    CF = {"cfo", "cfi", "cff", "netCashChange", "dividendsPaid",
          "interestExp", "ebitda"}
    if code in PL: return "PL"
    if code in BS: return "BS"
    if code in CF: return "CF"
    return "PL"  # default for unknown


async def reimport(db: AsyncSession, fb: FirebaseClient, only_company: str | None = None):
    fin = fb.get("/pf/financials")
    if not isinstance(fin, dict):
        print("⚠ /pf/financials is empty in Firebase")
        return

    all_keys = list(fin.keys())
    all_keys = [k for k in all_keys if not (k.startswith("_") and not k.startswith("__nsbu_"))]

    lookup = await build_company_lookup(db)
    print(f"  Firebase keys to process: {len(all_keys)}")
    print(f"  Company lookup forms:     {len(lookup)}")

    totals = {
        "matched": 0, "unmatched": 0, "skipped_no_data": 0,
        "reports_created": 0, "lines_created": 0, "errors": 0,
    }
    errors: list[str] = []

    for raw_key in all_keys:
        is_nsbu = raw_key.startswith("__nsbu_")
        company_key = raw_key[len("__nsbu_"):] if is_nsbu else raw_key
        standard = "NSBU" if is_nsbu else "IFRS"

        company = lookup.get(company_key.strip().lower())
        if not company:
            # try aggressive normalisation
            import re
            agg = re.sub(r"[^a-zа-яё0-9]", "", company_key.lower())
            company = lookup.get(agg)
        if not company:
            totals["unmatched"] += 1
            print(f"    ⚠ unmatched: '{raw_key}'")
            continue

        if only_company and company.code != only_company.lower():
            continue

        data = fin.get(raw_key)
        if not isinstance(data, dict):
            totals["skipped_no_data"] += 1
            continue

        years_raw = normalize_array(data.get("years"))
        years = [safe_int(y) for y in years_raw if safe_int(y)]
        years = [y for y in years if y and 2000 <= y <= 2100]
        if not years:
            totals["skipped_no_data"] += 1
            print(f"    ⚠ {raw_key} [{standard}]: no valid years")
            continue

        # Discover all line series
        lines_data: dict[str, list] = {}
        for fkey, fval in data.items():
            if fkey in META_FIELDS:
                continue
            if not isinstance(fval, (list, dict)):
                continue
            arr = normalize_array(fval)
            if arr:
                lines_data[fkey] = arr

        if not lines_data:
            totals["skipped_no_data"] += 1
            continue

        # Group by report type
        codes_by_rtype: dict[str, list[str]] = {"PL": [], "BS": [], "CF": []}
        for code in lines_data:
            rt = _classify_report_type(code)
            codes_by_rtype[rt].append(code)

        unit_scale = safe_int(data.get("unitScale")) or 1000
        source     = safe_str(data.get("source"), 32) or standard.lower()
        notes      = safe_str(data.get("notes"), 4096)

        try:
            for year in years:
                year_idx = years.index(year)
                for rtype, codes in codes_by_rtype.items():
                    if not codes:
                        continue
                    has_any = any(
                        year_idx < len(lines_data.get(c, [])) and lines_data[c][year_idx] is not None
                        for c in codes
                    )
                    if not has_any:
                        continue

                    rep = FinancialReport(
                        company_id=company.id,
                        year=year, quarter=None,
                        standard=standard, report_type=rtype,
                        currency="UZS", unit_scale=unit_scale,
                        source=source, notes=notes,
                        extra={"firebase_data_key": raw_key},
                    )
                    db.add(rep)
                    await db.flush()
                    totals["reports_created"] += 1

                    for code in codes:
                        arr = lines_data.get(code, [])
                        if year_idx >= len(arr):
                            continue
                        val = arr[year_idx]
                        if val is None:
                            continue
                        dec = safe_decimal(val)
                        if dec is None:
                            continue
                        db.add(FinancialLine(
                            report_id=rep.id,
                            line_code=code,
                            line_name=code,  # raw — operator can rename via UI later
                            value=dec,
                            is_subtotal=False, is_calculated=False,
                            sort_order=0,
                        ))
                        totals["lines_created"] += 1

            await db.commit()
            totals["matched"] += 1
            cells = sum(
                1 for c in lines_data
                for v in lines_data[c]
                if v is not None
            )
            print(f"    ✓ {raw_key:<35} [{standard}] → {company.code:<6}  "
                  f"{len(lines_data)} codes, {cells} cells, {len(years)} years")

        except Exception as e:
            await db.rollback()
            totals["errors"] += 1
            err = f"{raw_key}: {type(e).__name__}: {str(e)[:160]}"
            errors.append(err)
            print(f"    ❌ {raw_key} [{standard}]: {err}")

    print()
    print("=" * 70)
    print("Totals:")
    for k, v in totals.items():
        print(f"  {k:>20}: {v}")
    if errors:
        print()
        print("First errors:")
        for e in errors[:10]:
            print(f"  · {e}")


async def main_async(no_wipe: bool, only_company: str | None):
    fb = FirebaseClient()
    async with AsyncSessionLocal() as db:
        if not no_wipe:
            print("Step 1/2: wiping all financial_reports + financial_lines …")
            lc, rc = await wipe_all_financials(db)
            print(f"   deleted {rc} reports, {lc} lines")
            print()

        print("Step 2/2: re-importing from Firebase …")
        try:
            await reimport(db, fb, only_company)
        except Exception as e:
            print(f"FATAL: {type(e).__name__}: {e}")
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wipe", action="store_true",
                        help="Skip the wipe step (re-import on top of existing data — may double-up)")
    parser.add_argument("--only-company", help="Limit to one company code (e.g. ngmk)")
    args = parser.parse_args()
    asyncio.run(main_async(args.no_wipe, args.only_company))


if __name__ == "__main__":
    main()
