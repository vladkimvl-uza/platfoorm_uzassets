"""seed monolith hardcoded data — catalogs and baseline business data

Revision ID: 0004_monolith_seeds
Revises: 0003_companies
Create Date: 2026-05-04 14:30:00.000000

The legacy monolith (`index.html`, ~66k lines) contained several constant
arrays with real business data and reference catalogs that were never moved
into the Firebase Realtime DB. We extracted them as JSON files in
`backend/data/seed/` and seed them here.

Seeded:
  System config (lookups / catalogs as JSONB):
    catalog.consultants                  17 consulting firms (PwC, EY, …)
    catalog.procurement_categories       15 categories from Decree Ф-59
    catalog.decrees                      list of presidential decrees
    catalog.financial_line_codes         33 IFRS chart-of-accounts codes
    catalog.esg_agencies                 3 ESG rating agencies
    catalog.ifrs_sheet_map               company-code → Excel-sheet name
    ui.task_status_labels                task status localization
    ui.task_priority_labels              task priority localization
    snapshot.procurement_summary_2024_2026   procurement plan/fact per company

  Business tables (real records):
    governance_data                      20 board-of-directors snapshots

For governance_data: matched against companies by `abbr` → company.code.
For raw catalog seeds: stored in system_config as JSONB so they're editable
through admin UI later without schema changes.

The Firebase migration script may already have populated some of this data.
We use ON CONFLICT DO UPDATE for system_config (overwrite — these are
authoritative defaults from monolith) and ON CONFLICT DO NOTHING for
governance_data (preserve any user edits that came through Firebase).
"""
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_monolith_seeds"
down_revision: Union[str, None] = "0003_companies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Where the JSON seed files live, relative to backend/
_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "seed"


