"""Late-migration: pull financial data from Firebase RTDB for the 6 companies
that were missed by the original migration due to name-mapping mismatch.

Background
----------
The 6 affected companies (utc, uty, uap, uks, ung, upt) have data in Firebase
but missing from Postgres because the original migration searched by Russian
company name, while Firebase stores them under shorter/legacy names like
'Узбектелеком' or 'UzPost', not the full 'АО «Узбектелеком»'.

This script uses an explicit hard-coded mapping (Postgres code → list of
candidate Firebase keys) to bridge that gap.

Run:
    docker compose exec backend python /tmp/migrate_missing_6.py --dry-run    # preview
    docker compose exec backend python /tmp/migrate_missing_6.py --apply      # actually write

Idempotent: deletes any existing FinancialReport+lines for (company, year,
standard, report_type) before re-inserting from Firebase. Safe to re-run.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.parse
import urllib.request
from decimal import Decimal
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.financial import FinancialReport, FinancialLine

FB_URL = "https://uza-projectsflow-default-rtdb.europe-west1.firebasedatabase.app"

# Postgres code → list of candidate Firebase keys (try in order)
COMPANY_FB_MAP: dict[str, list[str]] = {
    "utc": ["UzTelecom", "Узбектелеком"],
    "uty": ["Узбекистон Темир Йуллари", "UTY"],
    "uap": ["Uzbekistan Airports"],
    "uks": ["Узкимёсаноат"],
    "ung": ["Узбекнефтегаз"],
    "upt": ["Узбекистон Почтаси", "UzPost"],
}

# Field classification — mirrors monolith's _allF and standard accounting categories
PL_FIELDS = {
    "revenue", "cogs", "grossProfit", "opProfit",
    "finIncome", "finCost", "forex",
    "pbt", "tax", "profit", "depreciation",
    "ebitda", "interestExp",
}
BS_FIELDS = {
    "totalAssets", "totalLiabilities", "equity",
    "totalNCA", "totalCA", "ppe",
    "ltBorrowings", "stBorrowings", "ltBankLoans",
    "ltOtherLoans", "stBankLoans", "stOtherLoans",
    "cash", "debt", "longTermDebt",
    "inventories", "tradeReceivables",
}
CF_FIELDS = {"cfo", "cfi", "cff", "netCashChange", "dividendsPaid"}

META_FIELDS = {
    "years", "source", "_meta", "createdAt", "updatedAt",
    "lastEdit", "editedBy", "checksum", "id",
}


def fetch_firebase(key: str) -> dict | None:
    """Fetch one Firebase financials record. Returns None if missing/empty."""
    enc = urllib.parse.quote(key, safe="")
    url = f"{FB_URL}/pf/financials/{enc}.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    [WARN] Fetch failed for {key}: {e}")
        return None
    if not isinstance(data, dict):
        return None
    # Empty record check: only meta or only nulls
    has_data = False
    for k, v in data.items():
        if k in META_FIELDS:
            continue
        if isinstance(v, dict):
            v = list(v.values())
        if isinstance(v, list) and any(x not in (None, "", 0) for x in v):
            has_data = True
            break
    return data if has_data else None


def normalize_array(v: Any) -> list:
    """Firebase stores arrays as objects {0:val, 1:val} — normalize back to list."""
    if isinstance(v, dict):
        # Sort by numeric key
        try:
            return [v[k] for k in sorted(v.keys(), key=lambda x: int(x))]
        except (ValueError, TypeError):
            return list(v.values())
    if isinstance(v, list):
        return v
    return []


def parse_record(rec: dict) -> dict[int, dict[str, float]]:
    """Convert Firebase record into {year: {line_code: value}} dict.
    Skips null/empty values."""
    if not rec:
        return {}
    years = normalize_array(rec.get("years", []))
    years = [int(y) for y in years if y is not None]
    if not years:
        return {}

    by_year: dict[int, dict[str, float]] = {y: {} for y in years}

    for k, v in rec.items():
        if k in META_FIELDS:
            continue
        vals = normalize_array(v)
        if not vals:
            continue
        for i, val in enumerate(vals):
            if i >= len(years):
                break
            if val in (None, ""):
                continue
            try:
                fv = float(val)
            except (TypeError, ValueError):
                continue
            by_year[years[i]][k] = fv

    # Drop years that ended up empty
    return {y: d for y, d in by_year.items() if d}


def split_by_report_type(line_codes: dict[str, float]) -> dict[str, dict[str, float]]:
    """Split a year's metrics by report_type (PL/BS/CF)."""
    out: dict[str, dict[str, float]] = {"PL": {}, "BS": {}, "CF": {}}
    for code, val in line_codes.items():
        if code in PL_FIELDS:
            out["PL"][code] = val
        elif code in BS_FIELDS:
            out["BS"][code] = val
        elif code in CF_FIELDS:
            out["CF"][code] = val
        # Unknown codes are dropped (with a warning at caller)
    return {k: v for k, v in out.items() if v}


