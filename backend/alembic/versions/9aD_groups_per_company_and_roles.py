"""Per-company groups + per-(user,group) roles (Pack 147).

Revision ID: 9aD_groups_per_company_and_roles
Revises: 9aC_drop_rbac_v2_unused
Create Date: 2026-05-16

Schema:
  * `groups.company_id` UUID FK companies(id) ON DELETE CASCADE, UNIQUE
    (1:1 group↔company; NULL allowed for future free-form groups).
  * `user_group_role` (user_id, group_id, role_id) PK (user_id, group_id) —
    "user X in group Y has role Z".

Seed:
  * Role `viewer` (sort_order=200, is_system) with kpi/bp/companies/
    governance/esg/financials/ratings/tasks .view permissions — used as
    safe default for migrated users.

Data migration:
  1. Auto-create a Group for each existing Company (code=company.code,
     name=company.name_ru, company_id=company.id) unless one already
     exists with that company_id.
  2. For each user with `allowed_companies` JSONB array — match each
     entry against companies.id OR companies.code (case-insens), insert
     (user_id, group_id, viewer.id) into user_group_role.
  3. Same for users.organization_id.
  4. DROP COLUMN users.allowed_companies.

Downgrade:
  No-op (allowed_companies cannot be reconstructed losslessly from
  user_group_role since role mapping isn't 1:1 with the old shape).
  Restore from backup if needed.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9aD_groups_per_company_and_roles"
down_revision = "9aC_drop_rbac_v2_unused"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ───── 1. Schema additions ─────
    op.add_column(
        "groups",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_groups_company_id", "groups", "companies",
        ["company_id"], ["id"], ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_groups_company_id", "groups", ["company_id"])
    op.create_index("ix_groups_company_id", "groups", ["company_id"])

    op.create_table(
        "user_group_role",
        sa.Column("user_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"],  ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"],  ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "group_id"),
    )
    op.create_index("ix_user_group_role_user",  "user_group_role", ["user_id"])
    op.create_index("ix_user_group_role_group", "user_group_role", ["group_id"])
    op.create_index("ix_user_group_role_role",  "user_group_role", ["role_id"])

    # ───── 2. Seed viewer role ─────
    op.execute("""
        INSERT INTO roles (id, code, name_ru, is_system, is_active, sort_order, created_at, updated_at)
        SELECT gen_random_uuid(), 'viewer', 'Наблюдатель', true, true, 200, now(), now()
         WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = 'viewer')
    """)

    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p
            ON p.code IN (
              'kpi.view','bp.view','companies.view','governance.view',
              'esg.view','financials.view','ratings.view','tasks.view'
            )
         WHERE r.code = 'viewer'
        ON CONFLICT DO NOTHING
    """)

    # ───── 3. Auto-create group per existing company ─────
    # Use a name suffix only if same code is already taken by an unrelated group.
    op.execute("""
        INSERT INTO groups (id, code, name, company_id, created_at, updated_at)
        SELECT gen_random_uuid(),
               CASE
                 WHEN EXISTS (SELECT 1 FROM groups gg WHERE gg.code = c.code)
                 THEN c.code || '_co'
                 ELSE c.code
               END,
               c.name_ru,
               c.id,
               now(), now()
          FROM companies c
         WHERE NOT EXISTS (SELECT 1 FROM groups g WHERE g.company_id = c.id)
    """)

    # ───── 4. Migrate users.allowed_companies → user_group_role ─────
    # CASE WHEN guards against rows where allowed_companies is JSON-null
    # ('null'::jsonb) or a scalar/object — PG would otherwise try to
    # evaluate jsonb_array_elements_text on them and DataError.
    op.execute("""
        WITH viewer_role AS (
            SELECT id FROM roles WHERE code = 'viewer'
        ),
        expanded AS (
            SELECT u.id AS user_id,
                   jsonb_array_elements_text(
                       CASE WHEN jsonb_typeof(u.allowed_companies) = 'array'
                            THEN u.allowed_companies
                            ELSE '[]'::jsonb
                       END
                   ) AS company_ref
              FROM users u
             WHERE u.allowed_companies IS NOT NULL
        ),
        resolved AS (
            SELECT e.user_id, c.id AS company_id
              FROM expanded e
              JOIN companies c
                ON c.id::text = trim(e.company_ref)
                OR lower(c.code) = lower(trim(e.company_ref))
        )
        INSERT INTO user_group_role (user_id, group_id, role_id, created_at)
        SELECT r.user_id, g.id, (SELECT id FROM viewer_role), now()
          FROM resolved r
          JOIN groups g ON g.company_id = r.company_id
        ON CONFLICT (user_id, group_id) DO NOTHING
    """)

    # ───── 5. Migrate users.organization_id → user_group_role ─────
    op.execute("""
        WITH viewer_role AS (SELECT id FROM roles WHERE code = 'viewer')
        INSERT INTO user_group_role (user_id, group_id, role_id, created_at)
        SELECT u.id, g.id, (SELECT id FROM viewer_role), now()
          FROM users u
          JOIN groups g ON g.company_id = u.organization_id
         WHERE u.organization_id IS NOT NULL
        ON CONFLICT (user_id, group_id) DO NOTHING
    """)

    # ───── 6. Drop allowed_companies ─────
    op.drop_column("users", "allowed_companies")


def downgrade() -> None:
    """Lossy: would need backup to reconstruct allowed_companies."""
    op.execute(
        "DO $$ BEGIN RAISE NOTICE "
        "'9aD downgrade is a no-op (data lost on drop of users.allowed_companies)'; "
        "END $$;"
    )
