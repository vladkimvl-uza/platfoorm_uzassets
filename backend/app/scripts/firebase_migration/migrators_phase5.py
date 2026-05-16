"""Phase 5 — structural migrators for executive-level dashboards.

Add Firebase → Postgres migrators for modules where Phase 4 was
JSONB-dump-only (raw_dumps) and Vue pages currently render empty:

  • BusinessPlanMigrator  /pf/businessPlan  → bp_records
  • KpiMigrator           /pf/kpi           → kpi_managers + kpi_indicators
  • EsgIssuesMigrator     /pf/esgIssues     → esg_issues
  • ProcurementMigrator   /pf/procurement   → procurement_data + procurement_contracts

All migrators:
  – Idempotent UPSERTs by deterministic keys (so re-running yields the same DB)
  – Lookup company_id by Company.code (case-insensitive, fallback to name)
  – Skip orphan records with detailed reason logging
  – Honour ctx.dry_run (count what WOULD happen, no DB writes)
  – Commit per-migrator (partial successes durable on partial failure)

Wiring:
  Append the four classes to ALL_MIGRATORS in `migrators.py` __after__
  RatingsMigrator (so companies/years are present), e.g.:

      from .migrators_phase5 import (
          BusinessPlanMigrator, KpiMigrator,
          EsgIssuesMigrator, ProcurementMigrator,
      )

      ALL_MIGRATORS = [
          ..., RatingsMigrator, GovernanceMigrator,
          BusinessPlanMigrator, KpiMigrator,
          EsgIssuesMigrator, ProcurementMigrator,
          RawDumpMigrator,
      ]

Run with --only to test one at a time:
  docker compose exec -e PYTHONPATH=/app backend python -m \
      app.scripts.firebase_migration.main --only bp --dry-run
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from sqlalchemy import select, delete

from app.models.company import Company
from app.models.bp_kpi import BpRecord, KpiManager, KpiIndicator
from app.models.esg import ESGIssue
from app.models.procurement import ProcurementData, ProcurementContract

from .base import Migrator, MigrationContext


log = logging.getLogger(__name__)


# =====================================================================
# Helpers
# =====================================================================

def _to_decimal(v: Any) -> Optional[Decimal]:
    """Coerce arbitrary Firebase value (str, int, float, None) to Decimal.
    Returns None for empty / unparseable inputs."""
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
        return int(float(v))  # tolerate "5.0" string
    except (ValueError, TypeError):
        return None


def _norm_dict(data: Any) -> dict[str, Any]:
    """Firebase may return a list (numeric-keyed) or dict — normalize to dict."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {str(i): v for i, v in enumerate(data) if v is not None}
    return {}


def _iter_records(data: Any) -> Iterable[dict[str, Any]]:
    """Yield record-shaped values from Firebase list-or-dict-or-list-of-dicts."""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, dict):
                yield v


async def _build_company_lookup(ctx: MigrationContext) -> dict[str, Company]:
    """Return a flat case-insensitive lookup of companies keyed by:
       - code (lowercase)        e.g. 'ngmk'
       - name_ru (normalized)    e.g. 'нгмк'
       - name_short              if present

    Firebase keys for /pf/businessPlan, /pf/kpi etc. are typically Russian
    short names ('НГМК', 'АГМК', 'Узбекуголь') — not codes — so we need
    name-based lookup as a fallback."""
    rows_q = await ctx.db.execute(select(Company))
    rows = rows_q.scalars().all()

    lookup: dict[str, Company] = {}
    for c in rows:
        if c.code:
            lookup[c.code.lower().strip()] = c
        if c.name_ru:
            lookup[c.name_ru.lower().strip()] = c
        # name_short / name_uz often used as Firebase keys
        for fld in ("name_short", "name_uz", "name_en"):
            v = getattr(c, fld, None)
            if v:
                lookup[v.lower().strip()] = c
    return lookup


