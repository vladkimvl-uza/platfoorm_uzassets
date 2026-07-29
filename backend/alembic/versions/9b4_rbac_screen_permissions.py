"""RBAC: собственные права экранов министра / обзора / SOE Health / удельной себестоимости

Зачем. Четыре самостоятельных экрана сидели на чужих правах:

  * /executive-dashboard, /soe-health, /unit-cost — все три на financials.view.
    Выдал роли «Финансы» — человек получил и экран министра, и методику МВФ,
    и удельную себестоимость. Управлять ими по отдельности было нечем.
  * /executive-overview требовал projects.view — кода, которого НЕТ в каталоге
    и нет ни у одной роли. Экран открывался только владельцу и роли admin
    (super-admin bypass), для всех остальных был закрыт наглухо.

Плюс обратный случай: tasks.manage спрашивают три бэкенд-гейта (направления,
storage_admin, направления консультантов), а кода в каталоге нет — выдать его
роли было невозможно, работал только bypass владельца.

Раздача ролям сохраняет фактический доступ 1:1: новое право просмотра получают
ровно те роли, у которых сегодня есть право, на котором экран гейтился. Единое
исключение — exec_overview.view: сегодня экран не открывается никому, и это та
самая поломка, которую чиним, поэтому право выдаётся ролям с tasks.view (обзор
показывает проекты/дедлайны в границах скоупа пользователя).

Revision ID: 9b4_rbac_screen_permissions
Revises: 9b3_rbac_module_permissions
Create Date: 2026-07-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b4_rbac_screen_permissions"
down_revision: Union[str, None] = "9b3_rbac_module_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (код, модуль, действие, англ. название в каталоге)
SCREEN_PERMISSIONS = [
    ("exec_dashboard.view", "exec_dashboard", "view", "View executive dashboard"),
    ("exec_overview.view", "exec_overview", "view", "View portfolio executive overview"),
    ("soe_health.view", "soe_health", "view", "View SOE health check"),
    # Пороги методики МВФ правятся через PUT /financials/soe-health/params.
    ("soe_health.edit", "soe_health", "edit", "Edit SOE health check thresholds"),
    ("unit_cost.view", "unit_cost", "view", "View unit cost"),
    # PUT /unit-cost/prices и PUT /unit-cost/companies/{code}.
    ("unit_cost.edit", "unit_cost", "edit", "Edit unit cost data"),
    # Гейт есть давно (directions/storage_admin/consultants), кода в каталоге не было.
    ("tasks.manage", "tasks", "manage", "Manage task directions and storage"),
]

# Код → роли, которым он выдаётся при ПЕРВОМ появлении в каталоге.
# admin получает всё (каталожная конвенция; фактически он и так super-admin).
ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    # Держатели financials.view сегодня: admin, company_admin, organization, viewer.
    "exec_dashboard.view": ("admin", "company_admin", "organization", "viewer"),
    "soe_health.view": ("admin", "company_admin", "organization", "viewer"),
    "unit_cost.view": ("admin", "company_admin", "organization", "viewer"),
    # Держатели financials.edit сегодня: admin, company_admin, organization.
    "soe_health.edit": ("admin", "company_admin", "organization"),
    "unit_cost.edit": ("admin", "company_admin", "organization"),
    # Обзор портфеля: держатели tasks.view (проекты/дедлайны), скоуп режется в сервисе.
    "exec_overview.view": ("admin", "company_admin", "organization", "viewer"),
    # Управление направлениями/хранилищем — уровень администратора платформы.
    "tasks.manage": ("admin",),
}


def upgrade() -> None:
    bind = op.get_bind()

    # Что уже есть в каталоге — фиксируем ДО вставки. Раздавать права ролям
    # можно только за коды, которых раньше не было: иначе повторный прогон
    # вернул бы права, снятые администратором вручную.
    known = set(
        bind.execute(sa.text("SELECT code FROM permissions")).scalars().all()
    )
    created_codes = [code for code, *_ in SCREEN_PERMISSIONS if code not in known]

    for code, module, action, name in SCREEN_PERMISSIONS:
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

    for code in created_codes:
        roles = ROLE_GRANTS.get(code, ("admin",))
        bind.execute(sa.text(
            """
            INSERT INTO role_permission (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r CROSS JOIN permissions p
            WHERE r.code = ANY(:roles) AND p.code = :code
            ON CONFLICT DO NOTHING
            """
        ), {"roles": list(roles), "code": code})


def downgrade() -> None:
    bind = op.get_bind()
    codes = [code for code, *_ in SCREEN_PERMISSIONS]
    bind.execute(sa.text(
        """
        DELETE FROM role_permission
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = ANY(:codes))
        """
    ), {"codes": codes})
    bind.execute(sa.text(
        "DELETE FROM permissions WHERE code = ANY(:codes)"
    ), {"codes": codes})
