"""add admin.users permission for RBAC management

Revision ID: 0009_admin_users_perm
Revises: 0008_cleanup_legacy_financials
Create Date: 2026-05-04 19:00:00.000000

The RBAC admin endpoints (manage users, assign roles, reset passwords)
require the `admin.users` permission. This adds it and grants it
exclusively to the `admin` role + auto-grants to is_owner=true users
(handled at code level in security.py — owner bypasses permission checks).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0009_admin_users_perm"
down_revision: Union[str, None] = "0008_cleanup_legacy_financials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the permission (idempotent — uses ON CONFLICT)
    op.execute("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at)
        VALUES
          (gen_random_uuid(), 'admin.users',     'Управление пользователями',  'admin', 'admin', 'Создание/удаление пользователей, назначение ролей',          NOW(), NOW()),
          (gen_random_uuid(), 'admin.audit',     'Просмотр журнала аудита',    'admin', 'view',  'Просмотр audit_log',                                          NOW(), NOW()),
          (gen_random_uuid(), 'admin.role_edit', 'Редактирование ролей',        'admin', 'edit',  'Редактирование набора прав ролей',                            NOW(), NOW())
        ON CONFLICT (code) DO NOTHING
    """)

    # Grant all 3 admin.* permissions to the `admin` role
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.code = 'admin'
          AND p.code IN ('admin.users', 'admin.audit', 'admin.role_edit')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permission
        WHERE permission_id IN (
            SELECT id FROM permissions
            WHERE code IN ('admin.users', 'admin.audit', 'admin.role_edit')
        )
    """)
    op.execute("""
        DELETE FROM permissions
        WHERE code IN ('admin.users', 'admin.audit', 'admin.role_edit')
    """)