def _resolve_company(co_key: str, lookup: dict[str, Company]) -> Optional[Company]:
    """Try several normalizations to match a Firebase company key to Company."""
    if not co_key:
        return None
    candidates = [
        co_key.lower().strip(),
        co_key.lower().strip().replace("ао ", "").replace("ао_", ""),
        co_key.lower().strip().replace(" ", ""),
    ]
    for c in candidates:
        hit = lookup.get(c)
        if hit:
            return hit
    return None


# =====================================================================
# 1. BusinessPlan migrator
# =====================================================================

# Allowed period keys per the monolith schema. Anything else is reported.
BP_PERIODS = {"annual", "q1", "q2", "q3", "q4"}

# Allowed metric keys per BP_FIELDS in the monolith.
BP_METRICS = {
    "revenue", "cogs", "grossProfit", "opExpenses", "sellExp", "adminExp",
    "otherOpExp", "otherOpInc", "opProfit",
    "finIncome", "divIncome", "intIncome", "fxIncome", "otherFinInc",
    "finCost", "intExp", "fxLoss", "otherFinExp",
    "hhProfit", "pbt", "tax", "profit",
}


class BusinessPlanMigrator(Migrator):
    """Migrate `/pf/businessPlan` → bp_records.

    Firebase shape (per monolith comment block):

      _db.businessPlan = {
        "<companyKey>": {
          "<year>": {
            "annual"|"q1"|"q2"|"q3"|"q4": {
              "<metricKey>": {plan: number|null, expect: number|null, fact: number|null}
            }
          }
        }
      }

    UPSERT key: (company_id, year, period, metric).
    """

    name = "bp"
    firebase_path = "/pf/businessPlan"

    async def apply(self, ctx: MigrationContext) -> None:
        data = ctx.fb.get(self.firebase_path)
        if not data:
            ctx.report.add_warning(f"{self.firebase_path}: empty in Firebase")
            return

        if not isinstance(data, dict):
            ctx.report.add_warning(f"{self.firebase_path}: expected dict, got {type(data).__name__}")
            return

        lookup = await _build_company_lookup(ctx)

        created = 0
        updated = 0
        skipped_orphan = 0
        skipped_bad = 0
        unknown_periods: set[str] = set()
        unknown_metrics: set[str] = set()

        for co_key, by_year in data.items():
            if co_key.startswith("_"):  # _meta etc.
                continue
            if not isinstance(by_year, dict):
                continue

            company = _resolve_company(co_key, lookup)
            if not company:
                skipped_orphan += 1
                ctx.report.add_skip("bp", f"company '{co_key}' not in PG")
                continue

            for year_str, by_period in by_year.items():
                year = _to_int(year_str)
                if not year or year < 2000 or year > 2100:
                    skipped_bad += 1
                    continue
                if not isinstance(by_period, dict):
                    continue

                for period, metrics in by_period.items():
                    if period not in BP_PERIODS:
                        unknown_periods.add(period)
                        continue
                    if not isinstance(metrics, dict):
                        continue

                    for metric, vals in metrics.items():
                        if metric not in BP_METRICS:
                            unknown_metrics.add(metric)
                            continue
                        if not isinstance(vals, dict):
                            continue

                        plan   = _to_decimal(vals.get("plan"))
                        expect = _to_decimal(vals.get("expect"))
                        fact   = _to_decimal(vals.get("fact"))

                        # Skip if all three are None (avoid empty rows)
                        if plan is None and expect is None and fact is None:
                            continue

                        existing_q = await ctx.db.execute(
                            select(BpRecord).where(
                                BpRecord.company_id == company.id,
                                BpRecord.year == year,
                                BpRecord.period == period,
                                BpRecord.metric == metric,
                            )
                        )
                        existing = existing_q.scalar_one_or_none()

                        if ctx.dry_run:
                            if existing:
                                updated += 1
                                ctx.report.add_update("bp")
                            else:
                                created += 1
                                ctx.report.add_create("bp")
                            continue

                        if existing:
                            existing.plan = plan
                            existing.expect = expect
                            existing.fact = fact
                            updated += 1
                            ctx.report.add_update("bp")
                        else:
                            ctx.db.add(BpRecord(
                                company_id=company.id,
                                year=year,
                                period=period,
                                metric=metric,
                                plan=plan,
                                expect=expect,
                                fact=fact,
                            ))
                            created += 1
                            ctx.report.add_create("bp")

        if not ctx.dry_run:
            await ctx.db.flush()

        print(f"  ✓ bp: {created} created, {updated} updated, "
              f"{skipped_orphan} orphan-company, {skipped_bad} bad-year")
        if unknown_periods:
            ctx.report.add_warning(f"bp/unknown-periods: {sorted(unknown_periods)[:10]}")
        if unknown_metrics:
            ctx.report.add_warning(f"bp/unknown-metrics: {sorted(unknown_metrics)[:10]}")


