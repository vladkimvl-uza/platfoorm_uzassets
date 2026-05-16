"""Yearly USD rates + UZ Republic budget per year (Pack 7.35)

Revision ID: 0025_yearly_rates_uz_budget
Revises: 7b2c0ffe4ai0
Create Date: 2026-05-11

Adds:
  • uz_budget_trln column to year_registry (доходная часть бюджета РУ, трлн сум)

Seeds default values for 2021–2026 (sourced from CBU + World Bank):
  Year  USD rate (UZS/USD)  UZ Budget (трлн UZS)
  2021  10 610.00           230.0
  2022  11 050.00           260.0
  2023  11 420.00           290.0
  2024  12 650.91           320.0
  2025  12 576.41           350.0
  2026  12 200.00           380.0

These match the hardcoded fallbacks in Pack 7.34's useCurrencyConverter.ts
and the legacy _UZ_BUDGET_TRLN dict in _pack5_blocks.py.
"""
from alembic import op
import sqlalchemy as sa


revision = "0025_yearly_rates_uz_budget"
down_revision = "7b2c0ffe4ai0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add column
    op.add_column(
        "year_registry",
        sa.Column("uz_budget_trln", sa.Numeric(12, 4), nullable=True),
    )

    # 2. Ensure all 6 target years exist (2021–2026). Year 2021 and 2022
    # may not have been seeded in the initial migration (which only added
    # 2023–2026).
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO year_registry (id, year, is_closed, created_at, updated_at)
            VALUES
              (gen_random_uuid(), 2021, TRUE, NOW(), NOW()),
              (gen_random_uuid(), 2022, TRUE, NOW(), NOW())
            ON CONFLICT (year) DO NOTHING;
            """
        )
    )

    # 3. Update USD rates + budget for 2021–2026.
    # Pattern: UPDATE row by year. Uses COALESCE to NOT overwrite a value
    # that an admin may have already manually set via the API.
    seeds = [
        (2021, 10610.00, 230.0),
        (2022, 11050.00, 260.0),
        (2023, 11420.00, 290.0),
        (2024, 12650.91, 320.0),
        (2025, 12576.41, 350.0),
        (2026, 12200.00, 380.0),
    ]
    for year, usd_rate, budget in seeds:
        bind.execute(
            sa.text(
                """
                UPDATE year_registry
                SET
                  usd_rate        = COALESCE(usd_rate, :usd_rate),
                  uz_budget_trln  = COALESCE(uz_budget_trln, :budget),
                  updated_at      = NOW()
                WHERE year = :year
                """
            ),
            {"year": year, "usd_rate": usd_rate, "budget": budget},
        )


def downgrade() -> None:
    # Drop the column (data loss).
    op.drop_column("year_registry", "uz_budget_trln")
