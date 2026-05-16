"""sectors permissions

Revision ID: 0011_sectors_perms
Revises: 0010_canonical_names
Create Date: 2026-05-04 21:00:00.000000

Adds CRUD permissions for sectors so they can be managed via UI just
like companies. Grants all sector permissions to the `admin` role.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0011_sectors_perms"
down_revision: Union[str, None] = "0010_canonical_names"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at)
        VALUES
          (gen_random_uuid(), 'sectors.view',   'Просмотр секторов',         'sectors', 'view',   'Просмотр списка секторов',                NOW(), NOW()),
          (gen_random_uuid(), 'sectors.create', 'Создание секторов',          'sectors', 'create', 'Создание новых секторов',                NOW(), NOW()),
          (gen_random_uuid(), 'sectors.edit',   'Редактирование секторов',    'sectors', 'edit',   'Изменение названий и порядка секторов',  NOW(), NOW()),
          (gen_random_uuid(), 'sectors.delete', 'Удаление секторов',          'sectors', 'delete', 'Удаление пустых секторов',                NOW(), NOW())
        ON CONFLICT (code) DO NOTHING;
    """)

    # Grant all 4 sector permissions to admin role
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.code = 'admin'
          AND p.code IN ('sectors.view', 'sectors.create', 'sectors.edit', 'sectors.delete')
        ON CONFLICT DO NOTHING;
    """)

    # Grant sectors.view to all roles that already have companies.view
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT DISTINCT rp.role_id, p_view.id
        FROM role_permission rp
        JOIN permissions p_companies ON p_companies.id = rp.permission_id
                                     AND p_companies.code = 'companies.view'
        CROSS JOIN permissions p_view
        WHERE p_view.code = 'sectors.view'
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permission WHERE permission_id IN (
            SELECT id FROM permissions WHERE code LIKE 'sectors.%'
        );
        DELETE FROM permissions WHERE code LIKE 'sectors.%';
    """)
