"""Phase 6 — ProcurementClosuresMigrator.

Reads /pf/procurementContracts.rows (8346 raw closures) from Firebase or from
system_config.firebase_dump.procurementContracts (Phase 4 already snapshotted
that 6.4 MB JSONB). Inserts into procurement_closures, then computes
market_avg + deviation_pct in a second pass using median-per-(product_code, year).

Algorithm note: the monolith uses log-scale clustering (bs=0.5, k_cap=7) to
split a productCode into sub-products before benchmarking. THIS migrator does
NOT cluster — it uses raw productCode median. Result: deviation_pct is approxi-
mate (some product codes mix physically different goods → noisy). True clean
benchmarking requires running the clustering pass on procurement_data first
and writing to product_clusters + procurement_benchmarks. Out of scope for
Phase 6 — done in Phase 7 if needed.

Wiring: append `ProcurementClosuresMigrator` to ALL_MIGRATORS in migrators.py.
"""
from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import delete, select, text

from app.models.company import Company
from app.models.procurement import ProcurementClosure

from .base import Migrator, MigrationContext


log = logging.getLogger(__name__)


# =====================================================================
# Helpers
# =====================================================================

def _to_decimal(v: Any) -> Optional[Decimal]:
    if v is None or v == "" or v == "—" or v == "-":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _parse_date(v: Any) -> Optional[date]:
    """Parse Firebase date string ('YYYY-MM-DD' or ISO with time)."""
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        # Try common alternatives
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    return None


def _year_from_row(row: dict[str, Any]) -> Optional[int]:
    """Year priority: explicit `year` field → contractDate → startDate."""
    if "year" in row:
        y = _to_int(row["year"])
        if y:
            return y
    for fld in ("contractDate", "startDate", "endDate"):
        d = _parse_date(row.get(fld))
        if d:
            return d.year
    return None


async def _build_company_lookup(ctx: MigrationContext) -> dict[str, Company]:
    """Reuse the same multi-key lookup as Phase 5."""
    rows_q = await ctx.db.execute(select(Company))
    rows = rows_q.scalars().all()
    lookup: dict[str, Company] = {}
    for c in rows:
        for fld in ("code", "name_ru", "name_short", "name_uz", "name_en"):
            v = getattr(c, fld, None)
            if v:
                lookup[v.lower().strip()] = c
                # Also stripped of АО/quotes
                stripped = v.lower().strip().replace("«", "").replace("»", "").replace('"', "")
                if stripped.startswith("ао "):
                    stripped = stripped[3:].strip()
                if stripped:
                    lookup[stripped] = c
    return lookup


def _resolve_company(co_key: str, lookup: dict[str, Company]) -> Optional[Company]:
    if not co_key:
        return None
    return lookup.get(co_key.lower().strip())


def _category_id_from_product(product_code: Optional[str]) -> Optional[str]:
    """Extract KTRU category prefix. Example:
       '01.30.10.121-00063' → '01.30.10.121'
       'ABC-123-456'        → 'ABC'   (best-effort)
    """
    if not product_code:
        return None
    pc = product_code.strip()
    if "-" in pc:
        return pc.split("-", 1)[0]
    return pc


# =====================================================================
# ProcurementClosures migrator
# =====================================================================

