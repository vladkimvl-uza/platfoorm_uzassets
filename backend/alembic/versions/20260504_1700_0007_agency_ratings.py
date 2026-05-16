"""create agency_ratings table for external credit + ESG ratings

Revision ID: 0007_agency_ratings
Revises: 0006_split_projects
Create Date: 2026-05-04 17:00:00.000000

The existing `ratings` table (from migration 0001) is designed for COMPOSITE
ratings — internal scores computed from multiple metrics, with quarterly
versions and dimension breakdowns. That stays as-is for future use.

This migration adds a separate `agency_ratings` table for EXTERNAL public
ratings published by rating agencies (Fitch, S&P, Moody's, Sustainable Fitch,
S&P ESG, CDP, MSCI, Sustainalytics).

Each row represents ONE rating from ONE agency for ONE company.
Discriminator `is_esg` separates ESG from credit ratings.

Storage migration source: `/pf/ratings` in Firebase.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_agency_ratings"
down_revision: Union[str, None] = "0006_split_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agency_ratings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agency", sa.String(64), nullable=False),
        # Discriminator — set at insert based on agency name
        sa.Column("is_esg", sa.Boolean(), server_default=sa.false(), nullable=False),

        # Core rating fields (all from monolith: rating/outlook/date/score/url)
        sa.Column("rating", sa.String(16), nullable=True),    # "BB", "B+", "AA-", "3" (numeric SF)
        sa.Column("outlook", sa.String(32), nullable=True),   # "Stable", "Positive", "Negative", "Developing"
        sa.Column("score",  sa.String(16), nullable=True),    # numeric score for agencies that publish it
        sa.Column("rating_date_text", sa.String(64), nullable=True),  # free-form: "июл 2025"
        sa.Column("rating_date",      sa.Date(), nullable=True),       # parsed when possible

        sa.Column("report_url", sa.String(2000), nullable=True),

        # Legacy carry
        sa.Column("legacy_id", sa.String(96), nullable=True, unique=True),
        sa.Column("legacy_board_id", sa.String(64), nullable=True),
        sa.Column("extra", sa.dialects.postgresql.JSONB(), nullable=True),
    )

    # One rating per (company, agency) — matches monolith `findOne(boardId, agency)` semantics
    op.create_unique_constraint(
        "ux_agency_ratings_co_agency", "agency_ratings", ["company_id", "agency"]
    )

    op.create_index("ix_agency_ratings_company", "agency_ratings", ["company_id"])
    op.create_index("ix_agency_ratings_agency",  "agency_ratings", ["agency"])
    op.create_index("ix_agency_ratings_is_esg",  "agency_ratings", ["is_esg"])
    op.create_index("ix_agency_ratings_date",
                    "agency_ratings", [sa.text("rating_date DESC NULLS LAST")])


def downgrade() -> None:
    op.drop_index("ix_agency_ratings_date",    table_name="agency_ratings")
    op.drop_index("ix_agency_ratings_is_esg",  table_name="agency_ratings")
    op.drop_index("ix_agency_ratings_agency",  table_name="agency_ratings")
    op.drop_index("ix_agency_ratings_company", table_name="agency_ratings")
    op.drop_constraint("ux_agency_ratings_co_agency", "agency_ratings", type_="unique")
    op.drop_table("agency_ratings")
