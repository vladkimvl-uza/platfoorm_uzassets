"""Audit Firebase /pf/financials vs PostgreSQL financial_reports/financial_lines.

Purpose: shows EXACTLY what the migrator sees in Firebase — which company keys
match canonical companies, which line codes are recognised by the catalog
(get pretty Russian names + sort order) versus those known only by their raw
firebase code.

Important: as of the latest FinancialsMigrator, NO fields are dropped during
import. Codes outside the catalog are still saved to financial_lines, just
with line_name == raw code. The "unknown" report below is informational only —
it tells you which codes might benefit from being added to the catalog for
nicer display names.

Run:
  python -m app.scripts.firebase_migration.audit_financials
  python -m app.scripts.firebase_migration.audit_financials --verbose
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.financial import FinancialReport, FinancialLine
from app.scripts.firebase_migration.base import FirebaseClient


def _load_catalog_codes() -> set[str]:
    catalog_path = (Path(__file__).resolve().parents[3]
                    / "data" / "seed" / "financial_lines_catalog.json")
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    return set(d.get("code", "") for d in raw if d.get("code"))


# Fields the monolith stores at the top level of each company entry that
# are NOT line codes — these are metadata / wrappers and must NOT be reported
# as "dropped financial lines".
META_FIELDS = {
    "name", "source", "years", "lastUpdated", "_note", "_meta",
    "unitScale", "currency", "notes", "status",
}


async def build_company_lookup(db: AsyncSession) -> dict[str, Company]:
    """Lower-cased multi-form lookup matching FinancialsMigrator behaviour."""
    res = await db.execute(select(Company))
    lookup = {}
    for c in res.scalars().all():
        for v in [c.code, c.name_short, c.name_ru, c.name_uz, c.name_en]:
            if v:
                lookup[str(v).strip().lower()] = c
        # Strip surrounding АО/AO/JSC quotes — match migrator's normalization.
        if c.name_ru:
            stripped = (c.name_ru
                        .replace("АО ", "").replace("«", "").replace("»", "")
                        .strip().lower())
            if stripped:
                lookup[stripped] = c
    return lookup


def _classify_top_level_fields(data: dict, catalog_codes: set[str]) -> tuple[list[str], list[str], list[str]]:
    """Return (catalog_known, catalog_unknown, meta_keys).

    Both lists are real line series and BOTH will be migrated. The split is
    only about whether the catalog has a friendly name for the code.
    """
    catalog_known, catalog_unknown, meta = [], [], []
    for k, v in data.items():
        if k in META_FIELDS:
            meta.append(k)
            continue
        if isinstance(v, (list, dict)):
            if k in catalog_codes:
                catalog_known.append(k)
            else:
                catalog_unknown.append(k)
        else:
            meta.append(k)
    return catalog_known, catalog_unknown, meta


async def audit(verbose: bool):
    catalog_codes = _load_catalog_codes()
    print(f"  catalog has {len(catalog_codes)} known line codes")

    fb = FirebaseClient()
    fin = fb.get("/pf/financials")
    if not isinstance(fin, dict):
        print("⚠ /pf/financials is empty in Firebase or not a dict — nothing to audit")
        return

    all_keys = list(fin.keys())
    all_keys = [k for k in all_keys if not (k.startswith("_") and not k.startswith("__nsbu_"))]
    print(f"  Firebase /pf/financials: {len(all_keys)} top-level keys (excluding _meta)")

    async with AsyncSessionLocal() as db:
        lookup = await build_company_lookup(db)
        print(f"  Company lookup keys: {len(lookup)}")

        # ====== iterate ======
        stats = {
            "matched": 0, "unmatched": 0,
            "total_known_fields": 0, "total_unknown_fields": 0,
            "fields_with_values": 0, "fields_all_null": 0,
        }
        unknown_codes_seen: dict[str, int] = {}
        unmatched_keys: list[str] = []

        for raw_key in all_keys:
            is_nsbu = raw_key.startswith("__nsbu_")
            company_key = raw_key[len("__nsbu_"):] if is_nsbu else raw_key
            standard = "NSBU" if is_nsbu else "IFRS"

            data = fin.get(raw_key)
            if not isinstance(data, dict):
                continue

            company = lookup.get(company_key.strip().lower())
            if not company:
                stats["unmatched"] += 1
                unmatched_keys.append(raw_key)
                if verbose:
                    print(f"  ⚠ UNMATCHED: '{raw_key}' (no canonical company)")
                continue

            stats["matched"] += 1
            known, unknown, _meta = _classify_top_level_fields(data, catalog_codes)

            stats["total_known_fields"]   += len(known)
            stats["total_unknown_fields"] += len(unknown)
            for c in unknown:
                unknown_codes_seen[c] = unknown_codes_seen.get(c, 0) + 1

            # Per-field: count years with non-null values
            field_summaries: list[str] = []
            empty_codes: list[str] = []
            filled_codes: list[str] = []
            years_arr = data.get("years") or []
            if isinstance(years_arr, dict):
                years_arr = list(years_arr.values())

            for code in known + unknown:
                arr = data.get(code)
                if isinstance(arr, dict):
                    arr = list(arr.values())
                if not isinstance(arr, list):
                    continue
                non_null = sum(1 for x in arr if x is not None and x != "" and x != 0)
                total    = len(arr)
                if non_null > 0:
                    filled_codes.append(f"{code}({non_null}/{total})")
                    stats["fields_with_values"] += 1
                else:
                    empty_codes.append(code)
                    stats["fields_all_null"] += 1

            if verbose:
                print(f"\n  {raw_key:<35} [{standard}] → {company.code} ({company.name_short})")
                print(f"     years: {years_arr}")
                if filled_codes:
                    print(f"     ✓ FILLED  ({len(filled_codes)}): {', '.join(filled_codes)}")
                if empty_codes:
                    print(f"     · EMPTY   ({len(empty_codes)}): {', '.join(empty_codes)}")
                if unknown:
                    print(f"     • unknown to catalog: {', '.join(unknown)} (still imported)")

        # ====== summary ======
        print()
        print("=" * 70)
        print("Summary")
        print(f"  matched companies:     {stats['matched']}")
        print(f"  unmatched companies:   {stats['unmatched']}")
        print(f"  catalog-known fields:  {stats['total_known_fields']}")
        print(f"  unknown-but-imported:  {stats['total_unknown_fields']}")
        print(f"  fields with values:    {stats['fields_with_values']}")
        print(f"  fields entirely empty: {stats['fields_all_null']}  ← these are NULL in Firebase, nothing to migrate")

        if unknown_codes_seen:
            print()
            print(f"Unknown line codes ({len(unknown_codes_seen)} unique) — "
                  "data IS migrated, but adding these to catalog gives them friendly names:")
            for code, n in sorted(unknown_codes_seen.items(), key=lambda x: -x[1]):
                print(f"  · {code:<30} (in {n} record(s))")

        if unmatched_keys:
            print()
            print(f"Unmatched Firebase keys ({len(unmatched_keys)}) — these ARE NOT migrated:")
            for k in unmatched_keys[:20]:
                print(f"  · {k}")
            if len(unmatched_keys) > 20:
                print(f"  · ... ({len(unmatched_keys) - 20} more)")


async def main():
    parser = argparse.ArgumentParser(description="Audit Firebase financials vs DB catalog")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print every company key, not just the dropped ones")
    args = parser.parse_args()
    await audit(args.verbose)


if __name__ == "__main__":
    asyncio.run(main())
