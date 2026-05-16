"""Concrete Firebase migrators.

Order is important — companies must be migrated first because financials,
ratings, KPI, etc. all reference companies by `code`.

Each migrator:
  1. Fetches data from Firebase (read-only)
  2. Normalizes Firebase quirks (array-as-object, missing fields)
  3. UPSERTs into Postgres with deterministic keys (idempotent)
  4. Reports created / updated / skipped counts
  5. In dry_run mode, only logs what it WOULD do — no DB writes
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.company import Company, Sector
from app.models.financial import FinancialReport, FinancialLine
from app.models.announcement import Announcement
from app.models.year_registry import YearRegistry

from .base import (
    Migrator, MigrationContext,
    normalize_array, safe_str, safe_int, safe_decimal,
)

log = logging.getLogger(__name__)


# =====================================================================
# COMPANIES — /pf/customCompanies
# =====================================================================

class CompaniesMigrator(Migrator):
    """Migrate `/pf/customCompanies` → `companies` table.

    Firebase shape (per second sample we saw):
      list of {abbr, color, name, sector}
    """

    name = "companies"
    firebase_path = "/pf/customCompanies"

    async def apply(self, ctx: MigrationContext) -> None:
        raw = ctx.fb.get(self.firebase_path)
        items = normalize_array(raw)

        if not items:
            ctx.report.add_warning("/pf/customCompanies — пусто или не существует")
            return

        # Build a sector code → id map for FK lookup
        sector_result = await ctx.db.execute(select(Sector))
        sectors_by_name = {s.name_ru.lower().strip(): s for s in sector_result.scalars().all()}
        sectors_by_code = {s.code: s for s in sectors_by_name.values()}

        for item in items:
            if not isinstance(item, dict):
                ctx.report.add_skip("companies", f"non-object item: {type(item).__name__}")
                continue

            abbr = safe_str(item.get("abbr"), 16)
            name = safe_str(item.get("name"), 255)
            if not abbr or not name:
                ctx.report.add_skip("companies", f"missing abbr/name: {item}")
                continue

            code = abbr.lower()  # use abbr as deterministic code
            color_hex = safe_str(item.get("color"), 9)
            sector_name = safe_str(item.get("sector"), 255)

            sector_id = None
            if sector_name:
                # try by code first, then by Russian name
                s = sectors_by_code.get(sector_name.lower()) or sectors_by_name.get(sector_name.lower())
                if s:
                    sector_id = s.id
                else:
                    ctx.report.add_warning(
                        f"companies/{abbr}: sector '{sector_name}' не найден в Postgres — оставляю NULL"
                    )

            extra = {k: v for k, v in item.items() if k not in {"abbr", "name", "sector", "color"}}

            # Upsert: try update, else insert
            existing_q = await ctx.db.execute(
                select(Company).where(Company.code == code)
            )
            existing = existing_q.scalar_one_or_none()

            if existing:
                if ctx.dry_run:
                    ctx.report.add_update("companies")
                    log.info("DRY-RUN  companies UPDATE  code=%s name='%s'", code, name)
                else:
                    existing.name_ru = name
                    existing.name_short = abbr.upper()
                    if sector_id:
                        existing.sector_id = sector_id
                    if color_hex:
                        if existing.extra is None:
                            existing.extra = {}
                        existing.extra = {**(existing.extra or {}), "color_hex": color_hex, **extra}
                    existing.is_custom = True
                    ctx.report.add_update("companies")
            else:
                if ctx.dry_run:
                    ctx.report.add_create("companies")
                    log.info("DRY-RUN  companies CREATE  code=%s name='%s'", code, name)
                else:
                    company = Company(
                        code=code,
                        name_ru=name,
                        name_short=abbr.upper(),
                        sector_id=sector_id,
                        is_active=True,
                        is_custom=True,
                        sort_order=0,
                        extra={"color_hex": color_hex, **extra} if color_hex or extra else None,
                    )
                    ctx.db.add(company)
                    ctx.report.add_create("companies")

        if not ctx.dry_run:
            await ctx.db.flush()


# =====================================================================
# FINANCIALS — /financials/{company_code}
# =====================================================================

class FinancialsMigrator(Migrator):
    """Migrate `/financials/{company_code}` → financial_reports + financial_lines.

    Firebase shape per company:
      {
        name, lastUpdated, source, notes,
        years: [2022, 2023, 2024, 2025],
        revenue: [120, 145, 167, 210],   # parallel arrays per year
        cogs: [...], grossProfit: [...], opProfit: [...],
        ... (33 line codes total)
      }

    Two parallel datasets share the `/financials` path:
      /financials/{co}                — IFRS data
      /financials/__nsbu_{co}         — NSBU data (prefix-distinguished)

    Each (company, year, standard) produces UP TO 3 reports of types PL / BS / CF
    based on which line codes have data. Line codes are mapped to report types
    via the catalog file (`data/seed/financial_lines_catalog.json`).
    """

    name = "financials"
    firebase_path = "/financials"

    @staticmethod
    def _load_catalog() -> dict:
        """Load financial_lines_catalog.json → {code: catalog_entry}."""
        import json
        from pathlib import Path
        catalog_path = (Path(__file__).resolve().parents[3]
                        / "data" / "seed" / "financial_lines_catalog.json")
        if not catalog_path.exists():
            return {}
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        return {entry["code"]: entry for entry in raw}

    async def apply(self, ctx: MigrationContext) -> None:
        from app.models.financial import FinancialReport, FinancialLine

        catalog = self._load_catalog()
        if not catalog:
            # Catalog is now optional — used only for friendly line names and
            # report_type assignment. Migration proceeds with raw codes when
            # the catalog file is missing.
            ctx.report.add_warning(
                "financial_lines_catalog.json missing — line names will fall back to raw codes"
            )
            catalog = {}

        all_keys = ctx.fb.shallow_keys(self.firebase_path)
        # Skip _meta and similar — but KEEP __nsbu_* keys (they hold NSBU data!)
        all_keys = [k for k in all_keys if not (k.startswith("_") and not k.startswith("__nsbu_"))]

        # Build a multi-form lookup index. Firebase stores companies under
        # human-readable Russian/Latin names that may match name_short, name_ru,
        # name_ru-without-АО-prefix, or code. We index ALL these forms,
        # case-insensitively, so any Firebase key resolves to the right
        # Postgres company row.
        comp_result = await ctx.db.execute(select(Company))
        all_companies = list(comp_result.scalars().all())

        company_by_code: dict[str, Company] = {c.code: c for c in all_companies}
        company_lookup: dict[str, Company] = {}

        def _strip_legal_form(s: str) -> str:
            """`АО «Навоийский ГМК»` → `Навоийский ГМК`. Helps match Firebase
            keys which often omit the legal form prefix and quotes."""
            s = s.strip()
            for prefix in ("АО «", "АО \"", "ГП «", "ГП \"", "АО ", "ГП ", 'JSC ', 'SE '):
                if s.startswith(prefix):
                    s = s[len(prefix):].strip()
            for suffix in ("»", "\"", "» ", " JSC", " State Enterprise"):
                if s.endswith(suffix):
                    s = s[:-len(suffix)].strip()
            return s

        for c in all_companies:
            forms = []
            if c.code:       forms.append(c.code)
            if c.name_short: forms.append(c.name_short)
            if c.name_ru:    forms.append(c.name_ru)
            if c.name_ru:    forms.append(_strip_legal_form(c.name_ru))
            if c.name_en:    forms.append(c.name_en)
            if c.name_en:    forms.append(_strip_legal_form(c.name_en))
            if c.name_uz:    forms.append(_strip_legal_form(c.name_uz))
            for f in forms:
                if not f:
                    continue
                key = f.strip().lower()
                if key and key not in company_lookup:
                    company_lookup[key] = c

        # Counters
        reports_created = 0
        reports_updated = 0
        lines_created = 0
        skipped_orphan = 0
        first_errors: list[str] = []
        unmatched_keys: list[str] = []   # Firebase keys we couldn't map to any company

        for raw_key in all_keys:
            try:
                # Detect NSBU prefix
                is_nsbu = raw_key.startswith("__nsbu_")
                standard = "NSBU" if is_nsbu else "IFRS"
                company_key = raw_key[len("__nsbu_"):] if is_nsbu else raw_key

                data = ctx.fb.get(f"{self.firebase_path}/{raw_key}")
                if not isinstance(data, dict):
                    ctx.report.add_skip("financials", f"{raw_key}: non-object data")
                    continue

                # Resolve company: try unified multi-form lookup
                company = company_lookup.get(company_key.strip().lower())

                # If still no match — log and SKIP (don't create stub).
                # Stubs cause more confusion than they solve: a company appears
                # in the list with an unfamiliar slug, has no sector, no metadata.
                # Better to log loudly so the operator can rename the Firebase
                # key OR add the company to the canonical seed.
                if not company:
                    unmatched_keys.append(raw_key)
                    ctx.report.add_skip("financials", f"{raw_key}: no matching company in canonical list (skipped)")
                    continue

                # Years array — parallel index for all line codes
                years_raw = normalize_array(data.get("years"))
                years = [safe_int(y) for y in years_raw if safe_int(y)]
                years = [y for y in years if y and 2000 <= y <= 2100]
                if not years:
                    ctx.report.add_skip("financials", f"{raw_key}: no valid years")
                    continue

                # source/notes/unit
                source = safe_str(data.get("source"), 32) or standard.lower()
                notes  = safe_str(data.get("notes"), 4096)
                unit_scale = safe_int(data.get("unitScale")) or 1000  # monolith default = thousand sum

                # ── Discover ALL line codes present in this Firebase entry ──
                # Previously: only catalog codes → unrecognised fields silently
                # dropped. Now: every top-level array/dict field becomes a
                # candidate line. This guarantees nothing the user entered in
                # the monolith editor is lost on import. The catalog is only
                # consulted for friendly naming + report_type assignment.
                META_FIELDS = {
                    "name", "source", "years", "lastUpdated", "_note", "_meta",
                    "unitScale", "currency", "notes", "status",
                }
                lines_data: dict[str, list] = {}
                for fkey, fval in data.items():
                    if fkey in META_FIELDS:
                        continue
                    if not isinstance(fval, (list, dict)):
                        # Top-level scalar (rare) — skip; not a line series
                        continue
                    arr = normalize_array(fval)
                    # Keep series even if all values null — caller may want
                    # the structure. But skip purely empty lists.
                    if not arr:
                        continue
                    lines_data[fkey] = arr

                if not lines_data:
                    ctx.report.add_skip("financials", f"{raw_key}: no line series in data")
                    continue

                # Group line codes by report_type (PL / BS / CF). Codes outside
                # the catalog default to PL (most common in monolith P&L editor)
                # and can be moved later via UI if mis-classified.
                codes_by_rtype: dict[str, list[str]] = {"PL": [], "BS": [], "CF": []}
                for code in lines_data.keys():
                    rtype = (catalog.get(code, {}) or {}).get("report_type") or "PL"
                    if rtype not in codes_by_rtype:
                        rtype = "PL"
                    codes_by_rtype[rtype].append(code)

                # For each (year, report_type) combo where we have data — upsert report + lines
                for year in years:
                    year_idx = years.index(year)

                    for rtype, codes in codes_by_rtype.items():
                        if not codes:
                            continue

                        # Check if at least one code has a non-null value for this year
                        has_any = False
                        for code in codes:
                            arr = lines_data.get(code, [])
                            if year_idx < len(arr) and arr[year_idx] is not None:
                                has_any = True
                                break
                        if not has_any:
                            continue

                        # Upsert report
                        existing_q = await ctx.db.execute(
                            select(FinancialReport).where(
                                FinancialReport.company_id == company.id,
                                FinancialReport.year == year,
                                FinancialReport.standard == standard,
                                FinancialReport.report_type == rtype,
                                FinancialReport.quarter.is_(None),
                            )
                        )
                        report_obj = existing_q.scalar_one_or_none()

                        if report_obj:
                            if not ctx.dry_run:
                                report_obj.source = source
                                report_obj.unit_scale = unit_scale
                                if notes:
                                    report_obj.notes = notes
                            reports_updated += 1
                            ctx.report.add_update("financial_reports")
                        else:
                            if ctx.dry_run:
                                reports_created += 1
                                ctx.report.add_create("financial_reports")
                                continue
                            report_obj = FinancialReport(
                                company_id=company.id,
                                year=year, quarter=None,
                                standard=standard, report_type=rtype,
                                currency="UZS", unit_scale=unit_scale,
                                source=source, notes=notes,
                                extra={"firebase_data_key": raw_key},
                            )
                            ctx.db.add(report_obj)
                            await ctx.db.flush()
                            reports_created += 1
                            ctx.report.add_create("financial_reports")

                        # Wipe existing lines for this report (idempotent re-import)
                        if not ctx.dry_run:
                            await ctx.db.execute(
                                delete(FinancialLine).where(
                                    FinancialLine.report_id == report_obj.id
                                )
                            )

                        # Add lines for each code that has a value this year
                        for code in codes:
                            arr = lines_data.get(code, [])
                            if year_idx >= len(arr):
                                continue
                            val = arr[year_idx]
                            if val is None:
                                continue
                            dec_val = safe_decimal(val)
                            if dec_val is None:
                                continue

                            entry = catalog.get(code, {}) or {}
                            # Friendly name: catalog if present, else fall back
                            # to the raw code (operator can rename in UI later).
                            line_name    = entry.get("name_ru") or code
                            line_name_en = entry.get("name_en")
                            parent_code  = entry.get("parent_code")
                            is_subtotal  = bool(entry.get("is_subtotal", False))
                            sort_order   = int(entry.get("sort_order", 0))

                            if not ctx.dry_run:
                                ctx.db.add(FinancialLine(
                                    report_id=report_obj.id,
                                    line_code=code,
                                    line_name=line_name,
                                    line_name_en=line_name_en,
                                    parent_code=parent_code,
                                    value=dec_val,
                                    is_subtotal=is_subtotal,
                                    is_calculated=False,
                                    sort_order=sort_order,
                                ))
                            lines_created += 1
                            ctx.report.add_create("financial_lines")

                # Commit per company to isolate failures
                if not ctx.dry_run:
                    try:
                        await ctx.db.flush()
                        await ctx.db.commit()
                    except Exception as commit_err:
                        await ctx.db.rollback()
                        if len(first_errors) < 5:
                            first_errors.append(
                                f"{raw_key}: commit failed: "
                                f"{type(commit_err).__name__}: {str(commit_err)[:140]}"
                            )

            except Exception as e:
                if len(first_errors) < 5:
                    first_errors.append(
                        f"{raw_key}: {type(e).__name__}: {str(e)[:140]}"
                    )
                if not ctx.dry_run:
                    try: await ctx.db.rollback()
                    except: pass

        print(f"  ✓ financials: {reports_created} reports created, "
              f"{reports_updated} updated, {lines_created} lines, "
              f"{skipped_orphan} orphans, {len(unmatched_keys)} unmatched company keys")
        if unmatched_keys:
            print(f"  ⚠ {len(unmatched_keys)} Firebase key(s) could not be matched to any company:")
            for k in unmatched_keys[:15]:
                print(f"     · {k!r}")
            if len(unmatched_keys) > 15:
                print(f"     · ... ({len(unmatched_keys) - 15} more)")
            print(f"     ─ tip: rename the Firebase key OR add the company to canonical seed (migration 0010)")
        if first_errors:
            print(f"  ⚠ first {len(first_errors)} error(s):")
            for err in first_errors:
                print(f"     · {err}")

    async def _upsert_line(self, ctx, report_id, line_code: str, line_name: str, value: Decimal, sort: int) -> None:
        """[Legacy method, kept for backwards compat — new code uses bulk INSERT.]"""
        existing_q = await ctx.db.execute(
            select(FinancialLine).where(
                FinancialLine.report_id == report_id,
                FinancialLine.line_code == line_code,
            )
        )
        line = existing_q.scalar_one_or_none()
        if line:
            line.value = value
            ctx.report.add_update("financial_lines")
        else:
            ctx.db.add(FinancialLine(
                report_id=report_id,
                line_code=line_code,
                line_name=line_name,
                value=value,
                sort_order=sort,
            ))
            ctx.report.add_create("financial_lines")


# =====================================================================
# ANNOUNCEMENTS — /pf/announcements/ann_*
# =====================================================================

class AnnouncementsMigrator(Migrator):
    """Migrate `/pf/announcements/ann_*` → `announcements` table.

    Firebase shape:
      {id, title, body, author, priority, createdAt (ms timestamp)}
    """

    name = "announcements"
    firebase_path = "/pf/announcements"

    async def apply(self, ctx: MigrationContext) -> None:
        keys = ctx.fb.shallow_keys(self.firebase_path)
        if not keys:
            ctx.report.add_warning(f"{self.firebase_path} пуст")
            return

        for k in keys:
            data = ctx.fb.get(f"{self.firebase_path}/{k}")
            if not isinstance(data, dict):
                ctx.report.add_skip("announcements", f"{k}: not an object")
                continue

            firebase_id = safe_str(data.get("id"), 128) or k
            title = safe_str(data.get("title"), 255)
            body = safe_str(data.get("body"), 65535)
            priority = safe_str(data.get("priority"), 32) or "normal"

            if not title and not body:
                ctx.report.add_skip("announcements", f"{k}: empty title and body")
                continue

            created_at_ms = data.get("createdAt")
            if isinstance(created_at_ms, (int, float)):
                created_dt = datetime.fromtimestamp(created_at_ms / 1000.0, tz=timezone.utc)
            else:
                created_dt = datetime.now(tz=timezone.utc)

            existing_q = await ctx.db.execute(
                select(Announcement).where(
                    Announcement.extra["firebase_id"].astext == firebase_id
                )
            )
            existing = existing_q.scalar_one_or_none()

            if existing:
                if ctx.dry_run:
                    ctx.report.add_update("announcements")
                else:
                    existing.title = title or existing.title
                    existing.body = body or existing.body
                    existing.severity = priority
                    ctx.report.add_update("announcements")
            else:
                if ctx.dry_run:
                    ctx.report.add_create("announcements")
                else:
                    ann = Announcement(
                        title=title or "(без заголовка)",
                        body=body or "",
                        severity=priority,
                        publish_at=created_dt,
                        is_published=True,
                        extra={
                            "firebase_id": firebase_id,
                            "firebase_author": safe_str(data.get("author"), 128),
                        },
                    )
                    ctx.db.add(ann)
                    ctx.report.add_create("announcements")

        if not ctx.dry_run:
            await ctx.db.flush()


# =====================================================================
# YEAR REGISTRIES — /pf/esgYearsTracked, /pf/ratingsYearsTracked
# =====================================================================

class YearRegistryMigrator(Migrator):
    """Migrate year registries → year_registry table."""

    name = "years"
    firebase_path = "/pf"  # parent

    async def apply(self, ctx: MigrationContext) -> None:
        years_to_add: set[int] = set()
        for fb_key in ["esgYearsTracked", "ratingsYearsTracked"]:
            data = ctx.fb.get(f"/pf/{fb_key}")
            years = []
            if isinstance(data, list):
                years = data
            elif isinstance(data, dict):
                years = list(data.values()) if all(str(k).isdigit() for k in data.keys()) else []
                if not years:
                    if "years" in data:
                        years = normalize_array(data["years"])
                    else:
                        years = [int(k) for k in data.keys() if str(k).isdigit()]

            for y in years:
                year_int = safe_int(y)
                if year_int and 2000 <= year_int <= 2100:
                    years_to_add.add(year_int)

        # Upsert each year (year is unique)
        for year_int in sorted(years_to_add):
            existing_q = await ctx.db.execute(
                select(YearRegistry).where(YearRegistry.year == year_int)
            )
            if existing_q.scalar_one_or_none():
                ctx.report.add_skip("year_registry", f"{year_int} already exists")
                continue
            if ctx.dry_run:
                ctx.report.add_create("year_registry")
            else:
                ctx.db.add(YearRegistry(year=year_int, label=str(year_int)))
                ctx.report.add_create("year_registry")

        if not ctx.dry_run:
            await ctx.db.flush()


# =====================================================================
# RAW JSON DUMP — /pf/{governanceData,procurementData,...} as backup
# =====================================================================

class RawDumpMigrator(Migrator):
    """For data domains where the Firebase shape is too complex to map cleanly,
    dump the JSON to system_config so it's available for later structured migration."""

    name = "raw_dumps"
    firebase_path = "/pf"

    DUMP_KEYS = [
        "governanceData",
        "procurementData",
        "procurementContracts",
        "procurementBenchmark",
        "credit",
        "creditPortfolio",
        "finModel",
        "kpi",
        # NB: 'ratings' is now in the agency_ratings table (RatingsMigrator).
        "businessPlan",
        "bpInsights",
        "esgIssues",
        # NB: 'tasks' and 'boards' are migrated to real tables by
        # TasksMigrator/BoardsMigrator — not dumped here.
        "comments",
        "consultantImport",
        "customDirections",
        "systemConfig",
        "nationalContext",
    ]

    async def apply(self, ctx: MigrationContext) -> None:
        from app.models.system_config import SystemConfig

        for k in self.DUMP_KEYS:
            data = ctx.fb.get(f"/pf/{k}")
            if data is None:
                ctx.report.add_skip("raw_dumps", f"{k}: empty in Firebase")
                continue

            config_key = f"firebase_dump.{k}"
            existing_q = await ctx.db.execute(
                select(SystemConfig).where(SystemConfig.key == config_key)
            )
            existing = existing_q.scalar_one_or_none()

            # Best-effort size check (Firebase might return huge structures)
            try:
                size = len(json.dumps(data, default=str))
            except (TypeError, ValueError):
                ctx.report.add_skip("raw_dumps", f"{k}: cannot JSON-serialize")
                continue

            if size > 20 * 1024 * 1024:  # 20 MB cap (JSONB supports up to 1GB but practical limit lower)
                ctx.report.add_warning(f"raw_dumps/{k}: {size} bytes — exceeds 20MB cap, skipping")
                ctx.report.add_skip("raw_dumps", f"{k}: too large ({size} bytes)")
                continue

            if existing:
                if ctx.dry_run:
                    ctx.report.add_update("raw_dumps")
                else:
                    existing.value = data
                    existing.description = f"Firebase backup of /pf/{k} ({size} bytes)"
                    ctx.report.add_update("raw_dumps")
            else:
                if ctx.dry_run:
                    ctx.report.add_create("raw_dumps")
                else:
                    ctx.db.add(SystemConfig(
                        key=config_key,
                        value=data,
                        description=f"Firebase backup of /pf/{k} ({size} bytes)",
                        is_secret=False,
                    ))
                    ctx.report.add_create("raw_dumps")

        if not ctx.dry_run:
            await ctx.db.flush()