# =====================================================================
# 2. KPI migrator
# =====================================================================

class KpiMigrator(Migrator):
    """Migrate `/pf/kpi` → kpi_managers + kpi_indicators.

    Firebase shape (per monolith):

      _db.kpi = {
        "<companyKey>": {
          "<year>": {
            "managers": [
              {
                name, weight, role?, shortTitle?,
                indicators: [
                  {name, unit, weight,
                   plan, fact, q1Plan, q1Fact, q2Plan, q2Fact, q3Plan, q3Fact, q4Plan, q4Fact,
                   q1Weight?, q2Weight?, q3Weight?, q4Weight?}
                ]
              }
            ]
          }
        }
      }

    Strategy: for each (company, year), DELETE all existing managers + indicators
    (cascade) and re-insert. Since this is keyed by index/title and the editor
    rewrites the whole tree on save, full-rewrite is the only consistent
    semantic. Less elegant than UPSERT but safer.
    """

    name = "kpi"
    firebase_path = "/pf/kpi"

    async def apply(self, ctx: MigrationContext) -> None:
        data = ctx.fb.get(self.firebase_path)
        if not data:
            ctx.report.add_warning(f"{self.firebase_path}: empty in Firebase")
            return
        if not isinstance(data, dict):
            ctx.report.add_warning(f"{self.firebase_path}: expected dict, got {type(data).__name__}")
            return

        lookup = await _build_company_lookup(ctx)

        managers_created = 0
        indicators_created = 0
        co_year_processed = 0
        skipped_orphan = 0

        for co_key, by_year in data.items():
            if co_key.startswith("_"):
                continue
            if not isinstance(by_year, dict):
                continue

            company = _resolve_company(co_key, lookup)
            if not company:
                skipped_orphan += 1
                ctx.report.add_skip("kpi", f"company '{co_key}' not in PG")
                continue

            for year_str, payload in by_year.items():
                year = _to_int(year_str)
                if not year or year < 2000 or year > 2100:
                    continue
                if not isinstance(payload, dict):
                    continue

                managers = payload.get("managers", [])
                if not isinstance(managers, list):
                    # Sometimes serialized as numeric-keyed dict
                    managers = list(_iter_records(managers))
                if not managers:
                    continue

                co_year_processed += 1

                if not ctx.dry_run:
                    # Wipe existing for (company, year). Cascade deletes indicators.
                    await ctx.db.execute(
                        delete(KpiManager).where(
                            KpiManager.company_id == company.id,
                            KpiManager.year == year,
                        )
                    )
                    await ctx.db.flush()

                for m_idx, mgr_data in enumerate(managers):
                    if not isinstance(mgr_data, dict):
                        continue
                    title = (mgr_data.get("title") or mgr_data.get("name") or "").strip()
                    if not title:
                        role_v = (mgr_data.get("role") or "").strip()
                        person_v = (mgr_data.get("person") or "").strip()
                        if role_v and person_v:
                            title = role_v + " (" + person_v + ")"
                        elif role_v:
                            title = role_v
                        elif person_v:
                            title = person_v
                    if not title:
                        continue
                    short_title = (mgr_data.get("shortTitle") or mgr_data.get("short") or "").strip() or None
                    role = (mgr_data.get("role") or "").strip() or None

                    if ctx.dry_run:
                        managers_created += 1
                        ctx.report.add_create("kpi")
                        # Count indicators we WOULD insert
                        inds = mgr_data.get("indicators", [])
                        if isinstance(inds, dict):
                            inds = list(_iter_records(inds))
                        if isinstance(inds, list):
                            indicators_created += sum(1 for i in inds if isinstance(i, dict) and (i.get("name") or "").strip())
                        continue

                    mgr = KpiManager(
                        company_id=company.id,
                        year=year,
                        sort_order=m_idx,
                        title=title,
                        short_title=short_title,
                        role=role,
                    )
                    ctx.db.add(mgr)
                    await ctx.db.flush()  # to get mgr.id
                    managers_created += 1
                    ctx.report.add_create("kpi")

                    inds = mgr_data.get("indicators", [])
                    if isinstance(inds, dict):
                        inds = list(_iter_records(inds))
                    if not isinstance(inds, list):
                        continue

                    for i_idx, ind_data in enumerate(inds):
                        if not isinstance(ind_data, dict):
                            continue
                        name = (ind_data.get("name") or "").strip()
                        if not name:
                            continue

                        ind = KpiIndicator(
                            manager_id=mgr.id,
                            sort_order=i_idx,
                            name=name,
                            unit=(ind_data.get("unit") or "").strip()[:64] or None,
                            weight=_to_decimal(ind_data.get("weight")) or Decimal("0"),
                            plan_year=_to_decimal(ind_data.get("planYear") or ind_data.get("plan")),
                            fact_year=_to_decimal(ind_data.get("factYear") or ind_data.get("fact")),
                            q1_weight=_to_decimal((ind_data.get("quarters") or {}).get("q1", {}).get("weight")) or Decimal("0"),
                            q2_weight=_to_decimal((ind_data.get("quarters") or {}).get("q2", {}).get("weight")) or Decimal("0"),
                            q3_weight=_to_decimal((ind_data.get("quarters") or {}).get("q3", {}).get("weight")) or Decimal("0"),
                            q4_weight=_to_decimal((ind_data.get("quarters") or {}).get("q4", {}).get("weight")) or Decimal("0"),
                            q1_plan=_to_decimal((ind_data.get("quarters") or {}).get("q1", {}).get("plan")),
                            q2_plan=_to_decimal((ind_data.get("quarters") or {}).get("q2", {}).get("plan")),
                            q3_plan=_to_decimal((ind_data.get("quarters") or {}).get("q3", {}).get("plan")),
                            q4_plan=_to_decimal((ind_data.get("quarters") or {}).get("q4", {}).get("plan")),
                            q1_fact=_to_decimal((ind_data.get("quarters") or {}).get("q1", {}).get("fact")),
                            q2_fact=_to_decimal((ind_data.get("quarters") or {}).get("q2", {}).get("fact")),
                            q3_fact=_to_decimal((ind_data.get("quarters") or {}).get("q3", {}).get("fact")),
                            q4_fact=_to_decimal((ind_data.get("quarters") or {}).get("q4", {}).get("fact")),
                        )
                        ctx.db.add(ind)
                        indicators_created += 1

        if not ctx.dry_run:
            await ctx.db.flush()

        print(f"  ✓ kpi: {co_year_processed} (company×year) processed, "
              f"{managers_created} managers, {indicators_created} indicators, "
              f"{skipped_orphan} orphan-company")


