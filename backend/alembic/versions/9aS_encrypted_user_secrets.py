"""encrypt password_history + mfa_recovery_codes_hashed (P2-3, P2-4)

Adds Fernet-encrypted columns alongside the legacy plaintext-hash columns.
The application:
  - On READ: tries new column first, falls back to legacy column
  - On WRITE: writes to new column AND clears legacy column

Legacy columns are kept for one release cycle so a rollback doesn't lock
out users; a follow-up migration (next pack) drops them once verified.

Both columns hold bcrypt hashes (one-way), so the encryption is defense
in depth against backup-on-disk exfiltration (slows offline brute force
by requiring the Fernet key in addition to the backup file).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9aS_encrypted_user_secrets"
down_revision: Union[str, None] = "9aR_cp_payments_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Two new nullable columns. No backfill in this migration — the app
    # lazily migrates on next write (password change / recovery regen).
    op.add_column(
        "users",
        sa.Column("password_history_enc", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("mfa_recovery_codes_enc", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_recovery_codes_enc")
    op.drop_column("users", "password_history_enc")