# =====================================================================
# Boards & Tasks (ProjectsFlow heritage)
# =====================================================================

class BoardsMigrator(Migrator):
    """Migrate `/pf/boards` → boards table.

    Monolith board shape:
      { id, name, color, sector, description, sortOrder, archived, createdAt, ... }

    Boards in the monolith are typically per-company (board.name == company.name).
    We attempt to link `company_id` by matching board.name against company.name_ru,
    name_short, or code. Unmatched boards still migrate (company_id NULL).
    """

    name = "boards"
    firebase_path = "/pf/boards"

    async def apply(self, ctx: MigrationContext) -> None:
        raw = ctx.fb.get(self.firebase_path)
        items = normalize_array(raw)
        if not items:
            ctx.report.add_skip("boards", "no /pf/boards data in Firebase")
            return

        # Build lookup. We register every name field (code/name_short/name_ru/
        # name_uz/name_en) under TWO keys: the strict lower-stripped form, and
        # an aggressive form with all non-alphanumerics removed. Firebase
        # stores monolith COMPANIES[*].name verbatim — values like "УзАвто
        # Саноат", "Uzbekistan Airways", "UzTelecom" — none of which match
        # canonical name_short. The aggressive form catches them.
        from app.models.company import Company  # local import to avoid cycle
        import re

        def _norm_strict(s: str) -> str:
            return s.strip().lower() if s else ""

        def _norm_aggressive(s: str) -> str:
            if not s: return ""
            return re.sub(r"[^a-zа-яё0-9]", "", s.lower())

        comp_result = await ctx.db.execute(select(Company))
        all_companies = list(comp_result.scalars().all())
        comp_by_key: dict[str, Company] = {}
        for c in all_companies:
            for raw in (c.code, c.name_ru, c.name_short, c.name_uz, c.name_en):
                if not raw:
                    continue
                comp_by_key[_norm_strict(raw)]     = c
                comp_by_key[_norm_aggressive(raw)] = c

        # Hand-curated aliases for forms that don't normalise into any DB field.
        # Mirrors the alias table in migration 0014.
        ALIAS_MAP = {
            "узавтосаноат":             "uas",   # "УзАвто Саноат" → uas
            "uzbekistanairways":        "uhy",
            "uzbekistanairports":       "uap",
            "uztelecom":                "utc",
            "узбектелеком":             "utc",
            "узбекистонпочтаси":        "upt",
            "uzpost":                   "upt",
            "узбекистонтемирйуллари":   "uty",
            "uzbekistanrailways":       "uty",
            "тошшахартрансхизмат":      "tst",
            "узбекгидроэнерго":         "uge",
            "национальныеэлектрическиесетиузбекистана": "nes",
            "тепловыеэлектрическиестанции":            "tes",
            "региональныеэлектрическиесети":           "res",
            "навоийскийгмк":            "ngmk",
            "алмалыкскийгмк":           "agmk",
            "худудгазтаъминот":         "hgt",
            "узкимесаноат":             "uks",
        }
        comp_by_code = {c.code: c for c in all_companies}
        for alias, code in ALIAS_MAP.items():
            if code in comp_by_code:
                comp_by_key.setdefault(alias, comp_by_code[code])

        from app.models.board import Board

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            legacy_id = safe_str(item.get("id"), 64)
            board_name = safe_str(item.get("name"), 255)
            if not board_name:
                ctx.report.add_skip("boards", f"row {idx}: empty name")
                continue

            # Idempotency: lookup by legacy_id if available
            existing = None
            if legacy_id:
                res = await ctx.db.execute(select(Board).where(Board.legacy_id == legacy_id))
                existing = res.scalar_one_or_none()

            if existing:
                ctx.report.add_skip("boards", f"{board_name} already migrated")
                continue

            # Try to attach to a company by name match — strict first, then aggressive
            comp = (comp_by_key.get(_norm_strict(board_name))
                    or comp_by_key.get(_norm_aggressive(board_name)))
            company_id = comp.id if comp else None

            # When attached to a canonical company, normalise the displayed
            # board name to company.name_short. Without this, the Boards/Projects
            # list shows mixed legacy labels (e.g. "Узбекистон темир йуллари"
            # alongside "АГМК" instead of "УТЙ" / "АГМК"). The original Firebase
            # name is preserved in extra.legacy_name for audit.
            display_name = board_name
            legacy_name = None
            if comp and comp.name_short and comp.name_short != board_name:
                legacy_name = board_name
                display_name = comp.name_short

            if ctx.dry_run:
                ctx.report.add_create("boards")
                log.info("DRY-RUN  boards CREATE  name='%s' company=%s",
                         display_name, comp.code if comp else None)
                continue

            extra = {"source": "firebase.pf.boards"}
            if legacy_name:
                extra["legacy_name"] = legacy_name

            board = Board(
                name=display_name,
                description=safe_str(item.get("description"), 2000),
                company_id=company_id,
                color_hex=safe_str(item.get("color"), 9),
                sector_code=safe_str(item.get("sector"), 32),
                sort_order=safe_int(item.get("sortOrder")) or idx * 10,
                is_archived=bool(item.get("archived", False)),
                legacy_id=legacy_id,
                extra=extra,
            )
            ctx.db.add(board)
            ctx.report.add_create("boards")

        if not ctx.dry_run:
            await ctx.db.flush()


