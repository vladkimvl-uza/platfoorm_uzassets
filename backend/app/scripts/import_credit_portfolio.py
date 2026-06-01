"""
Initial bulk import of the credit portfolio (367 loans) from the monolith.

The script reads decoded loan JSON (extracted from CP_LOANS_*_DEFAULT base64
blobs in index.html) and inserts each loan into cp_loans, mapping the
Russian company names to their canonical codes from migration 0003.

Mapping rules (manual — names from the monolith differ slightly from the
canonical list and fuzzy match would be unreliable):
    АО "Узбекнефтегаз"      → ung
    АО "Узтрансгаз"         → utg
    АО "Navoiyazot"         → naz
    АО "Узметкомбинат"      → umk
    "Тошшаҳартрансхизмат" АЖ → tst
    АО "Ўзбеккўмир"         → uug   (Узбекуголь)
    АО "ТЭС Узбекистана"    → tes
    АО "UzTelecom"          → utc
    АО "Узбекгидроэнерго"   → uge
    АО "Алмалыкский ГМК"    → agmk
    АО "РЭС"                → res
    АО "Uzbekistan Airways" → uhy
    АО "Худудгазтаъминот"   → hgt
    АО "НЭС Узбекистана"    → nes
    АО "НГМК"               → ngmk
    "Навоийуран" ДК         → nur
    АО "Узавтосаноат"       → uas
    АО "Узкимёсаноат"       → uks
    АО "Uzbekistan Airports" → uap

Usage:
    docker compose exec backend python -m app.scripts.import_credit_portfolio --apply
    docker compose exec backend python -m app.scripts.import_credit_portfolio --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.credit import CreditPortfolioLoan
from app.services.credit_portfolio_helpers import (
    bank_short_name,
    classify_lender,
)

log = logging.getLogger(__name__)


# Manual mapping: monolith Russian company name → canonical code
# Keys must match the exact `company` field in the decoded JSON
COMPANY_NAME_TO_CODE = {
    'АО "Узбекнефтегаз"': "ung",
    'АО "Узтрансгаз"': "utg",
    'АО "Navoiyazot"': "naz",
    'АО "Узметкомбинат"': "umk",
    '"Тошшаҳартрансхизмат" АЖ': "tst",
    'АО "Ўзбеккўмир"': "uug",
    'АО "ТЭС Узбекистана"': "tes",
    'АО "UzTelecom"': "utc",
    'АО "Узбекгидроэнерго"': "uge",
    'АО "Алмалыкский ГМК"': "agmk",
    'АО "РЭС"': "res",
    'АО "Uzbekistan Airways"': "uhy",
    'АО "Худудгазтаъминот"': "hgt",
    'АО "НЭС Узбекистана"': "nes",
    'АО "НГМК"': "ngmk",
    '"Навоийуран" ДК': "nur",
    'АО "Узавтосаноат"': "uas",
    'АО "Узкимёсаноат"': "uks",
    'АО "Uzbekistan Airports"': "uap",
}


# Default as_of date (matches CP_AS_OF in monolith)
DEFAULT_AS_OF = date(2026, 1, 1)


def _safe_decimal(v) -> Optional[Decimal]:
    """Convert any number-like to Decimal, treating None/0 specially."""
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _safe_date(s) -> Optional[date]:
    """Parse YYYY-MM-DD or return None."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


async def _build_company_lookup(db: AsyncSession) -> dict[str, Company]:
    """Map canonical code → Company row."""
    rows = (await db.execute(select(Company))).scalars().all()
    return {c.code.lower(): c for c in rows if c.code}