# =====================================================================
# 3. ESG Issues migrator (lightweight — issues only)
# =====================================================================

class EsgIssuesMigrator(Migrator):
    """Migrate `/pf/esgIssues` → esg_issues.

    Firebase shape: a flat list/dict of issue records, each with at least
    {company, pillar (E|S|G), title, description, severity, status}.

    The exact schema is not documented in the monolith comment header — this
    migrator handles missing fields gracefully and dumps unrecognised keys
    into `extra` JSONB for AI context.

    Note: `esg_metrics` is NOT migrated here — in the monolith those are
    computed on-the-fly from financials/ratings rather than persisted as a
    separate FB tree. If you have a /pf/esgMetrics tree, write a separate
    migrator following the BP pattern.
    """

    name = "esg_issues"
    firebase_path = "/pf/esgIssues"

    async def apply(self, ctx: MigrationContext) -> None:
        data = ctx.fb.get(self.firebase_path)
        if not data:
            ctx.report.add_warning(f"{self.firebase_path}: empty in Firebase")
            return

        lookup = await _build_company_lookup(ctx)

        created = 0
        updated = 0
        skipped_orphan = 0

        # ESG issues are usually a flat list, but tolerate dict-keyed shapes
        for rec in _iter_records(data):
            co_key = (rec.get("company") or rec.get("companyKey") or rec.get("co") or "").strip()
            company = _resolve_company(co_key, lookup) if co_key else None
            if not company:
                skipped_orphan += 1
                ctx.report.add_skip("esg_issues", f"company '{co_key}' not in PG")
                continue

            pillar = (rec.get("pillar") or rec.get("category") or "G").upper()[:8]
            if pillar not in ("E", "S", "G"):
                pillar = "G"

            title = (rec.get("title") or rec.get("name") or "").strip()
            if not title:
                continue

            description = (rec.get("description") or rec.get("body") or "").strip() or None
            severity = (rec.get("severity") or "med").lower().strip()[:16] or "med"
            status = (rec.get("status") or "open").lower().strip()[:32] or "open"

            # Idempotency: dedupe by (company, pillar, title)
            existing_q = await ctx.db.execute(
                select(ESGIssue).where(
                    ESGIssue.company_id == company.id,
                    ESGIssue.pillar == pillar,
                    ESGIssue.title == title,
                )
            )
            existing = existing_q.scalar_one_or_none()

            if ctx.dry_run:
                if existing:
                    updated += 1; ctx.report.add_update("esg_issues")
                else:
                    created += 1; ctx.report.add_create("esg_issues")
                continue

            if existing:
                existing.description = description
                existing.severity = severity
                existing.status = status
                existing.extra = dict(rec)
                updated += 1
                ctx.report.add_update("esg_issues")
            else:
                ctx.db.add(ESGIssue(
                    company_id=company.id,
                    pillar=pillar,
                    title=title[:512],
                    description=description,
                    severity=severity,
                    status=status,
                    extra=dict(rec),
                ))
                created += 1
                ctx.report.add_create("esg_issues")

        if not ctx.dry_run:
            await ctx.db.flush()

        print(f"  ✓ esg_issues: {created} created, {updated} updated, "
              f"{skipped_orphan} orphan-company")