class TasksMigrator(Migrator):
    """Migrate `/pf/tasks` → tasks table.

    Monolith task shape:
      { id, boardId, num, title, status, priority, direction, assignee,
        assigneeEmail, deadline, description, scope, linkedTaskId,
        sortOrder, createdAt, updatedAt, modifiedBy, _isProject,
        portfolio_year, consultant, tags, ... }

    Tasks reference boards by `boardId` (monolith uses string id, we map to
    legacy_id → board UUID). Tasks with unknown boardId still migrate
    (board_id NULL — surfaced in admin UI for manual fixup).
    """

    name = "tasks"
    firebase_path = "/pf/tasks"

    # Map monolith status → our status. Monolith uses 8 statuses (line 50585):
    # new, init, active, review, done, quarterly, monthly, ongoing.
    # Defensive fallbacks handle legacy data that pre-dates the canonical list.
    STATUS_MAP = {
        "new":       "new",
        "init":      "init",
        "active":    "active",
        "review":    "review",
        "done":      "done",
        "quarterly": "quarterly",
        "monthly":   "monthly",
        "ongoing":   "ongoing",
        # Defensive fallbacks for legacy variations
        "in_progress": "active",
        "inprogress":  "active",
        "completed":   "done",
        "complete":    "done",
        "closed":      "done",
        "todo":        "new",
        "backlog":     "new",
        "open":        "new",
        "permanent":   "ongoing",
        "constant":    "ongoing",
    }

    PRIORITY_MAP = {
        "high":   "high",
        "medium": "medium",
        "low":    "low",
        # Defensive fallbacks
        "normal": "medium",
        "critical": "high",
    }

    async def apply(self, ctx: MigrationContext) -> None:
        raw = ctx.fb.get(self.firebase_path)
        items = normalize_array(raw)
        if not items:
            ctx.report.add_skip("tasks", "no /pf/tasks data in Firebase")
            return

        print(f"  ▶ Found {len(items)} item(s) in /pf/tasks (mix of projects + tasks)")

        from app.models.board import Board
        from app.models.task import Task
        from app.models.project import Project
        from app.models.user import User
        from app.models.company import Company

        # Build PRIMITIVE-only lookup tables (no ORM objects retained — they would
        # become "expired" after rollback and trigger MissingGreenlet on attr access)
        board_q = await ctx.db.execute(
            select(Board.id, Board.legacy_id, Board.name, Board.company_id)
        )
        board_by_legacy: dict[str, tuple] = {}    # legacy_id → (board_uuid, company_uuid|None)
        board_by_name:   dict[str, tuple] = {}
        for bid, leg, name, cid in board_q.all():
            if leg:
                board_by_legacy[leg] = (bid, cid)
            if name:
                board_by_name[name.strip().lower()] = (bid, cid)

        comp_q = await ctx.db.execute(
            select(Company.id, Company.code, Company.name_ru, Company.name_short,
                   Company.name_uz, Company.name_en)
        )
        # Two-pass index: strict (lower-stripped) AND aggressive (alphanumerics
        # only). Aggressive form catches Firebase variants like "УзАвто Саноат"
        # that monolith stored verbatim. See migration 0014 for the full alias
        # table that mirrors this behaviour at the SQL level.
        import re
        def _norm_strict(s):     return s.strip().lower() if s else ""
        def _norm_aggressive(s): return re.sub(r"[^a-zа-яё0-9]", "", s.lower()) if s else ""

        comp_by_key: dict[str, "UUID"] = {}
        comp_by_code: dict[str, "UUID"] = {}
        for cid, code, nru, nshort, nuz, nen in comp_q.all():
            comp_by_code[code] = cid
            for k in (code, nru, nshort, nuz, nen):
                if not k:
                    continue
                comp_by_key[_norm_strict(k)]     = cid
                comp_by_key[_norm_aggressive(k)] = cid

        ALIAS_MAP_TASKS = {
            "узавтосаноат":             "uas",
            "uzbekistanairways":        "uhy",
            "uzbekistanairports":       "uap",
            "uztelecom":                "utc",
            "узбектелеком":             "utc",
            "узбекистонпочтаси":        "upt",
            "uzpost":                   "upt",
            "узбекистонтемирйуллари":   "uty",
            "uzbekistanrailways":       "uty",
            "тошшахартрансхизмат":      "tst",
            "узбекгидроэнерго":         "uge",
            "национальныеэлектрическиесетиузбекистана": "nes",
            "тепловыеэлектрическиестанции":            "tes",
            "региональныеэлектрическиесети":           "res",
            "навоийскийгмк":            "ngmk",
            "алмалыкскийгмк":           "agmk",
            "худудгазтаъминот":         "hgt",
            "узкимесаноат":             "uks",
        }
        for alias, code in ALIAS_MAP_TASKS.items():
            cid = comp_by_code.get(code)
            if cid:
                comp_by_key.setdefault(alias, cid)

        user_q = await ctx.db.execute(select(User.id, User.email))
        users_by_email: dict[str, "UUID"] = {
            email.lower(): uid for uid, email in user_q.all() if email
        }

        # Pre-load existing legacy_ids from BOTH tables (since they share id-space)
        existing_q_t = await ctx.db.execute(
            select(Task.legacy_id).where(Task.legacy_id.is_not(None))
        )
        existing_q_p = await ctx.db.execute(
            select(Project.legacy_id).where(Project.legacy_id.is_not(None))
        )
        existing_legacy_ids: set[str] = (
            {row[0] for row in existing_q_t.all()} | {row[0] for row in existing_q_p.all()}
        )
        if existing_legacy_ids:
            print(f"  ⓘ {len(existing_legacy_ids)} item(s) already migrated — will skip those")

        seen_legacy_ids: set[str] = set()

        from datetime import datetime as _dt

        BATCH_SIZE = 200

        # Separate counters/buffers per destination table
        counts = {"tasks": 0, "projects": 0}
        skipped_dup = 0
        skipped_bad = 0
        skipped_inrun_dup = 0
        orphan_board = 0
        first_errors: list[str] = []

        # Two pending buffers — flushed independently
        pending_tasks:    list[dict] = []
        pending_projects: list[dict] = []

        async def _flush_one(buffer: list[dict], Model, label: str):
            """Flush one batch; on failure rollback and retry per-row."""
            nonlocal first_errors
            if not buffer or ctx.dry_run:
                buffer.clear()
                return

            objs = [Model(**kw) for kw in buffer]
            for o in objs:
                ctx.db.add(o)
            try:
                await ctx.db.flush()
                await ctx.db.commit()
                buffer.clear()
                return
            except Exception as batch_err:
                err_msg = f"{type(batch_err).__name__}: {str(batch_err)[:160]}"
                print(f"  ⚠ {label} batch flush failed ({err_msg})")
                print(f"  ↻ rolling back and retrying {len(buffer)} {label} item(s) individually…")
                await ctx.db.rollback()
                survivors = 0
                for kw in buffer:
                    try:
                        ctx.db.add(Model(**kw))
                        await ctx.db.flush()
                        await ctx.db.commit()
                        survivors += 1
                    except Exception as item_err:
                        await ctx.db.rollback()
                        if len(first_errors) < 8:
                            first_errors.append(
                                f"{label} legacy_id={kw.get('legacy_id')!r} "
                                f"title={(kw.get('title') or '')[:60]!r}: "
                                f"{type(item_err).__name__}: {str(item_err)[:140]}"
                            )
                lost = len(buffer) - survivors
                counts[label] -= lost
                print(f"     → {survivors}/{len(buffer)} {label} survived")
                buffer.clear()

        async def _maybe_flush():
            if len(pending_tasks)    >= BATCH_SIZE:  await _flush_one(pending_tasks,    Task,    "tasks")
            if len(pending_projects) >= BATCH_SIZE:  await _flush_one(pending_projects, Project, "projects")

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                skipped_bad += 1
                continue

            try:
                legacy_id = safe_str(item.get("id"), 64)
                title = safe_str(item.get("title"), 512)
                if not title:
                    skipped_bad += 1
                    continue

                if legacy_id and legacy_id in existing_legacy_ids:
                    skipped_dup += 1
                    continue
                if legacy_id and legacy_id in seen_legacy_ids:
                    skipped_inrun_dup += 1
                    continue
                if legacy_id:
                    seen_legacy_ids.add(legacy_id)

                # --- Board / company / user resolution ---
                board_legacy = safe_str(item.get("boardId"), 64)
                board_name_field = safe_str(item.get("boardName"), 255)
                board_uuid = None
                board_company_uuid = None
                if board_legacy:
                    pair = board_by_legacy.get(board_legacy)
                    if pair:
                        board_uuid, board_company_uuid = pair
                if not board_uuid and board_name_field:
                    pair = board_by_name.get(board_name_field.strip().lower())
                    if pair:
                        board_uuid, board_company_uuid = pair
                if not board_uuid:
                    orphan_board += 1

                assignee_email = safe_str(item.get("assigneeEmail"), 255)
                assignee_name  = safe_str(item.get("assignee"), 255)
                assignee_uuid  = users_by_email.get(assignee_email.lower()) if assignee_email else None

                company_uuid = board_company_uuid
                if not company_uuid and board_name_field:
                    cid = (comp_by_key.get(_norm_strict(board_name_field))
                           or comp_by_key.get(_norm_aggressive(board_name_field)))
                    if cid:
                        company_uuid = cid

                # --- Status / priority ---
                raw_status = (safe_str(item.get("status"), 32) or "new").lower()
                status = self.STATUS_MAP.get(raw_status, "new")
                raw_prio = (safe_str(item.get("priority"), 16) or "medium").lower()
                priority = self.PRIORITY_MAP.get(raw_prio, "medium")

                # --- Deadline ---
                deadline = item.get("deadline")
                due_date = None
                if isinstance(deadline, str) and deadline.strip():
                    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
                        try:
                            due_date = _dt.strptime(deadline.strip(), fmt).date()
                            break
                        except ValueError:
                            pass

                # --- Tags + consultants ---
                tags_raw = item.get("tags")
                if isinstance(tags_raw, str):
                    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
                elif isinstance(tags_raw, list):
                    tags = [str(t) for t in tags_raw if t]
                else:
                    tags = None

                consultant_raw = item.get("consultant")
                if isinstance(consultant_raw, list):
                    consultants = [str(c) for c in consultant_raw if c]
                elif isinstance(consultant_raw, str) and consultant_raw:
                    consultants = [consultant_raw]
                else:
                    consultants = []

                # --- Build extra payload — preserve all monolith-specific
                # task/project fields. The frontend's TaskProjectEditor and
                # computeProgress() read these directly:
                #   quarters       → required for status="quarterly" progress calc
                #   consultant     → free-form consultant tag (string or list)
                #   consultantComment, economicEffect, direction → editor fields
                # Without this block, all of the above would be lost on import.
                linked_legacy = safe_str(item.get("linkedTaskId"), 64)
                extra = {
                    "source":           "firebase.pf.tasks",
                    "consultants":      consultants,
                    "scope":            safe_str(item.get("scope"), 1000),
                    "modifiedBy":       safe_str(item.get("modifiedBy"), 255),
                    "linked_legacy_id": linked_legacy,
                }

                # quarters: dict like { q1: {weight, plan, fact}, q2: ..., q3: ..., q4: ... }
                # OR shorthand booleans { q1: true, q2: false, ... } — both forms accepted.
                if isinstance(item.get("quarters"), dict):
                    extra["quarters"] = item["quarters"]

                # consultant: single string or list — store verbatim
                cons_field = item.get("consultant")
                if cons_field:
                    extra["consultant"] = cons_field

                if item.get("consultantComment"):
                    extra["consultant_comment"] = safe_str(item.get("consultantComment"), 4000)

                if isinstance(item.get("economicEffect"), dict):
                    extra["economic_effect"] = item["economicEffect"]

                if item.get("direction"):
                    extra["direction"] = safe_str(item.get("direction"), 128)

                extra = {k: v for k, v in extra.items() if v}

                # === DECIDE: project vs task ===
                is_project = bool(item.get("_isProject") or item.get("isProject"))
                target = "projects" if is_project else "tasks"

                if ctx.dry_run:
                    counts[target] += 1
                    ctx.report.add_create(target)
                    continue

                kwargs = dict(
                    legacy_id=legacy_id,
                    title=title,
                    description=safe_str(item.get("description"), 10000),
                    num=safe_str(item.get("num"), 64),
                    status=status,
                    priority=priority,
                    board_id=board_uuid,
                    company_id=company_uuid,
                    assignee_id=assignee_uuid,
                    assignee_email=assignee_email,
                    assignee_name=assignee_name,
                    portfolio_year=safe_int(item.get("portfolio_year")),
                    due_date=due_date,
                    tags=tags,
                    extra=extra,
                )

                if is_project:
                    pending_projects.append(kwargs)
                else:
                    pending_tasks.append(kwargs)
                counts[target] += 1
                ctx.report.add_create(target)

                await _maybe_flush()
                if (idx + 1) % 1000 == 0 or idx + 1 == len(items):
                    print(f"     processed {idx + 1}/{len(items)} "
                          f"(tasks={counts['tasks']}, projects={counts['projects']})")

            except Exception as parse_err:
                if len(first_errors) < 8:
                    first_errors.append(
                        f"item {idx} id={item.get('id')!r}: "
                        f"{type(parse_err).__name__}: {str(parse_err)[:140]}"
                    )
                skipped_bad += 1

        # Final flush
        await _flush_one(pending_tasks,    Task,    "tasks")
        await _flush_one(pending_projects, Project, "projects")

        # ===== Phase 2: Resolve task → project links from extra.linked_legacy_id =====
        # When a task references a project as its parent, link it via project_id FK.
        if not ctx.dry_run:
            print(f"  ▶ Resolving task → project parent links…")
            # Build legacy_id → project.id map
            proj_q = await ctx.db.execute(
                select(Project.id, Project.legacy_id).where(Project.legacy_id.is_not(None))
            )
            proj_by_legacy: dict[str, "UUID"] = {leg: pid for pid, leg in proj_q.all()}

            # Find all tasks with linked_legacy_id in extra
            linked_q = await ctx.db.execute(
                select(Task.id, Task.extra)
                .where(Task.extra["linked_legacy_id"].is_not(None))
            )
            updates = []
            for tid, extra_payload in linked_q.all():
                if isinstance(extra_payload, dict):
                    linked = extra_payload.get("linked_legacy_id")
                    if linked and linked in proj_by_legacy:
                        updates.append((tid, proj_by_legacy[linked]))

            if updates:
                from sqlalchemy import update as sa_update
                for tid, pid in updates:
                    await ctx.db.execute(
                        sa_update(Task).where(Task.id == tid).values(project_id=pid)
                    )
                await ctx.db.commit()
                print(f"     ✓ Linked {len(updates)} task(s) to their parent projects")

        print(f"  ✓ Done: tasks={counts['tasks']}, projects={counts['projects']}, "
              f"dup_db={skipped_dup}, dup_inrun={skipped_inrun_dup}, "
              f"bad={skipped_bad}, orphan_board={orphan_board}")
        if first_errors:
            print(f"  ⚠ first {len(first_errors)} error(s):")
            for err in first_errors:
                print(f"     · {err}")

        if orphan_board > 0:
            ctx.report.add_skip("tasks_orphan_board", f"{orphan_board} item(s) without matching board")
        if skipped_inrun_dup > 0:
            ctx.report.add_skip("tasks_dup_in_firebase",
                                f"{skipped_inrun_dup} item(s) had duplicate id in Firebase payload")


