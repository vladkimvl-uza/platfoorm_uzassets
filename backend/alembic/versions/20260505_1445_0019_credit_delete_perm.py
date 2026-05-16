"""credit_portfolio_permissions: add credit.delete

Revision ID: 0019_credit_delete_perm
Revises: 0018_credit_portfolio
Create Date: 2026-05-05 14:45:00.000000

The base permissions migration (0002) already seeded credit.view / credit.edit /
credit.import. The dedicated DELETE permission was missing because the
monolith handled deletion via "edit" with a soft-delete flag. The new
backend separates concerns: editors can update fields, only the `debt`
role + admins can soft-delete a loan.

NOTE: This migration mirrors the INSERT pattern from migration 0002 exactly:
  - `permissions.id` requires explicit `gen_random_uuid()` (no DB default)
  - link table is `role_permission` (singular), composite (role_id, permission_id) PK
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0019_credit_delete_perm"
down_revision: Union[str, None] = "0018_credit_portfolio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Insert the new permission row (idempotent via ON CONFLICT)
    op.execute("""
        INSERT INTO permissions (id, code, module, action, name, description, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'credit.delete', 'credit', 'delete',
            'Удаление кредитов',
            'Soft-delete записей в кредитном портфеле',
            NOW(), NOW()
        )
        ON CONFLICT (code) DO NOTHING
    """)

    # 2. Grant to the `debt` role (debt manager).
    # `admin` and `is_owner=True` users bypass the matrix in require_permission,
    # so they implicitly have everything — no row needed for them here.
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r, permissions p
        WHERE p.code = 'credit.delete'
          AND r.code IN ('debt')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permission
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'credit.delete')
    """)
    op.execute("DELETE FROM permissions WHERE code = 'credit.delete'")
