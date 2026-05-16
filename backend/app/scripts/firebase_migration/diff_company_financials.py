"""Field-by-field diff: Firebase vs DB for a single company × standard.

Run:
  python -m app.scripts.firebase_migration.diff_company_financials ngmk
  python -m app.scripts.firebase_migration.diff_company_financials ngmk --standard NSBU

Output is a wide table per (year × line_code) with FB / DB columns side-by-side
so you can spot exactly what didn't migrate and where.
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.financial import FinancialReport, FinancialLine
from app.scripts.firebase_migration.base import FirebaseClient


META_FIELDS = {
    "name", "source", "years", "lastUpdated", "_note", "_meta",
    "unitScale", "currency", "notes", "status",
}


async def find_firebase_record(fb: FirebaseClient, company: Company, standard: str) -> dict | None:
    """Find /pf/financials/<key> for this (company, standard) using multi-form lookup."""
    fin = fb.get("/pf/financials")
    if not isinstance(fin, dict):
        return None

    candidates = [
        company.code, company.name_short, company.name_ru, company.name_uz, company.name_en
    ]
    candidates = [c for c in candidates if c]

    prefix = "__nsbu_" if standard == "NSBU" else ""

    # Try exact and lower-case match
    for c in candidates:
        for key in (f"{prefix}{c}", f"{prefix}{c.lower()}"):
            if key in fin:
                return fin[key]

    # Aggressive normalised match
    import re
    def _norm(s): return re.sub(r"[^a-zа-яё0-9]", "", (s or "").lower())
    target_norms = {_norm(c) for c in candidates if c}
    for k, v in fin.items():
        if standard == "NSBU" and not k.startswith("__nsbu_"):
            continue
        if standard == "IFRS" and k.startswith("__nsbu_"):
            continue
        bare = k[len("__nsbu_"):] if k.startswith("__nsbu_") else k
        if _norm(bare) in target_norms:
            return v
    return None


async def diff(db: AsyncSession, code: str, standard: str):
    fb = FirebaseClient()

    res = await db.execute(select(Company).where(Company.code == code.lower()))
    company = res.scalar_one_or_none()
    if not company:
        print(f"⚠ no company with code='{code}'")
        return

    print(f"Company: {company.code} ({company.name_short})")
    print(f"Standard: {standard}")
    print()

    fb_rec = await find_firebase_record(fb, company, standard)
    if fb_rec is None:
        print(f"⚠ Firebase has NO /pf/financials entry for this company × {standard}")
    else:
        years = fb_rec.get("years")
        if isinstance(years, dict):
            years = list(years.values())
        print(f"Firebase years: {years}")

    # ── load DB data ──
    rep_q = await db.execute(
        select(FinancialReport).where(
            FinancialReport.company_id == company.id,
            FinancialReport.standard == standard,
        )
    )
    reports = list(rep_q.scalars().all())
    print(f"DB reports: {len(reports)}  ({[(r.year, r.report_type) for r in reports]})")

    # Build flat: { (year, code): value }
    db_values: dict[tuple[int, str], float] = {}
    for r in reports:
        ln_q = await db.execute(
            select(FinancialLine).where(FinancialLine.report_id == r.id)
        )
        for ln in ln_q.scalars().all():
            db_values[(r.year, ln.line_code)] = float(ln.value) if ln.value is not None else None

    # Build flat from Firebase
    fb_values: dict[tuple[int, str], float] = {}
    if fb_rec:
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
                if i >= len(years):
                    continue
                if val is None or val == "":
                    continue
                try:
                    fb_values[(years[i], k)] = float(val)
                except (TypeError, ValueError):
                    pass

    # ── union of all (year, code) ──
    all_keys = sorted(set(fb_values) | set(db_values), key=lambda x: (x[0], x[1]))
    if not all_keys:
        print("\n(no data on either side)")
        return

    print()
    print(f"{'YEAR':<6} {'CODE':<22} {'FIREBASE':>14}   {'DB':>14}   STATUS")
    print("-" * 80)
    matches = mismatches = only_fb = only_db = 0
    for (year, code) in all_keys:
        fb_v = fb_values.get((year, code))
        db_v = db_values.get((year, code))

        fb_s = f"{fb_v:>14.2f}" if fb_v is not None else f"{'—':>14}"
        db_s = f"{db_v:>14.2f}" if db_v is not None else f"{'—':>14}"

        if fb_v is None and db_v is None:
            continue
        elif fb_v is not None and db_v is None:
            status = "❌ MISSING IN DB"
            only_fb += 1
        elif fb_v is None and db_v is not None:
            status = "+ db-only (manually entered?)"
            only_db += 1
        elif abs((fb_v or 0) - (db_v or 0)) < 0.001:
            status = "✓"
            matches += 1
        else:
            status = f"⚠ MISMATCH (Δ={(db_v - fb_v):.2f})"
            mismatches += 1

        print(f"{year:<6} {code:<22} {fb_s}   {db_s}   {status}")

    print()
    print("-" * 80)
    print(f"  matches: {matches}  |  mismatches: {mismatches}  "
          f"|  Firebase-only (not migrated): {only_fb}  |  DB-only: {only_db}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("code", help="Company code (e.g. ngmk, agmk)")
    parser.add_argument("--standard", choices=["IFRS", "NSBU"], default="IFRS")
    args = parser.parse_args()
    async with AsyncSessionLocal() as db:
        await diff(db, args.code, args.standard)


if __name__ == "__main__":
    asyncio.run(main())
