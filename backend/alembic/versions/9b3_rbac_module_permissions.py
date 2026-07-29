"""align RBAC module permission catalog

Revision ID: 9b3_rbac_module_permissions
Revises: 9b2_procurement_flag_dirty
Create Date: 2026-07-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b3_rbac_module_permissions"
down_revision: Union[str, None] = "9b2_procurement_flag_dirty"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MODULE_PERMISSIONS = [
    ("dashboard.view", "dashboard", "view", "View dashboard"),
    ("dashboard.edit", "dashboard", "edit", "Edit dashboard"),
    ("dashboard.export", "dashboard", "export", "Export dashboard"),
    ("dashboard.manage", "dashboard", "manage", "Manage dashboard"),
    ("investment.export", "investment", "export", "Export investments"),
    ("investment.manage", "investment", "manage", "Manage investments"),
    ("procurement_analysis.view", "procurement_analysis", "view", "View procurement analysis"),
    ("procurement_analysis.edit", "procurement_analysis", "edit", "Edit procurement analysis"),
    ("procurement_analysis.export", "procurement_analysis", "export", "Export procurement analysis"),
    ("procurement_analysis.manage", "procurement_analysis", "manage", "Manage procurement analysis"),
    ("consultants.view", "consultants", "view", "View consultants"),
    ("consultants.edit", "consultants", "edit", "Edit consultants"),
    ("consultants.export", "consultants", "export", "Export consultants"),
    ("consultants.manage", "consultants", "manage", "Manage consultants"),
    ("pmo.view", "pmo", "view", "View PMO"),
    ("pmo.edit", "pmo", "edit", "Edit PMO"),
    ("pmo.export", "pmo", "export", "Export PMO"),
    ("pmo.manage", "pmo", "manage", "Manage PMO"),
    ("monitoring.view", "monitoring", "view", "View monitoring"),
    ("monitoring.edit", "monitoring", "edit", "Edit monitoring"),
    ("monitoring.export", "monitoring", "export", "Export monitoring"),
    ("monitoring.manage", "monitoring", "manage", "Manage monitoring"),
    ("ai.view", "ai", "view", "Use AI assistant"),
    ("ai.manage", "ai", "manage", "Manage AI assistant"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for code, module, action, name in MODULE_PERMISSIONS:
        bind.execute(sa.text(
            """
            INSERT INTO permissions (id, code, name, module, action, created_at, updated_at)
            VALUES (gen_random_uuid(), :code, :name, :module, :action, now(), now())
            ON CONFLICT (code) DO UPDATE
            SET module = EXCLUDED.module,
                action = EXCLUDED.action,
                updated_at = now()
            """
        ), {"code": code, "name": name, "module": module, "action": action})

    # Admin role should receive newly introduced catalog permissions.
    bind.execute(sa.text(
        """
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin'
          AND p.code = ANY(:codes)
        ON CONFLICT DO NOTHING
        """
    ), {"codes": [code for code, *_ in MODULE_PERMISSIONS]})

    # Preserve legacy AI access: roles that had ai.chat can pass ai.view gates.
    bind.execute(sa.text(
        """
        INSERT INTO role_permission (role_id, permission_id)
        SELECT rp.role_id, p_view.id
        FROM role_permission rp
        JOIN permissions p_chat ON p_chat.id = rp.permission_id
        JOIN permissions p_view ON p_view.code = 'ai.view'
        WHERE p_chat.code = 'ai.chat'
        ON CONFLICT DO NOTHING
        """
    ))

    # Existing monitoring role is a broad read role; give it the route gate.
    bind.execute(sa.text(
        """
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r JOIN permissions p ON p.code = 'monitoring.view'
        WHERE r.code = 'monitoring'
        ON CONFLICT DO NOTHING
        """
    ))


def downgrade() -> None:
    bind = op.get_bind()
    codes = [code for code, *_ in MODULE_PERMISSIONS]
    bind.execute(sa.text(
        """
        DELETE FROM role_permission
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = ANY(:codes))
        """
    ), {"codes": codes})
    bind.execute(sa.text(
        "DELETE FROM permissions WHERE code = ANY(:codes)"
    ), {"codes": codes})