# =====================================================================
# 4. Procurement migrator (lightweight — purchases only)
# =====================================================================

class ProcurementMigrator(Migrator):
    """Migrate `/pf/procurement` → procurement_data + procurement_contracts.

    Firebase shape (per monolith paGetYearData):

      _db.procurement = {
        "years": {
          "<year>": {
            "marketAvg": {<categoryId>: {price: <number>}},   # benchmarks (separate tree handles these)
            "purchases": [
              {contractNo, supplier, supplierInn?, productCode?, productName?,
               quantity?, unit?, unitPrice?, totalAmount?,
               company (key), year, closureDate?}
            ]
          }
        }
      }

    Each `purchases[]` row creates a `procurement_data` entry. We dedupe by
    (company_id, contract_no, product_code, year) — this is the closest
    natural key without a Firebase ID.

    NB: `marketAvg`, contracts metadata, and benchmarks are NOT covered here.
    Those tend to be computed from purchases by paCompute() in the monolith;
    on the Vue side they should be derived likewise. If a separate FB tree
    `/pf/procurementBenchmark` exists with persisted benchmarks — add a
    sibling migrator following GovernanceMigrator pattern.
    """

    name = "procurement"
    firebase_path = "/pf/procurement"

    async def apply(self, ctx: MigrationContext) -> None:
        data = ctx.fb.get(self.firebase_path)
        if not data:
            ctx.report.add_warning(f"{self.firebase_path}: empty in Firebase")
            return
        if not isinstance(data, dict):
            ctx.report.add_warning(f"{self.firebase_path}: expected dict, got {type(data).__name__}")
            return

        lookup = await _build_company_lookup(ctx)

        years = data.get("years") or {}
        if not isinstance(years, dict):
            ctx.report.add_warning("procurement: 'years' is not a dict")
            return

        created = 0
        updated = 0
        skipped_orphan = 0
        skipped_bad = 0

        for year_str, year_data in years.items():
            year = _to_int(year_str)
            if not year or year < 2000 or year > 2100:
                skipped_bad += 1
                continue
            if not isinstance(year_data, dict):
                continue

            purchases = year_data.get("purchases") or []
            if not isinstance(purchases, list):
                purchases = list(_iter_records(purchases))

            for p in purchases:
                if not isinstance(p, dict):
                    continue

                co_key = (p.get("company") or p.get("co") or "").strip()
                company = _resolve_company(co_key, lookup) if co_key else None
                if not company:
                    skipped_orphan += 1
                    ctx.report.add_skip("procurement", f"company '{co_key}' not in PG")
                    continue

                contract_no = (p.get("contractNo") or p.get("contract") or "").strip() or None
                product_code = (p.get("productCode") or p.get("category") or "").strip() or None
                product_name = (p.get("productName") or p.get("product") or "").strip() or None

                quantity = _to_decimal(p.get("quantity") or p.get("qty"))
                unit = (p.get("unit") or "").strip()[:32] or None
                unit_price = _to_decimal(p.get("unitPrice") or p.get("price"))
                total_amount = _to_decimal(p.get("totalAmount") or p.get("total") or p.get("amount"))

                supplier_name = (p.get("supplier") or p.get("supplierName") or "").strip()[:512] or None
                supplier_inn = (p.get("supplierInn") or p.get("inn") or "").strip()[:32] or None

                # Dedup key: (company, contract_no, product_code, year)
                # If contract_no missing, fall back to (company, product_code, year, supplier).
                where_clauses = [
                    ProcurementData.company_id == company.id,
                    ProcurementData.year == year,
                    ProcurementData.product_code == product_code,
                ]
                if contract_no:
                    where_clauses.append(ProcurementData.extra["contract_no"].astext == contract_no)
                else:
                    where_clauses.append(ProcurementData.supplier_name == supplier_name)

                existing_q = await ctx.db.execute(
                    select(ProcurementData).where(*where_clauses).limit(1)
                )
                existing = existing_q.scalar_one_or_none()

                extra = dict(p)
                if contract_no:
                    extra.setdefault("contract_no", contract_no)

                if ctx.dry_run:
                    if existing:
                        updated += 1; ctx.report.add_update("procurement")
                    else:
                        created += 1; ctx.report.add_create("procurement")
                    continue

                if existing:
                    existing.quantity = quantity
                    existing.unit_price = unit_price
                    existing.total_amount = total_amount
                    existing.supplier_name = supplier_name
                    existing.supplier_inn = supplier_inn
                    existing.product_name = product_name[:1024] if product_name else None
                    existing.unit = unit
                    existing.extra = extra
                    updated += 1
                    ctx.report.add_update("procurement")
                else:
                    ctx.db.add(ProcurementData(
                        company_id=company.id,
                        year=year,
                        product_code=product_code,
                        product_name=product_name[:1024] if product_name else None,
                        quantity=quantity,
                        unit=unit,
                        unit_price=unit_price,
                        total_amount=total_amount,
                        supplier_name=supplier_name,
                        supplier_inn=supplier_inn,
                        is_dirty=False,
                        extra=extra,
                    ))
                    created += 1
                    ctx.report.add_create("procurement")

        if not ctx.dry_run:
            await ctx.db.flush()

        print(f"  ✓ procurement: {created} created, {updated} updated, "
              f"{skipped_orphan} orphan-company, {skipped_bad} bad-year")
