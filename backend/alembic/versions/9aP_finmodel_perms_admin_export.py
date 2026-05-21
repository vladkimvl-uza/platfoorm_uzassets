"""Seed missing finmodel.admin and finmodel.export permission codes.

Audit (post-v3) found `finmodel.admin` is referenced by PUT /macro and
`finmodel.export` is referenced by future export UI gating, but neither
was present in the permissions table. Owners + admin roles still bypass
via `has_effective_permission`, but explicit grant requires the codes
to exist for the role-permissions join.

Revision ID: 9aP_finmodel_perms_admin_export
Revises:     9aO_finmodel_seed_full_excel
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9aP_finmodel_perms_admin_export"
down_revision: Union[str, None] = "9aO_finmodel_seed_full_excel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO permissions (id, code, name, module, action)
        VALUES
          (gen_random_uuid(), 'finmodel.admin',  'Администрирование финмодели', 'finmodel', 'admin'),
          (gen_random_uuid(), 'finmodel.export', 'Экспорт финмодели',           'finmodel', 'export')
        ON CONFLICT (code) DO NOTHING
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DELETE FROM permissions WHERE code IN ('finmodel.admin', 'finmodel.export')
    """))