async def import_loans(
    json_path: Path,
    apply: bool,
) -> None:
    """Read JSON, map to companies, insert/update in cp_loans."""

    if not json_path.is_file():
        sys.exit(f"❌ JSON file not found: {json_path}")

    with open(json_path, encoding="utf-8") as f:
        loans_raw = json.load(f)

    if not isinstance(loans_raw, list):
        sys.exit("❌ JSON file must be an array of loan objects")


    async with AsyncSessionLocal() as db:
        # Build company code → Company map
        co_map = await _build_company_lookup(db)
        missing_codes = sorted(
            {c for c in COMPANY_NAME_TO_CODE.values() if c not in co_map}
        )
        if missing_codes:
            sys.exit(
                f"❌ The following canonical codes are missing in companies "
                f"table: {missing_codes}. Run migration 0003 first."
            )

        # Validate all loan companies map cleanly
        unknown_companies: set[str] = set()
        for ln in loans_raw:
            co_name = (ln.get("company") or "").strip()
            if co_name not in COMPANY_NAME_TO_CODE:
                unknown_companies.add(co_name)
        if unknown_companies:
            pass

        # Look up existing loan_codes to determine insert vs update
        existing_codes = set(
            (await db.execute(select(CreditPortfolioLoan.loan_code))).scalars().all()
        )

        inserted = 0
        updated = 0
        skipped = 0
        per_company: dict[str, int] = {}

        for ln in loans_raw:
            co_name = (ln.get("company") or "").strip()
            code = COMPANY_NAME_TO_CODE.get(co_name)
            if code is None:
                skipped += 1
                continue
            company = co_map.get(code)
            if company is None:
                skipped += 1
                continue
            per_company[code] = per_company.get(code, 0) + 1

            loan_code = ln.get("id")
            if not loan_code:
                skipped += 1
                continue

            # Auto-classify lender_type if not set (mostly already set in source)
            lender_type = ln.get("lenderType") or classify_lender(ln.get("bank") or "")

            data = dict(
                loan_code=loan_code,
                company_id=company.id,
                borrower_unit=ln.get("borrowerUnit"),
                bank=ln.get("bank") or "",
                bank_short_name=bank_short_name(ln.get("bank") or ""),
                contract_ref=ln.get("contract"),
                currency=(ln.get("currency") or "").upper(),
                rate=_safe_decimal(ln.get("rate")),
                rate_text=ln.get("rateText"),
                sum_total=_safe_decimal(ln.get("sumTotal")),
                sum_disbursed=_safe_decimal(ln.get("sumDisbursed")),
                debt_currency=_safe_decimal(ln.get("debtCurrency")),
                debt_usd=_safe_decimal(ln.get("debtUsd")),
                date_get=_safe_date(ln.get("dateGet")),
                date_due=_safe_date(ln.get("dateDue")),
                is_guaranteed=bool(ln.get("isGuaranteed")),
                lender_type=lender_type,
                auto_flags={},
                notes=None,
                as_of_date=DEFAULT_AS_OF,
            )

            if apply:
                if loan_code in existing_codes:
                    # Update existing
                    existing = (
                        await db.execute(
                            select(CreditPortfolioLoan).where(
                                CreditPortfolioLoan.loan_code == loan_code
                            )
                        )
                    ).scalar_one()
                    for k, v in data.items():
                        if k == "loan_code":
                            continue
                        setattr(existing, k, v)
                    updated += 1
                else:
                    # Insert new
                    db.add(CreditPortfolioLoan(**data))
                    inserted += 1
            else:
                # Dry-run
                if loan_code in existing_codes:
                    updated += 1
                else:
                    inserted += 1

        if apply:
            try:
                await db.commit()
            except Exception as e:
                await db.rollback()
                sys.exit(f"❌ DB error during commit: {e}")
        else:
            await db.rollback()

        # ─── Summary ───
        for code in sorted(per_company.keys(), key=lambda c: -per_company[c]):
            co_map[code]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import credit portfolio loans from decoded JSON file"
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=Path(__file__).parent / "cp_loans_all.json",
        help="Path to JSON file with loans (default: backend/app/scripts/cp_loans_all.json)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually commit changes (default: dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without committing (default behavior)",
    )
    args = parser.parse_args()

    apply = bool(args.apply) and not bool(args.dry_run)
    if not apply:
        pass

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    asyncio.run(import_loans(args.json, apply))


if __name__ == "__main__":
    main()
