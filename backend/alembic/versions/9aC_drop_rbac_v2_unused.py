"""Drop unused RBAC v2 tables (Pack 145 — RBAC v3 cleanup).

Revision ID: 9aC_drop_rbac_v2_unused
Revises: 9aB_mfa_onboarding
Create Date: 2026-05-16

После аудита (см. C1) остатки RBAC v2 признаны мёртвым кодом — их API не
вызывается фронтом, а боевой gate (security.require_permission) их не учитывал.
Удаляются:
  * user_permission_grant     — direct user grants (UI не управлял)
  * user_module_visibility    — module hide overrides (UI не управлял)
  * permission_template       — reusable bundles (UI не управлял)
  * group_role                — роли группе (UI не поддерживал)
  * rbac_change_log           — отдельный аудит (есть общий audit_log)

ОСТАЁТСЯ:
  * group_permission_grant — единственная реально используемая таблица:
    через неё модель Group выдаёт permissions сверх ролевых, и теперь
    эти grants участвуют в has_effective_permission (фикс C1).

Также удаляются 4 seed-template из permission_template (заодно с таблицей).
"""
from alembic import op


revision = "9aC_drop_rbac_v2_unused"
down_revision = "9aB_mfa_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_rcl_type_time")
    op.execute("DROP INDEX IF EXISTS ix_rcl_subject")
    op.execute("DROP TABLE IF EXISTS rbac_change_log CASCADE")

    op.execute("DROP TABLE IF EXISTS permission_template CASCADE")

    op.execute("DROP TABLE IF EXISTS group_role CASCADE")

    op.execute("DROP INDEX IF EXISTS ix_umv_user")
    op.execute("DROP TABLE IF EXISTS user_module_visibility CASCADE")

    op.execute("DROP INDEX IF EXISTS ix_upg_expires")
    op.execute("DROP INDEX IF EXISTS ix_upg_code")
    op.execute("DROP INDEX IF EXISTS ix_upg_user")
    op.execute("DROP TABLE IF EXISTS user_permission_grant CASCADE")


def downgrade() -> None:
    """Эта миграция не имеет осмысленного отката.

    Таблицы можно пересоздать только повторным накатыванием 9a1_rbac_granular,
    но данные потеряны. Поэтому downgrade — no-op (с warning в логе).
    """
    op.execute(
        "DO $$ BEGIN RAISE NOTICE "
        "'9aC_drop_rbac_v2_unused: downgrade is a no-op (data already lost)'; END $$;"
    )
