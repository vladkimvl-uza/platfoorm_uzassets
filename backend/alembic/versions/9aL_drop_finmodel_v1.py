"""Drop FinModel v1 single-row storage table.

Per `finmodel-v2-handoff.md` Phase 0.5: old v1 was UzAirports-only, locked to
monolith-lifted ~8000-line JS blob with Firebase-style RTDB JSONB storage.
v2 will replace with proper NSBU template + per-(company,year) rows + formula
engine + audit. Migration upgrade DROPs the old table; downgrade is a no-op
(no going back — old schema permanently retired).

Backup of finmodel_storage.data was taken to:
  backups/finmodel-v1-YYYYMMDD-HHMMSS/finmodel_data.json
(142KB, 23 companies, 2021-2025 facts auto-filled from Financials before drop)

Revision ID: 9aL_drop_finmodel_v1
Revises:     9aK_year_registry_seed
"""
from typing import Sequence, Union

from alembic import op

revision: str = "9aL_drop_finmodel_v1"
down_revision: Union[str, None] = "9aK_year_registry_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS finmodel_storage CASCADE")


def downgrade() -> None:
    # Old v1 schema permanently retired. No rollback.
    pass
