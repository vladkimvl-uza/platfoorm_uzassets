"""seed agency_ratings from monolith _ESG_RATINGS_DB

Revision ID: 9aH_esg_agency_ratings_seed
Revises: 9aG_drop_requires_moderation
Create Date: 2026-05-17

The monolith stores ESG agency ratings (Sustainable Fitch / S&P ESG / CDP /
Sustainalytics / MSCI) in the JS constant `_ESG_RATINGS_DB` (22 entries).
The Vue ESG dashboard reads them via the structured `agency_ratings` table.

This migration replicates the monolith's `_syncEsgRatings` normalization
(index.html:52569) — agency rename "S&P CSA"/"S&P CSR" → "S&P ESG", drops
"Private" placeholders, strips "SF "/"S&P "/"CDP " prefix from rating text.

Match companies via the seed file's `code` column (matches `companies.code`
exactly, case-insensitive). Entries with `code: null` are skipped (companies
not yet present in Postgres — e.g. Узбекистон Темир Йуллари, Узбекпочтаси).

Uses ON CONFLICT DO NOTHING on (company_id, agency) — preserves any rating
already entered via UI / Firebase migration.
"""
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9aH_esg_agency_ratings_seed"
down_revision: Union[str, None] = "9aG_drop_requires_moderation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "seed"


def _normalize_agency(name: str) -> str:
    """Monolith _syncEsgRatings: S&P CSA / S&P CSR → S&P ESG."""
    name = (name or "").strip()
    if name in ("S&P CSA", "S&P CSR"):
        return "S&P ESG"
    return name


def _strip_prefix(rating: str) -> str:
    """Strip 'SF '/'S&P '/'CDP ' prefix from the raw rating text."""
    import re
    return re.sub(r"^(SF|S&P|CDP)\s+", "", (rating or "").strip(), flags=re.IGNORECASE)


def _numeric_score(rating: str) -> str:
    """Extract digits only from a rating string ('SF 54' → '54'). Empty if none."""
    import re
    digits = re.sub(r"[^0-9]", "", rating or "")
    return digits


def upgrade() -> None:
    bind = op.get_bind()

    seed_path = _SEED_DIR / "esg_agency_ratings.json"
    if not seed_path.is_file():
        print(f"  ⚠ ESG ratings seed not found: {seed_path} — skipping")
        return
    rows = json.loads(seed_path.read_text(encoding="utf-8"))

    # Build code → company_id map
    db_rows = bind.execute(sa.text("SELECT id, code FROM companies")).fetchall()
    by_code = {(r.code or "").lower(): r.id for r in db_rows}

    insert_sql = sa.text("""
        INSERT INTO agency_ratings (
            id, company_id, agency, is_esg,
            rating, outlook, score,
            rating_date_text, rating_date,
            report_url,
            legacy_id, legacy_board_id,
            extra,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid(), :company_id, :agency, TRUE,
            :rating, NULL, :score,
            :rating_date_text, NULL,
            :report_url,
            :legacy_id, NULL,
            CAST(:extra AS jsonb),
            NOW(), NOW()
        )
        ON CONFLICT (company_id, agency) DO NOTHING
    """)

    created = 0
    skipped_no_code = 0
    skipped_private = 0
    skipped_empty = 0
    skipped_no_co = 0

    for row in rows:
        code = (row.get("code") or "").lower()
        if not code:
            skipped_no_code += 1
            continue

        company_id = by_code.get(code)
        if company_id is None:
            print(f"  ⚠ ESG seed: company code '{code}' not in companies — skipping {row.get('name')}")
            skipped_no_co += 1
            continue

        # Prefer the more recent year (r2026), fall back to r2025
        raw_rating_2026 = (row.get("r2026") or "").strip()
        raw_rating_2025 = (row.get("r2025") or "").strip()
        raw_rating = raw_rating_2026 or raw_rating_2025
        if not raw_rating:
            skipped_empty += 1
            continue

        agency = _normalize_agency(row.get("agency") or "Sustainable Fitch")
        if agency == "Private" or raw_rating.lower() == "private":
            skipped_private += 1
            continue
        if not agency:
            skipped_empty += 1
            continue

        rating_text = _strip_prefix(raw_rating)
        score_digits = _numeric_score(raw_rating)
        # Year tag: take year of source ("2026" if r2026 present else "2025")
        year_tag = "2026" if raw_rating_2026 else "2025"

        bind.execute(insert_sql, {
            "company_id": company_id,
            "agency": agency,
            "rating": rating_text or None,
            "score": score_digits or None,
            "rating_date_text": year_tag,
            "report_url": (row.get("url") or "").strip() or None,
            "legacy_id": f"esg::{code}::{agency}",
            "extra": json.dumps({
                "source": "monolith._ESG_RATINGS_DB",
                "raw_rating": raw_rating,
                "r2025": raw_rating_2025 or None,
                "r2026": raw_rating_2026 or None,
                "report_flag": bool(row.get("report")),
            }, ensure_ascii=False),
        })
        created += 1

    print(
        f"\n  ✓ ESG agency_ratings seeded: {created} inserted · "
        f"{skipped_no_code} skipped (no code) · "
        f"{skipped_no_co} skipped (company not in DB) · "
        f"{skipped_private} skipped (Private) · "
        f"{skipped_empty} skipped (empty rating)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Only remove rows seeded by this migration (extra.source matches).
    bind.execute(sa.text("""
        DELETE FROM agency_ratings
        WHERE extra->>'source' = 'monolith._ESG_RATINGS_DB'
    """))
