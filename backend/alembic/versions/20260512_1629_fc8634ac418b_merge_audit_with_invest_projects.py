"""merge_audit_with_invest_projects

Revision ID: fc8634ac418b
Revises: 0028_invest_projects, 8a1d_audit_log
Create Date: 2026-05-12 16:29:08.535030+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fc8634ac418b"
down_revision: Union[str, None] = ("0028_invest_projects", "8a1d_audit_log")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
