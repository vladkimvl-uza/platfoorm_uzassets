"""re-seed procurement_closures with UMK derived-price rows

Revision ID: 9b0_procurement_reseed_umk
Revises: 9aZ_fk_indexes
Create Date: 2026-06-26

Пере-сидит procurement_closures из обновлённого
procurement_closures_q1_2026.json (8 346 строк). Добавлены 89 строк UMK,
у которых в источнике пустая «Unit price», но цена восстановлена как
сумма_контракта / количество. Для 57 затронутых product_code пересчитаны
median (market_avg) + deviation_pct.

upgrade(): DELETE существующих source='q1-2026-xlsx' → re-INSERT из JSON.
Идемпотентно по содержимому: всегда приводит к актуальному снимку сида.
"""
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b0_procurement_reseed_umk"
down_revision: Union[str, None] = "9aZ_fk_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "seed"

_PURCHASE_TYPE_NORM = {
    "E-SHOP":                    "e_shop",
    "E_STORE":                   "e_shop",
    "AUCTION":                   "auction",
    "BEST_OFFER":                "best_offer",
    "OTHER_COMPETITIVE_METHODS": "competitive",
}


def _norm_purchase_type(s):
    if not s:
        return None
    return _PURCHASE_TYPE_NORM.get(str(s).upper().strip(), str(s).strip()[:32])


def upgrade() -> None:
    bind = op.get_bind()

    seed_path = _SEED_DIR / "procurement_closures_q1_2026.json"
    if not seed_path.is_file():
        print(f"  ⚠ Procurement closures seed not found: {seed_path} — skipping")
        return

    # Сносим прежние сид-строки (8 257) — заменяем актуальным снимком.
    deleted = bind.execute(sa.text(
        "DELETE FROM procurement_closures WHERE extra->>'source' = 'q1-2026-xlsx' RETURNING id"
    )).fetchall()
    print(f"  Removed {len(deleted)} previous q1-2026-xlsx rows.")

    rows = json.loads(seed_path.read_text(encoding="utf-8"))
    print(f"  Loading {len(rows)} rows from {seed_path.name} ...")

    db_rows = bind.execute(sa.text("SELECT id, code FROM companies")).fetchall()
    by_code = {(r.code or "").lower(): r.id for r in db_rows}
    co_sector_q = bind.execute(sa.text(
        "SELECT c.id, s.code AS sector_code FROM companies c LEFT JOIN sectors s ON s.id = c.sector_id"
    )).fetchall()
    sector_by_co = {r.id: r.sector_code for r in co_sector_q}

    insert_sql = sa.text("""
        INSERT INTO procurement_closures (
            id, company_id, year, closure_date,
            category_id, product_code, product_name,
            unit_price, market_avg, deviation_pct,
            unit, volume, total_amount, saved_amount,
            supplier_name, supplier_inn,
            contract_id, lot_id, platform, purchase_type, region, sector,
            is_clean, is_dirty, extra,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid(), :company_id, :year, :closure_date,
            :category_id, :product_code, :product_name,
            :unit_price, :market_avg, :deviation_pct,
            :unit, :volume, :total_amount, :saved_amount,
            :supplier_name, :supplier_inn,
            :contract_id, :lot_id, :platform, :purchase_type, :region, :sector,
            TRUE, FALSE, CAST(:extra AS jsonb),
            NOW(), NOW()
        )
    """)

    inserted = 0
    skipped_no_co = 0
    BATCH = 500
    batch: list[dict] = []

    for r in rows:
        code = (r.get("co") or "").lower()
        company_id = by_code.get(code)
        if company_id is None:
            skipped_no_co += 1
            continue

        cat_raw = r.get("category_id")
        cat_str = str(int(cat_raw)) if isinstance(cat_raw, (int, float)) and cat_raw is not None else (
            str(cat_raw) if cat_raw is not None else None
        )
        dev = r.get("deviation_pct")
        if dev is not None:
            if dev > 999_999.9999:
                dev = 999_999.9999
            elif dev < -999_999.9999:
                dev = -999_999.9999

        batch.append({
            "company_id":    company_id,
            "year":          int(r.get("year") or 2026),
            "closure_date":  r.get("contract_date"),
            "category_id":   cat_str,
            "product_code":  r.get("product_code"),
            "product_name":  (r.get("product_name") or "")[:1024] or None,
            "unit_price":    r.get("unit_price"),
            "market_avg":    r.get("market_avg"),
            "deviation_pct": dev,
            "unit":          r.get("unit"),
            "volume":        r.get("volume"),
            "total_amount":  r.get("total_amount"),
            "saved_amount":  r.get("saved_amount"),
            "supplier_name": (r.get("supplier_name") or "")[:512] or None,
            "supplier_inn":  r.get("supplier_inn"),
            "contract_id":   None,
            "lot_id":        r.get("lot_id"),
            "platform":      (r.get("platform") or "")[:64] or None,
            "purchase_type": _norm_purchase_type(r.get("purchase_type")),
            "region":        (r.get("region") or "")[:128] or None,
            "sector":        sector_by_co.get(company_id),
            "extra": json.dumps({
                "source": "q1-2026-xlsx",
                "start_summa": r.get("start_summa"),
                "contract_amount": r.get("contract_amount"),
                "saved_percent": r.get("saved_percent"),
                "product_type": r.get("product_type"),
            }, ensure_ascii=False),
        })
        if len(batch) >= BATCH:
            bind.execute(insert_sql, batch)
            inserted += len(batch)
            batch = []
    if batch:
        bind.execute(insert_sql, batch)
        inserted += len(batch)

    print(f"  ✓ procurement_closures re-seeded: {inserted} inserted · {skipped_no_co} skipped (no company)")


def downgrade() -> None:
    # Откат: удаляем актуальный снимок (предыдущий сид восстанавливается
    # повторным накатом 9aI вручную при необходимости).
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM procurement_closures WHERE extra->>'source' = 'q1-2026-xlsx'"))