# =====================================================================
# Agency ratings (credit + ESG) — /pf/ratings
# =====================================================================

class RatingsMigrator(Migrator):
    """Migrate `/pf/ratings` → agency_ratings table.

    Monolith rating shape:
      { boardId, agency, rating, outlook, date, score, url }

    Each rating is associated with a board (1:1 with company in our model).
    Discriminator: ESG_AGENCIES list — agencies in it are ESG, others are credit.

    Idempotency: composite legacy_id = "{board_id}::{agency}". Re-running the
    migrator with the same data produces the same result. If a rating with a
    different value exists for the same (company, agency), it is UPDATED
    (matches monolith RatingsStore.save() behaviour).
    """

    name = "ratings"
    firebase_path = "/pf/ratings"

    # Russian month name → number (for parsing "июл 2025" style dates)
    RU_MONTHS = {
        "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "июн": 6,
        "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
    }

    @classmethod
    def _parse_rating_date(cls, text):
        """Parse loose date text like 'июл 2025', 'ноя 2024', '2025' into a date.

        Returns first day of the month if month is known, first of January
        for year-only, or None if unparseable.
        """
        from datetime import date as _date
        if not text:
            return None
        s = str(text).strip().lower()
        if not s:
            return None
        # Year-only: "2025"
        if s.isdigit() and len(s) == 4:
            try:
                return _date(int(s), 1, 1)
            except ValueError:
                return None
        # "июл 2025"
        parts = s.replace(".", " ").split()
        if len(parts) >= 2:
            month_part = parts[0][:3]
            year_part = parts[-1]
            month = cls.RU_MONTHS.get(month_part)
            try:
                year = int(year_part)
            except (ValueError, TypeError):
                year = None
            if month and year:
                try:
                    return _date(year, month, 1)
                except ValueError:
                    return None
        return None

    async def apply(self, ctx: MigrationContext) -> None:
        from app.models.agency_rating import AgencyRating, ESG_AGENCIES, is_esg_agency
        from app.models.board import Board
        from app.models.company import Company

        raw = ctx.fb.get(self.firebase_path)
        items = normalize_array(raw)
        if not items:
            ctx.report.add_skip("ratings", "no /pf/ratings data in Firebase")
            return

        print(f"  ▶ Found {len(items)} rating(s) in /pf/ratings")

        # Build board_legacy_id → company_id lookup (primitive only)
        board_q = await ctx.db.execute(
            select(Board.legacy_id, Board.company_id, Board.name).where(Board.legacy_id.is_not(None))
        )
        board_to_company: dict[str, "UUID"] = {}
        board_name_lookup: dict[str, str] = {}  # legacy_id → board name (for fallback)
        for leg, cid, name in board_q.all():
            if leg and cid:
                board_to_company[leg] = cid
            if leg and name:
                board_name_lookup[leg] = name

        # Fallback: company name → company_id (if board has no company linked)
        comp_q = await ctx.db.execute(
            select(Company.id, Company.name_ru, Company.name_short, Company.code)
        )
        comp_by_name: dict[str, "UUID"] = {}
        for cid, nru, nshort, code in comp_q.all():
            for k in (code, nru, nshort):
                if k:
                    comp_by_name[k.strip().lower()] = cid

        # Pre-load existing legacy_ids for idempotency
        existing_q = await ctx.db.execute(
            select(AgencyRating.legacy_id).where(AgencyRating.legacy_id.is_not(None))
        )
        existing_legacy_ids: set[str] = {row[0] for row in existing_q.all()}

        created = 0
        skipped_dup = 0
        skipped_orphan = 0
        skipped_bad = 0
        first_errors: list[str] = []

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                skipped_bad += 1
                continue

            try:
                board_legacy = safe_str(item.get("boardId"), 64)
                agency = safe_str(item.get("agency"), 64)
                if not agency:
                    skipped_bad += 1
                    continue

                # Resolve company
                company_uuid = board_to_company.get(board_legacy) if board_legacy else None
                if not company_uuid and board_legacy:
                    # Try via board name
                    board_name = board_name_lookup.get(board_legacy, "")
                    if board_name:
                        company_uuid = comp_by_name.get(board_name.strip().lower())
                if not company_uuid:
                    skipped_orphan += 1
                    continue

                # Composite legacy_id for idempotency
                composite_legacy = f"{board_legacy}::{agency}"
                if composite_legacy in existing_legacy_ids:
                    skipped_dup += 1
                    continue

                rating_date_text = safe_str(item.get("date"), 64)
                rating_date = self._parse_rating_date(rating_date_text)

                if ctx.dry_run:
                    created += 1
                    ctx.report.add_create("ratings")
                    continue

                rec = AgencyRating(
                    company_id=company_uuid,
                    agency=agency,
                    is_esg=is_esg_agency(agency),
                    rating=safe_str(item.get("rating"), 16),
                    outlook=safe_str(item.get("outlook"), 32),
                    score=safe_str(item.get("score"), 16),
                    rating_date_text=rating_date_text,
                    rating_date=rating_date,
                    report_url=safe_str(item.get("url"), 2000),
                    legacy_id=composite_legacy,
                    legacy_board_id=board_legacy,
                    extra={"source": "firebase.pf.ratings"},
                )
                ctx.db.add(rec)
                existing_legacy_ids.add(composite_legacy)
                created += 1
                ctx.report.add_create("ratings")

                # Commit every 50 records
                if created % 50 == 0:
                    try:
                        await ctx.db.flush()
                        await ctx.db.commit()
                    except Exception as e:
                        await ctx.db.rollback()
                        if len(first_errors) < 5:
                            first_errors.append(
                                f"flush err at {idx}: {type(e).__name__}: {str(e)[:140]}"
                            )

            except Exception as e:
                if len(first_errors) < 5:
                    first_errors.append(
                        f"item {idx} agency={item.get('agency')!r}: "
                        f"{type(e).__name__}: {str(e)[:140]}"
                    )
                skipped_bad += 1

        # Final flush
        if not ctx.dry_run:
            try:
                await ctx.db.flush()
                await ctx.db.commit()
            except Exception as e:
                await ctx.db.rollback()
                if len(first_errors) < 5:
                    first_errors.append(f"final flush: {type(e).__name__}: {str(e)[:140]}")

        # Count by category
        if not ctx.dry_run:
            esg_q = await ctx.db.execute(
                select(func.count()).select_from(AgencyRating).where(AgencyRating.is_esg.is_(True))
            )
            credit_q = await ctx.db.execute(
                select(func.count()).select_from(AgencyRating).where(AgencyRating.is_esg.is_(False))
            )
            esg_count = esg_q.scalar_one()
            credit_count = credit_q.scalar_one()
            print(f"  ✓ ratings created={created}, dup={skipped_dup}, "
                  f"orphan_company={skipped_orphan}, bad={skipped_bad}")
            print(f"     → {credit_count} credit, {esg_count} ESG (total in DB: {credit_count+esg_count})")
        else:
            print(f"  ✓ ratings would-create={created}, dup={skipped_dup}, "
                  f"orphan_company={skipped_orphan}, bad={skipped_bad}")

        if first_errors:
            print(f"  ⚠ first {len(first_errors)} error(s):")
            for err in first_errors:
                print(f"     · {err}")

        if skipped_orphan > 0:
            ctx.report.add_skip(
                "ratings_orphan_company",
                f"{skipped_orphan} rating(s) had no matching company"
            )


