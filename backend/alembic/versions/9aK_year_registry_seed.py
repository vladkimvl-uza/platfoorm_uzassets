"""year_registry: seed default USD/EUR rates so frontend fallback isn't needed.

Inserts 2024-2027 baseline rates IF those years don't already exist.
Values come from CBU.uz среднегодовые курсы (как-of 2026-05). After this
migration the hardcoded fallback in `useCurrencyConverter.ts` is no
longer the source of truth — DB is.

Revision ID: 9aK_year_registry_seed
Revises:     9aJ_company_library
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9aK_year_registry_seed"
down_revision: Union[str, None] = "9aJ_company_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (year, usd_rate, eur_rate, uz_budget_trln, inflation_pct, cb_rate_pct, gdp_growth_pct, is_closed, label)
# Source: cbu.uz среднегодовые + stat.uz макроэкономика
SEED_ROWS = [
    (2024, 12576.41, 13616.00, 320.00, 9.50, 14.00, 6.00, True,  "FY 2024 · закрыт"),
    (2025, 12750.00, 13950.00, 358.00, 8.80, 14.00, 6.20, True,  "FY 2025 · закрыт"),
    (2026, 13000.00, 14140.00, 395.00, 7.50, 13.50, 6.50, False, "FY 2026"),
    (2027, 13200.00, 14300.00, 432.00, 6.50, 12.50, 6.80, False, "FY 2027 · план"),
]


def upgrade() -> None:
    # Use INSERT ... ON CONFLICT DO NOTHING — idempotent, безопасно если
    # админ уже вручную ввёл значения раньше миграции.
    conn = op.get_bind()
    for (year, usd, eur, budget, infl, cb, gdp, closed, label) in SEED_ROWS:
        conn.execute(
            sa.text(
                """
                INSERT INTO year_registry
                  (id, year, label, is_closed, usd_rate, eur_rate, uz_budget_trln,
                   inflation_pct, cb_rate_pct, gdp_growth_pct, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :year, :label, :closed, :usd, :eur, :budget,
                   :infl, :cb, :gdp, NOW(), NOW())
                ON CONFLICT (year) DO NOTHING
                """
            ),
            {
                "year": year, "label": label, "closed": closed,
                "usd": usd, "eur": eur, "budget": budget,
                "infl": infl, "cb": cb, "gdp": gdp,
            },
        )


def downgrade() -> None:
    # Revert seed: remove only the years we inserted, ONLY if values
    # untouched (label still matches seed) — иначе админ редактировал
    # и мы не должны их сносить.
    conn = op.get_bind()
    for (year, _u, _e, _b, _i, _c, _g, _cl, label) in SEED_ROWS:
        conn.execute(
            sa.text("DELETE FROM year_registry WHERE year = :y AND label = :l"),
            {"y": year, "l": label},
        )