def _load(name: str):
    path = _SEED_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Seed file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def upgrade() -> None:
    bind = op.get_bind()

    # ============================================================
    # 1. SYSTEM CONFIG CATALOGS (lookups, JSONB)
    # ============================================================
    upsert_config = sa.text("""
        INSERT INTO system_config (id, key, value, description, is_secret, created_at, updated_at)
        VALUES (gen_random_uuid(), :key, CAST(:value AS jsonb), :description, FALSE, NOW(), NOW())
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value,
            description = EXCLUDED.description,
            updated_at = NOW()
    """)

    catalogs = [
        ("catalog.consultants",
         "consultants.json",
         "Consulting firms directory (17 firms: PwC, EY, Deloitte, KPMG, McKinsey, BCG, etc.)"),
        ("catalog.procurement_categories",
         "procurement_categories.json",
         "Procurement categories per Presidential Decree Ф-59 from 18.11.2025 (15 centralized categories)"),
        ("catalog.decrees",
         "decrees.json",
         "Presidential decrees registry"),
        ("catalog.financial_line_codes",
         "financial_line_codes.json",
         "IFRS chart-of-accounts canonical line codes (33 fields used in financial reports)"),
        ("catalog.esg_agencies",
         "esg_agencies.json",
         "ESG rating agencies (Sustainable Fitch, S&P ESG, CDP)"),
        ("catalog.ifrs_sheet_map",
         "ifrs_sheet_map.json",
         "Mapping of company code → Excel sheet name (used during financial data import)"),
        ("ui.task_status_labels",
         "task_status_labels.json",
         "Task status localization (init/new/active/review/done)"),
        ("ui.task_priority_labels",
         "task_priority_labels.json",
         "Task priority localization (high/medium/low)"),
        ("snapshot.procurement_summary_2024_2026",
         "procurement_summary.json",
         "Aggregated procurement plan/fact per company for 2024-2026, with audit and decree status. "
         "Migrated from monolith PROCUREMENT_DATA constant — to be re-modeled into procurement_summaries table when Part 9 is built."),
    ]

    for key, filename, description in catalogs:
        try:
            data = _load(filename)
            bind.execute(upsert_config, {
                "key": key,
                "value": json.dumps(data, ensure_ascii=False),
                "description": description,
            })
        except Exception as e:
            print(f"  ⚠ Skipped {key}: {type(e).__name__}: {e}")

    # ============================================================
    # 2. GOVERNANCE_DATA (real records — match by company.code)
    # ============================================================
    # Build company_abbr → company.id map (lowercase code = lowercase abbr)
    rows = bind.execute(sa.text("SELECT id, code FROM companies")).fetchall()
    company_by_code = {r.code.lower(): r.id for r in rows}

    gov_data = _load("governance_data.json")

    # We seed for the current year (2025 — this is the year the monolith
    # data was current as of the project's last update).
    DATA_YEAR = 2025

    insert_gov = sa.text("""
        INSERT INTO governance_data (
            id, company_id, year,
            board_size, independent_directors_count, women_directors_count,
            has_audit_committee, has_strategy_committee,
            meetings_per_year, payload, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), :company_id, :year,
            :board_size, :indep, :women,
            :audit, :strategy,
            :meetings, CAST(:payload AS jsonb), NOW(), NOW()
        )
        ON CONFLICT DO NOTHING
    """)
    # Note: governance_data has no UNIQUE on (company_id, year), so manual check below

    skipped, created = 0, 0
    for row in gov_data:
        abbr = (row.get("abbr") or "").lower()
        company_id = company_by_code.get(abbr)
        if not company_id:
            print(f"  ⚠ governance_data: company '{abbr}' not found in Postgres — skipping")
            skipped += 1
            continue

        # Check if already exists (no unique constraint, so explicit check)
        exists = bind.execute(
            sa.text("SELECT 1 FROM governance_data WHERE company_id = :cid AND year = :y LIMIT 1"),
            {"cid": company_id, "y": DATA_YEAR},
        ).first()
        if exists:
            skipped += 1
            continue

        bind.execute(insert_gov, {
            "company_id": company_id,
            "year": DATA_YEAR,
            "board_size": row.get("members"),
            "indep": row.get("indep"),
            "women": row.get("women"),
            "audit": bool(row.get("audit")),
            "strategy": bool(row.get("strategy")),
            "meetings": row.get("meetings"),
            "payload": json.dumps({
                "vacant": row.get("vacant"),
                "exec": row.get("exec"),
                "nonexec": row.get("nonexec"),
                "committees": row.get("committees"),
                "anticorr": bool(row.get("anticorr", 0)),
                "procurement": bool(row.get("procurement", 0)),
                "esg": bool(row.get("esg", 0)),
                "dno": bool(row.get("dno", 0)),
                "induction": bool(row.get("induction", 0)),
                "score": row.get("score"),
                "ageMax": row.get("ageMax"),
                "ageAvg": row.get("ageAvg"),
                "ageMin": row.get("ageMin"),
                "_source": "monolith.GOV_DATA",
            }, ensure_ascii=False),
        })
        created += 1

    # ============================================================
    # 3. CONSULTANT_LOOKUP — task → consultant mapping (2025)
    # ============================================================
    # This is a complex mapping (47 lines). For now keep it as raw JSON in
    # system_config so the Tasks module (Part 5) can use it for backfill.
    # The actual task records will get migrated separately from /pf/tasks.
    # We don't have CONSULTANT_LOOKUP file extracted yet — skip silently.

    print(f"\n  ✓ governance_data seeded: {created} created, {skipped} skipped")


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        DELETE FROM system_config
        WHERE key IN (
            'catalog.consultants',
            'catalog.procurement_categories',
            'catalog.decrees',
            'catalog.financial_line_codes',
            'catalog.esg_agencies',
            'catalog.ifrs_sheet_map',
            'ui.task_status_labels',
            'ui.task_priority_labels',
            'snapshot.procurement_summary_2024_2026'
        )
    """))
    bind.execute(sa.text("""
        DELETE FROM governance_data
        WHERE payload->>'_source' = 'monolith.GOV_DATA'
    """))