# =====================================================================
# =====================================================================
# GOVERNANCE — board composition + scores per company per year
# =====================================================================

class GovernanceMigrator(Migrator):
    """Migrate `/pf/governanceData` → governance_data table.

    Firebase shape: list of {abbr, name, members, vacant, indep, exec, nonexec,
    women, committees, audit, strategy, anticorr, procurement, esg, dno,
    induction, score, meetings, ageMax?, ageAvg?, ageMin?}. The whole object
    is preserved in the JSONB payload column for AI context, but the most
    common fields are also extracted into typed columns for fast queries.

    The seed migration (0004) already populated 20 of 22 companies from a
    static file. This migrator picks up Firebase additions/edits — including
    UPT (Узбекистон Почтаси) and UTY (Узбекистон темир йуллари) which were
    missing from the original seed. Idempotent on (company_id, year).

    Lookup by abbr is case-insensitive — Firebase may have lowercase or
    mixed-case keys.
    """

    name = "governance"
    firebase_path = "/pf/governanceData"

    async def run(self, ctx: "MigrationContext") -> None:
        from app.models.governance import GovernanceData

        data = ctx.fb.get(self.firebase_path)
        if data is None:
            ctx.report.add_warning(f"{self.firebase_path}: empty in Firebase")
            return

        # Normalize: Firebase may return list (numeric-key array → list)
        # or dict-keyed-by-index (unordered)
        records = []
        if isinstance(data, list):
            records = [r for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            for v in data.values():
                if isinstance(v, dict):
                    records.append(v)

        if not records:
            ctx.report.add_warning(f"{self.firebase_path}: no records")
            return

        # Build company lookup by code (lowercase)
        comp_q = await ctx.db.execute(select(Company))
        companies_by_code: dict[str, Company] = {
            c.code.lower(): c for c in comp_q.scalars().all()
        }

        # Default year for governance snapshots — use current year of platform
        # (monolith stores all current data without year tag → assume current)
        from datetime import date
        default_year = date.today().year

        created = 0
        updated = 0
        skipped: list[str] = []

        for rec in records:
            abbr = (rec.get("abbr") or "").strip().lower()
            if not abbr:
                continue

            company = companies_by_code.get(abbr)
            if not company:
                skipped.append(abbr)
                continue

            year = int(rec.get("year") or default_year)

            # Extract typed fields
            board_size = rec.get("members")
            indep      = rec.get("indep")
            women      = rec.get("women")
            meetings   = rec.get("meetings")

            # Look up existing row for (company_id, year)
            existing_q = await ctx.db.execute(
                select(GovernanceData).where(
                    GovernanceData.company_id == company.id,
                    GovernanceData.year == year,
                )
            )
            existing = existing_q.scalar_one_or_none()

            if ctx.dry_run:
                if existing:
                    updated += 1
                    ctx.report.add_update("governance")
                else:
                    created += 1
                    ctx.report.add_create("governance")
                continue

            if existing:
                # Update typed fields + payload
                if board_size is not None:
                    existing.board_size = int(board_size)
                if indep is not None:
                    existing.independent_directors_count = int(indep)
                if women is not None:
                    existing.women_directors_count = int(women)
                if meetings is not None:
                    existing.meetings_per_year = int(meetings)
                # Audit committees
                existing.has_audit_committee   = bool(rec.get("audit"))
                existing.has_strategy_committee = bool(rec.get("strategy"))
                existing.payload = dict(rec)
                updated += 1
                ctx.report.add_update("governance")
            else:
                row = GovernanceData(
                    company_id=company.id,
                    year=year,
                    board_size=int(board_size) if board_size is not None else None,
                    independent_directors_count=int(indep) if indep is not None else None,
                    women_directors_count=int(women) if women is not None else None,
                    meetings_per_year=int(meetings) if meetings is not None else None,
                    has_audit_committee=bool(rec.get("audit")),
                    has_strategy_committee=bool(rec.get("strategy")),
                    payload=dict(rec),
                )
                ctx.db.add(row)
                created += 1
                ctx.report.add_create("governance")

        if not ctx.dry_run:
            await ctx.db.commit()

        print(f"  ✓ governance: {created} created, {updated} updated, "
              f"{len(skipped)} skipped (unmatched abbrs)")
        if skipped:
            print(f"  ⚠ unmatched abbrs: {skipped[:10]}")


# =====================================================================
# Registry of all migrators in order
# =====================================================================

ALL_MIGRATORS: list[type[Migrator]] = [
    CompaniesMigrator,         # 1. Must run first — others reference companies
    FinancialsMigrator,        # 2. Per-company financial reports
    AnnouncementsMigrator,     # 3. Standalone
    YearRegistryMigrator,      # 4. Year registries for ESG/ratings
    BoardsMigrator,            # 5. Kanban boards (must precede tasks)
    TasksMigrator,             # 6. Tasks + projects (depends on boards)
    RatingsMigrator,           # 7. Agency ratings (depends on boards/companies)
    GovernanceMigrator,        # 8. Board composition / governance scores
]

# --- Phase 5: structural migrators for executive dashboards ----------
# (loaded lazily so existing deployments without phase5 file still work)
try:
    from .migrators_phase5 import (
        BusinessPlanMigrator, KpiMigrator, ProcurementMigrator,
    )
    ALL_MIGRATORS.extend([
        BusinessPlanMigrator,  # 9.  /pf/businessPlan → bp_records
        KpiMigrator,           # 10. /pf/kpi → kpi_managers + kpi_indicators
        ProcurementMigrator,   # 11. /pf/procurementData → procurement_data
    ])
except ImportError:
    pass

# --- Phase 6: procurement closures from /pf/procurementContracts ------
try:
    from .migrators_phase6 import ProcurementClosuresMigrator
    ALL_MIGRATORS.append(ProcurementClosuresMigrator)  # 12. closures (raw rows → benchmarks)
except ImportError:
    pass

# Always last — JSONB catch-all backup of everything else
ALL_MIGRATORS.append(RawDumpMigrator)


# ??? Phase 9: ESG metrics seed (embedded ? no Firebase source) ???
try:
    from .migrators_phase9 import ESGMetricsMigrator as _M9
    ALL_MIGRATORS.append(_M9)  # type: ignore[arg-type]
except ImportError as _e:
    import logging as _log9
    _log9.getLogger(__name__).warning("Phase 9 ESG migrator not loaded: %s", _e)



# Phase 11: Consultants seed + assignments
try:
    from .migrators_phase11 import (
        ConsultantsMigrator as _M11A,
        ConsultantAssignmentsMigrator as _M11B,
    )
    ALL_MIGRATORS.append(_M11A)
    ALL_MIGRATORS.append(_M11B)
except ImportError as _e:
    import logging
    logging.getLogger(__name__).warning('Phase 11 not loaded: %s', _e)
