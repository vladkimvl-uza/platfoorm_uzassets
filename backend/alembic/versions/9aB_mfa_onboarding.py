"""mfa onboarding skip column

Revision ID: 9aB_mfa_onboarding
Revises: 9aA_telegram_2fa
Create Date: 2026-05-14

Pack 13.3 - adds users.mfa_onboarding_skipped_until (timestamptz, NULL).
"""
from alembic import op


revision = "9aB_mfa_onboarding"
down_revision = "9aA_telegram_2fa"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE users ADD COLUMN mfa_onboarding_skipped_until TIMESTAMPTZ NULL;
        EXCEPTION WHEN duplicate_column THEN NULL; END $$;
    """)
    op.execute("""
        COMMENT ON COLUMN users.mfa_onboarding_skipped_until IS
        'When user skipped MFA onboarding; wizard suppressed until this timestamp passes';
    """)


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_onboarding_skipped_until;")