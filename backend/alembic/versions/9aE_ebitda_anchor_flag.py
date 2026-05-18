"""Mark Узбекнефтегаз as EBITDA anchor via module_flags (Pack 148 A1).

Revision ID: 9aE_ebitda_anchor_flag
Revises: 9aD_groups_per_company_and_roles
Create Date: 2026-05-16

`credit_portfolio._resolve_ebitda` used to hardcode the anchor company
via `Company.code IN ('ung','uzneftgaz','uzbekneftegaz')`. Move that
configuration into Company.module_flags JSON so it can be retargeted
without a code change.

After this migration:
  * Companies with `module_flags->>'ebitda_anchor' = 'true'` are
    treated as the system-wide EBITDA reference (currently expected:
    one row — Узбекнефтегаз).
"""
from alembic import op


revision = "9aE_ebitda_anchor_flag"
down_revision = "9aD_groups_per_company_and_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE companies
           SET module_flags = jsonb_set(
                                  coalesce(module_flags, '{}'::jsonb),
                                  '{ebitda_anchor}',
                                  'true'::jsonb,
                                  true)
         WHERE lower(code) IN ('ung', 'uzneftgaz', 'uzbekneftegaz')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE companies
           SET module_flags = module_flags - 'ebitda_anchor'
         WHERE module_flags ? 'ebitda_anchor'
    """)
