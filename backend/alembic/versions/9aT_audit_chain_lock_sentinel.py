"""audit chain serialization via sentinel-row lock

Replaces pg_advisory_xact_lock — under load the advisory lock empirically
allowed two concurrent inserts to share the same prev_hash (chain break,
caught by uq_audit_log_prev_hash UNIQUE constraint).

Mechanism: every writer does `SELECT id FROM audit_chain_lock WHERE id=1
FOR UPDATE` before reading the chain head. PG row-level exclusive lock
serializes writers reliably across separate connections, separate
transactions, separate workers — unlike advisory locks which had a
subtle interaction with our session/pool configuration.

The sentinel table has exactly one row that is never updated or deleted.
SELECT FOR UPDATE on it is a well-defined row-lock primitive.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9aT_audit_chain_lock_sentinel"
down_revision: Union[str, None] = "9aS_encrypted_user_secrets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_chain_lock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note", sa.String(255), nullable=True),
    )
    op.execute(
        "INSERT INTO audit_chain_lock (id, note) VALUES "
        "(1, 'audit chain writer serialization sentinel — never UPDATE/DELETE this row')"
    )


def downgrade() -> None:
    op.drop_table("audit_chain_lock")