class ProcurementClosuresMigrator(Migrator):
    """Migrate /pf/procurementContracts.rows → procurement_closures.

    Source preference:
      1. /pf/procurementContracts.rows (live Firebase)
      2. system_config['firebase_dump.procurementContracts'].rows (PG snapshot)

    Strategy:
      1. DELETE all existing rows for (company_id) being touched (full refresh
         per company) — simpler than per-row UPSERT and matches monolith's
         bulk-replace semantics.
      2. INSERT new rows.
      3. Second pass: compute median per (product_code, year) → fill market_avg
         + deviation_pct in-place.
    """

    name = "procurement_closures"
    firebase_path = "/pf/procurementContracts"

    async def apply(self, ctx: MigrationContext) -> None:
        # 1. Get the raw rows — try FB first, then snapshot
        contracts = ctx.fb.get(self.firebase_path)
        rows: list[dict[str, Any]] = []
        if isinstance(contracts, dict):
            r = contracts.get("rows")
            if isinstance(r, list):
                rows = r

        if not rows:
            # Fall back to system_config snapshot from Phase 4
            res = await ctx.db.execute(text(
                "SELECT value FROM system_config "
                "WHERE key = 'firebase_dump.procurementContracts' LIMIT 1"
            ))
            cfg_row = res.first()
            if cfg_row and cfg_row[0]:
                snap = cfg_row[0]
                if isinstance(snap, str):
                    snap = json.loads(snap)
                if isinstance(snap, dict):
                    r = snap.get("rows")
                    if isinstance(r, list):
                        rows = r
                        print(f"  ⓘ procurement_closures: using system_config snapshot ({len(rows)} rows)")

        if not rows:
            ctx.report.add_warning("procurement_closures: no rows in FB or snapshot")
            return

        lookup = await _build_company_lookup(ctx)

        # 2. Group rows by company_id (for bulk wipe-then-insert per company)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        skipped_orphan = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            co_abbr = (row.get("companyAbbr") or row.get("companyCode") or "").strip()
            if not co_abbr:
                skipped_orphan += 1
                continue
            company = _resolve_company(co_abbr, lookup)
            if not company:
                skipped_orphan += 1
                ctx.report.add_skip("procurement_closures", f"company '{co_abbr}' not in PG")
                continue
            grouped[str(company.id)].append(row)

        # If dry-run: just count and exit
        if ctx.dry_run:
            total = sum(len(v) for v in grouped.values())
            print(f"  ✓ procurement_closures (DRY): would insert {total} rows "
                  f"across {len(grouped)} companies, {skipped_orphan} orphan-rows")
            ctx.report.add_create("procurement_closures") if total else None
            return

        # 3. WIPE existing rows for touched companies
        co_ids = list(grouped.keys())
        if co_ids:
            await ctx.db.execute(
                delete(ProcurementClosure).where(
                    ProcurementClosure.company_id.in_(co_ids)
                )
            )
            await ctx.db.flush()

        # 4. INSERT all rows
        inserted = 0
        for co_id_str, co_rows in grouped.items():
            for row in co_rows:
                year = _year_from_row(row)
                product_code = (row.get("productCode") or "").strip() or None
                # Note: row.get("category") is a free-text description (up to 110 chars)
                # like "???????? ???????? ????????..." ? NOT a KTRU code. Always derive
                # category_id from productCode prefix instead.
                category_id = _category_id_from_product(product_code)

                unit_price = _to_decimal(row.get("unitPrice"))
                volume = _to_decimal(row.get("amount"))
                # `contractSumma` (UZS gross) is more reliable than unitPrice*amount
                total_amount = _to_decimal(row.get("contractSumma") or row.get("contractAmount"))
                saved_amount = _to_decimal(row.get("savedAmount"))

                ctx.db.add(ProcurementClosure(
                    company_id=co_id_str,
                    year=year,
                    closure_date=_parse_date(row.get("contractDate") or row.get("startDate")),
                    category_id=category_id,
                    product_code=product_code,
                    product_name=(row.get("productName") or "").strip()[:1024] or None,
                    unit_price=unit_price,
                    market_avg=None,           # filled by second pass
                    deviation_pct=None,        # filled by second pass
                    unit=(row.get("unit") or "").strip()[:32] or None,
                    volume=volume,
                    total_amount=total_amount,
                    saved_amount=saved_amount,
                    supplier_name=(row.get("vendor") or "").strip()[:512] or None,
                    supplier_inn=(row.get("vendorInn") or "").strip()[:32] or None,
                    contract_id=(row.get("id") or "").strip()[:64] or None,
                    lot_id=(row.get("lotId") or "").strip()[:64] or None,
                    platform=(row.get("platform") or "").strip()[:64] or None,
                    purchase_type=(row.get("purchaseType") or "").strip()[:32] or None,
                    region=(row.get("region") or "").strip()[:128] or None,
                    sector=(row.get("sector") or "").strip()[:64] or None,
                    is_clean=True,
                    is_dirty=False,
                    extra=row,
                ))
                inserted += 1
                ctx.report.add_create("procurement_closures")

                # Periodic flush — avoid 8000+ pending inserts in memory
                if inserted % 500 == 0:
                    await ctx.db.flush()

        await ctx.db.flush()
        print(f"  ✓ procurement_closures: {inserted} inserted, "
              f"{skipped_orphan} orphan-rows")

        # 5. SECOND PASS — compute market_avg & deviation_pct
        await self._compute_benchmarks(ctx)

    async def _compute_benchmarks(self, ctx: MigrationContext) -> None:
        """For each (product_code, year), median(unit_price) → market_avg.
        deviation_pct = (unit_price - market_avg) / market_avg * 100."""

        # Pull all rows we just inserted (id, product_code, year, unit_price)
        res = await ctx.db.execute(text("""
            SELECT id, product_code, year, unit_price
            FROM procurement_closures
            WHERE product_code IS NOT NULL AND unit_price IS NOT NULL
        """))
        all_rows = res.all()

        # Group prices per (product_code, year)
        groups: dict[tuple, list[Decimal]] = defaultdict(list)
        for r in all_rows:
            key = (r[1], r[2])
            groups[key].append(Decimal(str(r[3])))

        # Median per group
        medians: dict[tuple, Decimal] = {}
        for key, prices in groups.items():
            if len(prices) >= 2:                # need ≥2 samples to compute median meaningfully
                medians[key] = Decimal(str(statistics.median(prices)))

        # Bulk update each row's market_avg / deviation_pct
        updated = 0
        for r in all_rows:
            row_id, pc, yr, up = r
            key = (pc, yr)
            mavg = medians.get(key)
            if mavg is None or mavg == 0:
                continue
            up_d = Decimal(str(up))
            dev = (up_d - mavg) / mavg * Decimal("100")
            # Cap to fit Numeric(10,4): max abs value 999999.9999
            if dev > Decimal("999999"):
                dev = Decimal("999999")
            elif dev < Decimal("-999999"):
                dev = Decimal("-999999")
            await ctx.db.execute(text("""
                UPDATE procurement_closures
                SET market_avg = :mavg, deviation_pct = :dev
                WHERE id = :id
            """), {"mavg": float(mavg), "dev": float(dev), "id": row_id})
            updated += 1

        await ctx.db.flush()
        print(f"  ✓ procurement_closures benchmarks: median computed for "
              f"{len(medians)} (product_code,year) groups, "
              f"{updated} rows updated with market_avg/deviation_pct")
