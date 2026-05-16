"""telegram 2fa: users mfa columns + login challenge + outbox + prefs

Revision ID: 9aA_telegram_2fa
Revises: 9a9_partners
Create Date: 2026-05-13

Pack 13.0 — Telegram bot 2FA foundation.
- Adds MFA + telegram fields to users (all encrypted via Fernet at app layer)
- Creates mfa_login_challenge (one-shot codes, TTL 5 min)
- Creates telegram_outbox (async delivery queue for uza-tg-bot worker)
- Creates user_telegram_pref (per-user notification routing prefs)

Idempotent: all CREATE/ADD operations use IF NOT EXISTS where possible.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9aA_telegram_2fa"
down_revision = "9a9_partners"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # ── 1. Enums ───────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE mfa_method_enum AS ENUM ('none', 'telegram', 'totp', 'both');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE telegram_outbox_type_enum AS ENUM ('mfa_code', 'link_confirmation', 'notification', 'test');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE telegram_outbox_status_enum AS ENUM ('pending', 'sent', 'failed', 'discarded');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # ── 2. users.* columns (idempotent) ────────────────────────────────
    cols = [
        ("mfa_enabled",                    "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("mfa_method",                     "mfa_method_enum NOT NULL DEFAULT 'none'"),
        ("mfa_secret_encrypted",           "BYTEA"),                              # future TOTP
        ("mfa_recovery_codes_hashed",      "TEXT[]"),                             # bcrypt hashes
        ("telegram_chat_id_encrypted",     "BYTEA"),
        ("telegram_username",              "VARCHAR(64)"),
        ("telegram_linked_at",             "TIMESTAMP WITH TIME ZONE"),
        ("telegram_link_token_hashed",     "VARCHAR(128)"),                       # one-time
        ("telegram_link_token_expires_at", "TIMESTAMP WITH TIME ZONE"),
    ]
    for name, ddl in cols:
        op.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {name} {ddl};")

    # ── 3. mfa_login_challenge ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS mfa_login_challenge (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hashed  VARCHAR(128) NOT NULL,
            created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at   TIMESTAMP WITH TIME ZONE NOT NULL,
            used_at      TIMESTAMP WITH TIME ZONE,
            attempts     INTEGER NOT NULL DEFAULT 0,
            ip_address   VARCHAR(64),
            user_agent   VARCHAR(256)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_mfa_challenge_user ON mfa_login_challenge(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mfa_challenge_exp  ON mfa_login_challenge(expires_at);")

    # ── 4. telegram_outbox ─────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS telegram_outbox (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type            telegram_outbox_type_enum NOT NULL,
            status          telegram_outbox_status_enum NOT NULL DEFAULT 'pending',
            payload         JSONB NOT NULL,
            inline_buttons  JSONB,
            created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            attempted_at    TIMESTAMP WITH TIME ZONE,
            delivered_at    TIMESTAMP WITH TIME ZONE,
            attempts        INTEGER NOT NULL DEFAULT 0,
            last_error      TEXT,
            tg_message_id   BIGINT
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbox_user    ON telegram_outbox(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbox_status  ON telegram_outbox(status);")
    # Partial index for worker poll: SELECT WHERE status='pending' is the hot path
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbox_pending ON telegram_outbox(created_at) WHERE status='pending';")

    # ── 5. user_telegram_pref ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_telegram_pref (
            user_id              UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            enabled              BOOLEAN NOT NULL DEFAULT TRUE,
            type_assignments     BOOLEAN NOT NULL DEFAULT TRUE,
            type_mentions        BOOLEAN NOT NULL DEFAULT TRUE,
            type_deadlines       BOOLEAN NOT NULL DEFAULT TRUE,
            type_moderation      BOOLEAN NOT NULL DEFAULT TRUE,
            type_broadcasts      BOOLEAN NOT NULL DEFAULT FALSE,
            type_system          BOOLEAN NOT NULL DEFAULT FALSE,
            quiet_hours_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
            quiet_hours_start    TIME    NOT NULL DEFAULT '22:00',
            quiet_hours_end      TIME    NOT NULL DEFAULT '07:00',
            timezone             VARCHAR(64) NOT NULL DEFAULT 'Asia/Tashkent',
            updated_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS user_telegram_pref;")
    op.execute("DROP INDEX IF EXISTS ix_outbox_pending;")
    op.execute("DROP INDEX IF EXISTS ix_outbox_status;")
    op.execute("DROP INDEX IF EXISTS ix_outbox_user;")
    op.execute("DROP TABLE IF EXISTS telegram_outbox;")
    op.execute("DROP TYPE IF EXISTS telegram_outbox_status_enum;")
    op.execute("DROP TYPE IF EXISTS telegram_outbox_type_enum;")
    op.execute("DROP INDEX IF EXISTS ix_mfa_challenge_exp;")
    op.execute("DROP INDEX IF EXISTS ix_mfa_challenge_user;")
    op.execute("DROP TABLE IF EXISTS mfa_login_challenge;")
    for col in ["telegram_link_token_expires_at", "telegram_link_token_hashed", "telegram_linked_at",
                "telegram_username", "telegram_chat_id_encrypted", "mfa_recovery_codes_hashed",
                "mfa_secret_encrypted", "mfa_method", "mfa_enabled"]:
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {col};")
    op.execute("DROP TYPE IF EXISTS mfa_method_enum;")
