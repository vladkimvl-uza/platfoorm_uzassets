"""credit_portfolio: cp_loans + cp_fx_rates tables

Revision ID: 0018_credit_portfolio
Revises: 0017_financial_models
Create Date: 2026-05-05 14:30:00.000000

Migrates the "Кредитный портфель" module from the monolith. Schema mirrors
the monolith data structure 1:1 — see CP_LOANS_*_DEFAULT in index.html
line 24121+.

The old placeholder tables (loans, loan_archive, credit_portfolio_meta)
were never created in any prior migration, so this script just defines
the new tables. We drop them defensively in case they were created
manually during dev.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from typing import Sequence, Union


revision: str = "0018_credit_portfolio"
down_revision: Union[str, None] = "0017_financial_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Defensive cleanup of placeholder tables (never migrated, but might
    # exist from manual dev experimentation)
    op.execute("DROP TABLE IF EXISTS loan_archive CASCADE")
    op.execute("DROP TABLE IF EXISTS credit_portfolio_meta CASCADE")
    op.execute("DROP TABLE IF EXISTS loans CASCADE")

    # ─── cp_loans ──────────────────────────────────────────────────
    op.create_table(
        "cp_loans",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "loan_code",
            sa.String(32),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("borrower_unit", sa.String(255), nullable=True),
        sa.Column("bank", sa.String(255), nullable=False, index=True),
        sa.Column("bank_short_name", sa.String(128), nullable=True, index=True),
        sa.Column("contract_ref", sa.Text, nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, index=True),
        sa.Column("rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("rate_text", sa.String(255), nullable=True),
        sa.Column("sum_total", sa.Numeric(20, 2), nullable=True),
        sa.Column("sum_disbursed", sa.Numeric(20, 2), nullable=True),
        sa.Column("debt_currency", sa.Numeric(20, 2), nullable=True),
        sa.Column("debt_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("date_get", sa.Date, nullable=True),
        sa.Column("date_due", sa.Date, nullable=True, index=True),
        sa.Column(
            "is_guaranteed",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("lender_type", sa.String(16), nullable=True, index=True),
        sa.Column(
            "auto_flags",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("as_of_date", sa.Date, nullable=True),
        sa.Column("deleted_at", sa.Date, nullable=True, index=True),
        sa.Column(
            "created_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Composite indexes for common query patterns
    op.create_index(
        "ix_cp_loans_co_currency",
        "cp_loans",
        ["company_id", "currency"],
    )
    op.create_index(
        "ix_cp_loans_active",
        "cp_loans",
        ["company_id", "deleted_at"],
    )

    # ─── cp_fx_rates ──────────────────────────────────────────────
    op.create_table(
        "cp_fx_rates",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("as_of_date", sa.Date, nullable=False, index=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("rate_to_uzs", sa.Numeric(20, 6), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("as_of_date", "currency", name="uq_cp_fx_date_cur"),
    )

    # Seed the default FX snapshot — these are the rates as of 01.01.2026
    # used by the monolith CP_RATES_FX constant.
    op.execute("""
        INSERT INTO cp_fx_rates (as_of_date, currency, rate_to_uzs)
        VALUES
            ('2026-01-01', 'USD', 12078.47),
            ('2026-01-01', 'EUR', 14234.48),
            ('2026-01-01', 'CNY', 1723.99),
            ('2026-01-01', 'JPY', 76.0),
            ('2026-01-01', 'SDR', 16520.0),
            ('2026-01-01', 'RUB', 158.0),
            ('2026-01-01', 'UZS', 1.0)
    """)


def downgrade() -> None:
    op.drop_table("cp_fx_rates")
    op.drop_index("ix_cp_loans_active", table_name="cp_loans")
    op.drop_index("ix_cp_loans_co_currency", table_name="cp_loans")
    op.drop_table("cp_loans")