async def migrate_company(
    db: AsyncSession,
    company: Company,
    fb_keys: list[str],
    apply: bool,
) -> dict[str, int]:
    """Migrate one company. Returns counts dict."""
    stats = {"reports_added": 0, "lines_added": 0, "ifrs_keys_used": "", "nsbu_keys_used": ""}

    for standard, key_prefix in [("IFRS", ""), ("NSBU", "__nsbu_")]:
        # Try each candidate key, take first that has data
        rec = None
        used_key = None
        for k in fb_keys:
            rec = fetch_firebase(f"{key_prefix}{k}")
            if rec:
                used_key = f"{key_prefix}{k}"
                break

        if not rec:
            print(f"    [SKIP] {standard}: no data found in Firebase under any of {fb_keys}")
            continue

        if standard == "IFRS":
            stats["ifrs_keys_used"] = used_key
        else:
            stats["nsbu_keys_used"] = used_key

        by_year = parse_record(rec)
        if not by_year:
            print(f"    [SKIP] {standard}: record exists but no usable values (key={used_key})")
            continue

        print(f"    [{standard}] using key '{used_key}': years={sorted(by_year.keys())}")

        for year, line_codes in by_year.items():
            split = split_by_report_type(line_codes)

            for report_type, fields in split.items():
                if not fields:
                    continue

                if apply:
                    # Idempotent: delete existing report+lines first
                    existing_q = await db.execute(
                        select(FinancialReport).where(
                            FinancialReport.company_id == company.id,
                            FinancialReport.year == year,
                            FinancialReport.standard == standard,
                            FinancialReport.report_type == report_type,
                        )
                    )
                    existing = list(existing_q.scalars().all())
                    for ex in existing:
                        await db.execute(
                            delete(FinancialLine).where(FinancialLine.report_id == ex.id)
                        )
                        await db.delete(ex)
                    await db.flush()

                    # Insert fresh report
                    report = FinancialReport(
                        company_id=company.id,
                        year=year,
                        standard=standard,
                        report_type=report_type,
                        currency="UZS",
                        unit_scale=1000,  # legacy meta — endpoint ignores this, hardcodes 1e9
                        source="firebase_late_migration",
                        is_audited=False,
                    )
                    db.add(report)
                    await db.flush()  # get report.id

                    for line_code, value in fields.items():
                        db.add(FinancialLine(
                            report_id=report.id,
                            line_code=line_code,
                            line_name=line_code,
                            value=Decimal(str(value)),
                            sort_order=0,
                            is_subtotal=False,
                            is_calculated=False,
                            indent_level=0,
                        ))

                stats["reports_added"] += 1
                stats["lines_added"] += len(fields)

    return stats


async def main_async(apply: bool):
    print(f"{'='*100}")
    print(f"Late migration: Firebase → Postgres for 6 companies")
    print(f"Mode: {'APPLY (writing to DB)' if apply else 'DRY RUN (no writes)'}")
    print(f"{'='*100}\n")

    async with AsyncSessionLocal() as db:
        for code, fb_keys in COMPANY_FB_MAP.items():
            # Find the company record
            co_q = await db.execute(select(Company).where(Company.code == code))
            company = co_q.scalar_one_or_none()
            if not company:
                print(f"━━━ {code.upper()} → NOT FOUND in companies table, skipping")
                continue

            print(f"━━━ {code.upper()} ({company.name_ru})")
            print(f"    candidates: {fb_keys}")

            try:
                stats = await migrate_company(db, company, fb_keys, apply)
                print(f"    → reports: +{stats['reports_added']}, lines: +{stats['lines_added']}")
                print(f"      IFRS key: {stats['ifrs_keys_used'] or '(none)'}")
                print(f"      NSBU key: {stats['nsbu_keys_used'] or '(none)'}")
            except Exception as e:
                print(f"    [ERROR] {e}")
                import traceback
                traceback.print_exc()
            print()

        if apply:
            print("Committing transaction...")
            await db.commit()
            print("Done.")
        else:
            print("DRY RUN — no changes committed. Re-run with --apply to actually migrate.")


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    g.add_argument("--apply",   action="store_true", help="Actually write to DB")
    args = p.parse_args()
    asyncio.run(main_async(apply=args.apply))


if __name__ == "__main__":
    main()
