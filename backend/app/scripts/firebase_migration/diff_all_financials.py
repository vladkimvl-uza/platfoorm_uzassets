"""Run diff_company_financials for every company × {IFRS, NSBU}.

Produces a single summary table:
  code     IFRS-FB  IFRS-DB    NSBU-FB  NSBU-DB
  ngmk     130/26y  13/4y      130/26y  0/0y         <-- IFRS partial, NSBU missing
  agmk     ...

Then lists per-company codes that exist in Firebase but missing in DB,
to make it obvious what didn't migrate.

Run:
  python -m app.scripts.firebase_migration.diff_all_financials
  python -m app.scripts.firebase_migration.diff_all_financials --details
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.financial import FinancialReport, FinancialLine
from app.scripts.firebase_migration.base import FirebaseClient
from app.scripts.firebase_migration.diff_company_financials import (
    find_firebase_record, META_FIELDS,
)


async def collect_db_grid(db: AsyncSession, company_id, standard: str) -> dict[tuple[int, str], float]:
    rep_q = await db.execute(
        select(FinancialReport).where(
            FinancialReport.company_id == company_id,
            FinancialReport.standard == standard,
        )
    )
    out: dict[tuple[int, str], float] = {}
    for r in rep_q.scalars().all():
        ln_q = await db.execute(
            select(FinancialLine).where(FinancialLine.report_id == r.id)
        )
        for ln in ln_q.scalars().all():
            out[(r.year, ln.line_code)] = float(ln.value) if ln.value is not None else None
    return out


def collect_fb_grid(fb_rec: dict | None) -> dict[tuple[int, str], float]:
    out: dict[tuple[int, str], float] = {}
    if not fb_rec:
        return out
    years = fb_rec.get("years")
    if isinstance(years, dict):
        years = list(years.values())
    years = [int(y) for y in (years or []) if y is not None]
    for k, v in fb_rec.items():
        if k in META_FIELDS:
            continue
        if isinstance(v, dict):
            v = list(v.values())
        if not isinstance(v, list):
            continue
        for i, val in enumerate(v):
            if i >= len(years) or val is None or val == "":
                continue
            try:
                out[(years[i], k)] = float(val)
            except (TypeError, ValueError):
                pass
    return out


async def main_async(details: bool):
    fb = FirebaseClient()

    async with AsyncSessionLocal() as db:
        co_q = await db.execute(select(Company).order_by(Company.sort_order))
        companies = list(co_q.scalars().all())

        print(f"{'CODE':<8} {'NAME':<22}  {'IFRS  FB / DB':<20}  {'NSBU  FB / DB':<20}  STATUS")
        print("-" * 100)

        per_co_missing: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        totals = {"fb_cells": 0, "db_cells": 0, "missing_in_db": 0, "extra_in_db": 0}

        for co in companies:
            line = f"{co.code:<8} {(co.name_short or '?')[:22]:<22}  "
            for standard in ("IFRS", "NSBU"):
                fb_rec = await find_firebase_record(fb, co, standard)
                fb_grid = collect_fb_grid(fb_rec)
                db_grid = await collect_db_grid(db, co.id, standard)

                fb_count = len(fb_grid)
                db_count = len(db_grid)
                fb_codes = {c for (_, c) in fb_grid}
                fb_years = {y for (y, _) in fb_grid}
                db_codes = {c for (_, c) in db_grid}
                db_years = {y for (y, _) in db_grid}

                line += f"{fb_count:>4} cells/{len(fb_codes):>2}c×{len(fb_years):>1}y  /  {db_count:>4}/{len(db_codes):>2}c×{len(db_years):>1}y     "

                # Track misses
                missing = set(fb_grid) - set(db_grid)
                extra   = set(db_grid) - set(fb_grid)
                totals["fb_cells"]     += fb_count
                totals["db_cells"]     += db_count
                totals["missing_in_db"] += len(missing)
                totals["extra_in_db"]   += len(extra)

                if missing:
                    per_co_missing[co.code][standard] = sorted(
                        f"{y}.{c}" for (y, c) in missing
                    )

            # Status verdict
            def grade(fb_n, db_n):
                if fb_n == 0 and db_n == 0: return "—"
                if fb_n == 0:               return "+db only"
                if db_n == 0:               return "❌ missing"
                if db_n < fb_n * 0.5:       return "⚠ partial"
                if db_n < fb_n:             return "· near"
                return "✓"

            ifrs_g = grade(*[totals.get(k, 0) for k in []])  # noqa
            print(line)

        print()
        print("=" * 100)
        print("Totals across all companies × both standards:")
        print(f"  Firebase cells:  {totals['fb_cells']}")
        print(f"  DB cells:        {totals['db_cells']}")
        print(f"  Missing in DB:   {totals['missing_in_db']}  ← these should have migrated but did not")
        print(f"  Only in DB:      {totals['extra_in_db']}    ← manually entered after migration (or test data)")

        if details and per_co_missing:
            print()
            print("=" * 100)
            print("Detail — codes present in Firebase but MISSING in DB:")
            for code in sorted(per_co_missing.keys()):
                for standard in ("IFRS", "NSBU"):
                    missing = per_co_missing[code].get(standard, [])
                    if not missing:
                        continue
                    print(f"\n  {code} × {standard}: {len(missing)} cells missing")
                    # Group by year for readability
                    by_year: dict[int, list[str]] = defaultdict(list)
                    for tag in missing:
                        y, c = tag.split(".", 1)
                        by_year[int(y)].append(c)
                    for y in sorted(by_year):
                        codes_str = ", ".join(sorted(by_year[y]))
                        print(f"      {y}: {codes_str}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--details", action="store_true",
                        help="Print every (year, code) that's missing in DB")
    args = parser.parse_args()
    asyncio.run(main_async(args.details))


if __name__ == "__main__":
    main()
