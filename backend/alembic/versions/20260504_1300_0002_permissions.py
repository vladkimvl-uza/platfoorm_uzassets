"""seed permissions catalog and role-permission matrix

Revision ID: 0002_permissions
Revises: 0001_initial
Create Date: 2026-05-04 13:00:00.000000

Seeds:
  - ~70 permission codes spanning all platform modules
  - role → permissions matrix for the 22 platform roles

Owner (`is_owner=True`) and the `admin` role bypass the matrix in the auth
layer — they implicitly have every permission. Admin therefore gets only
`system.admin` here as a marker; the bypass happens in `require_permission`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_permissions"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# =====================================================================
# Permission catalog — (code, module, action, name, description)
# =====================================================================
PERMISSIONS = [
    # --- System / users / audit ---
    ("system.admin",                "system",      "admin",   "Полный администратор",            "Полный доступ ко всему"),
    ("system.config.view",          "system",      "view",    "Просмотр настроек",               None),
    ("system.config.edit",          "system",      "edit",    "Изменение настроек",              None),
    ("system.audit.view",           "system",      "view",    "Просмотр аудит-лога",             None),
    ("system.audit.verify_chain",   "system",      "admin",   "Проверка цепочки аудит-лога",     None),

    ("users.view",                  "users",       "view",    "Просмотр пользователей",          None),
    ("users.create",                "users",       "create",  "Создание пользователей",          None),
    ("users.edit",                  "users",       "edit",    "Редактирование пользователей",    None),
    ("users.delete",                "users",       "delete",  "Удаление пользователей",          None),
    ("users.assign_role",           "users",       "admin",   "Назначение ролей",                None),
    ("users.lock_unlock",           "users",       "admin",   "Блокировка / разблокировка",      None),

    # --- Companies ---
    ("companies.view",              "companies",   "view",    "Просмотр своих компаний",         None),
    ("companies.view_all",          "companies",   "view",    "Просмотр всех компаний",          None),
    ("companies.create",            "companies",   "create",  "Создание компаний",               None),
    ("companies.edit",              "companies",   "edit",    "Редактирование компаний",         None),
    ("companies.delete",            "companies",   "delete",  "Удаление компаний",               None),

    # --- Tasks (Kanban) ---
    ("tasks.view",                  "tasks",       "view",    "Просмотр задач",                  None),
    ("tasks.view_all",              "tasks",       "view",    "Просмотр всех задач",             None),
    ("tasks.create",                "tasks",       "create",  "Создание задач",                  None),
    ("tasks.edit",                  "tasks",       "edit",    "Редактирование задач",            None),
    ("tasks.delete",                "tasks",       "delete",  "Удаление задач",                  None),
    ("tasks.assign",                "tasks",       "edit",    "Назначение исполнителей",         None),

    # --- Ratings ---
    ("ratings.view",                "ratings",     "view",    "Просмотр рейтингов",              None),
    ("ratings.edit",                "ratings",     "edit",    "Редактирование рейтингов",        None),
    ("ratings.import",              "ratings",     "edit",    "Импорт рейтингов",                None),

    # --- ESG ---
    ("esg.view",                    "esg",         "view",    "Просмотр ESG",                    None),
    ("esg.edit",                    "esg",         "edit",    "Редактирование ESG",              None),
    ("esg.import",                  "esg",         "edit",    "Импорт ESG",                      None),

    # --- Financials ---
    ("financials.view",             "financials",  "view",    "Просмотр финансовой отчётности",  None),
    ("financials.edit",             "financials",  "edit",    "Редактирование фин. отчётности",  None),
    ("financials.import",           "financials",  "edit",    "Импорт фин. отчётности",          None),
    ("financials.export",           "financials",  "export",  "Экспорт фин. отчётности",         None),

    # --- KPI ---
    ("kpi.view",                    "kpi",         "view",    "Просмотр KPI",                    None),
    ("kpi.edit",                    "kpi",         "edit",    "Редактирование KPI",              None),
    ("kpi.import",                  "kpi",         "edit",    "Импорт KPI",                      None),

    # --- Business plan ---
    ("bp.view",                     "bp",          "view",    "Просмотр бизнес-плана",           None),
    ("bp.edit",                     "bp",          "edit",    "Редактирование бизнес-плана",     None),
    ("bp.submit",                   "bp",          "approve", "Отправка БП на утверждение",      None),
    ("bp.approve",                  "bp",          "approve", "Утверждение бизнес-плана",        None),

    # --- Procurement: requests (заявки) ---
    ("procurement.request.view",            "procurement", "view",    "Просмотр заявок на закупку", None),
    ("procurement.request.create",          "procurement", "create",  "Создание заявки",            None),
    ("procurement.request.approve_head",    "procurement", "approve", "Утв. заявки руководителем",  "Уровень: руководитель отдела"),
    ("procurement.request.approve_director","procurement", "approve", "Утв. заявки директором",     "Уровень: директор"),
    ("procurement.request.approve_plan",    "procurement", "approve", "Утв. плановым отделом",      None),
    ("procurement.request.approve_purchase","procurement", "approve", "Утв. отделом закупок",       None),

    # --- Procurement: contracts ---
    ("procurement.contract.view",           "procurement", "view",    "Просмотр контрактов",        None),
    ("procurement.contract.create",         "procurement", "create",  "Создание контракта",         None),
    ("procurement.contract.edit",           "procurement", "edit",    "Редактирование контракта",   None),
    ("procurement.contract.approve",        "procurement", "approve", "Утверждение контракта",      None),

    # --- Procurement: payments ---
    ("procurement.payment.view",            "procurement", "view",    "Просмотр платежей",          None),
    ("procurement.payment.create",          "procurement", "create",  "Создание платежа",           None),
    ("procurement.payment.review_mdm",      "procurement", "approve", "MDM-проверка платежа",       None),
    ("procurement.payment.approve_finance", "procurement", "approve", "Утв. фин. контролёром",      None),
    ("procurement.payment.approve_treasury","procurement", "approve", "Утв. казначейством",         None),
    ("procurement.payment.approve_cfo_dept","procurement", "approve", "Утв. CFO-департаментом",     None),
    ("procurement.payment.approve_committee","procurement","approve", "Утв. комиссией CFO",         None),

    # --- Treasury ---
    ("treasury.view",               "treasury",    "view",    "Просмотр казначейства",           None),
    ("treasury.budget.view",        "treasury",    "view",    "Просмотр бюджетов",               None),
    ("treasury.budget.edit",        "treasury",    "edit",    "Редактирование бюджетов",         None),
    ("treasury.payment.view",       "treasury",    "view",    "Просмотр платежей казначейства",  None),
    ("treasury.payment.approve",    "treasury",    "approve", "Утверждение платежа",             None),

    # --- Governance ---
    ("governance.view",             "governance",  "view",    "Просмотр корпоративного управления", None),
    ("governance.edit",             "governance",  "edit",    "Редактирование корпуправления",   None),

    # --- Credit / debt ---
    ("credit.view",                 "credit",      "view",    "Просмотр кредитного портфеля",    None),
    ("credit.edit",                 "credit",      "edit",    "Редактирование кредитов",         None),
    ("credit.import",               "credit",      "edit",    "Импорт кредитов",                 None),

    # --- Investment ---
    ("investment.view",             "investment",  "view",    "Просмотр инвестиций",             None),
    ("investment.edit",             "investment",  "edit",    "Редактирование инвестиций",       None),

    # --- Finmodel ---
    ("finmodel.view",               "finmodel",    "view",    "Просмотр финмодели",              None),
    ("finmodel.edit",               "finmodel",    "edit",    "Редактирование финмодели",        None),

    # --- AI ---
    ("ai.chat",                     "ai",          "view",    "Использование AI-чата",           None),
    ("ai.admin",                    "ai",          "admin",   "Администрирование AI",            None),

    # --- Reports ---
    ("reports.view",                "reports",     "view",    "Просмотр отчётов",                None),
    ("reports.export",              "reports",     "export",  "Экспорт отчётов",                 None),

    # --- Announcements ---
    ("announcements.view",          "announcements", "view",  "Просмотр объявлений",             None),
    ("announcements.manage",        "announcements", "admin", "Управление объявлениями",         None),
]


# =====================================================================
# Role → permissions matrix
#
# Note: `admin` and `is_owner=True` bypass these checks at the auth-layer,
# so they implicitly have everything. We give `admin` only `system.admin`
# here as a marker.
# =====================================================================
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": ["system.admin"],

    "organization": [
        "users.view",
        "companies.view",
        "tasks.view", "tasks.create", "tasks.edit", "tasks.assign",
        "ratings.view", "esg.view",
        "financials.view", "kpi.view", "bp.view",
        "procurement.request.view",
        "credit.view", "investment.view", "finmodel.view",
        "governance.view", "treasury.view",
        "reports.view",
        "announcements.view", "ai.chat",
    ],

    "lawyer": [
        "procurement.contract.view", "procurement.payment.view",
        "credit.view",
        "system.audit.view",
        "announcements.view", "ai.chat",
    ],

    "financier": [
        "financials.view", "financials.edit", "financials.export",
        "credit.view", "kpi.view", "treasury.view", "treasury.budget.view",
        "procurement.contract.view", "procurement.payment.view",
        "reports.view", "reports.export",
        "announcements.view", "ai.chat",
    ],

    "debt": [
        "credit.view", "credit.edit", "credit.import",
        "system.audit.view",
        "reports.view", "reports.export",
        "announcements.view", "ai.chat",
    ],

    "investment": [
        "investment.view", "investment.edit",
        "companies.view", "financials.view", "kpi.view",
        "reports.view",
        "announcements.view", "ai.chat",
    ],

    "finmodel": [
        "finmodel.view", "finmodel.edit",
        "financials.view", "financials.edit",
        "kpi.view",
        "reports.view",
        "announcements.view", "ai.chat",
    ],

    "monitoring": [
        # Cross-module read access + export
        "users.view",
        "companies.view", "companies.view_all",
        "tasks.view", "tasks.view_all",
        "ratings.view", "esg.view",
        "financials.view", "kpi.view", "bp.view",
        "procurement.request.view", "procurement.contract.view", "procurement.payment.view",
        "treasury.view", "treasury.budget.view", "treasury.payment.view",
        "credit.view", "investment.view", "finmodel.view",
        "governance.view",
        "system.audit.view",
        "reports.view", "reports.export",
        "announcements.view", "ai.chat",
    ],

    "fid": [
        "companies.view", "companies.view_all",
        "financials.view", "kpi.view", "ratings.view",
        "credit.view", "investment.view", "finmodel.view",
        "treasury.view", "bp.view",
        "reports.view", "reports.export",
        "announcements.view", "ai.chat",
    ],

    "audit_viewer": [
        # Pure read across the platform
        "users.view",
        "companies.view", "companies.view_all",
        "tasks.view", "tasks.view_all",
        "ratings.view", "esg.view",
        "financials.view", "kpi.view", "bp.view",
        "procurement.request.view", "procurement.contract.view", "procurement.payment.view",
        "treasury.view", "treasury.budget.view", "treasury.payment.view",
        "credit.view", "investment.view", "finmodel.view",
        "governance.view",
        "system.audit.view", "system.audit.verify_chain",
        "reports.view",
        "announcements.view",
    ],

    "initiator": [
        "tasks.view", "tasks.create",
        "procurement.request.create", "procurement.request.view",
        "announcements.view", "ai.chat",
    ],

    "department_worker": [
        "tasks.view", "tasks.create",
        "procurement.request.create", "procurement.request.view",
        "kpi.view",
        "announcements.view", "ai.chat",
    ],

    "department_head": [
        "tasks.view", "tasks.view_all", "tasks.assign",
        "procurement.request.view",
        "procurement.request.approve_head",
        "kpi.view",
        "announcements.view", "ai.chat",
    ],

    "department_director": [
        "tasks.view", "tasks.view_all", "tasks.assign",
        "procurement.request.view",
        "procurement.request.approve_head",
        "procurement.request.approve_director",
        "procurement.contract.view",
        "kpi.view", "bp.view", "bp.approve",
        "financials.view",
        "reports.view", "reports.export",
        "announcements.view", "ai.chat",
    ],

    "plan_department": [
        "procurement.request.view",
        "procurement.request.approve_plan",
        "kpi.view", "bp.view",
        "reports.view",
        "announcements.view", "ai.chat",
    ],

    "purchase_department": [
        "procurement.request.view",
        "procurement.request.approve_purchase",
        "procurement.contract.view", "procurement.contract.create",
        "announcements.view", "ai.chat",
    ],

    "procurement_owner": [
        "procurement.request.view",
        "procurement.contract.view", "procurement.contract.create",
        "procurement.contract.edit", "procurement.contract.approve",
        "procurement.payment.view", "procurement.payment.create",
        "reports.view", "reports.export",
        "announcements.view", "ai.chat",
    ],

    "finance_controller": [
        "procurement.contract.view",
        "procurement.payment.view", "procurement.payment.approve_finance",
        "treasury.view", "financials.view",
        "announcements.view", "ai.chat",
    ],

    "treasure_user": [
        "treasury.view", "treasury.budget.view", "treasury.payment.view",
        "treasury.payment.approve",
        "procurement.payment.view", "procurement.payment.approve_treasury",
        "reports.view", "reports.export",
        "announcements.view", "ai.chat",
    ],

    "mdm_steward": [
        "users.view",
        "companies.view", "companies.view_all",
        "procurement.payment.view", "procurement.payment.review_mdm",
        "system.audit.view",
        "announcements.view", "ai.chat",
    ],

    "cfo_department": [
        "treasury.view", "treasury.budget.view", "treasury.budget.edit",
        "treasury.payment.view",
        "procurement.payment.view", "procurement.payment.approve_cfo_dept",
        "financials.view", "financials.export",
        "kpi.view", "bp.view",
        "reports.view", "reports.export",
        "announcements.view", "ai.chat",
    ],

    "cfo_committee": [
        "treasury.view", "treasury.budget.view",
        "treasury.payment.view", "treasury.payment.approve",
        "procurement.payment.view", "procurement.payment.approve_committee",
        "financials.view",
        "reports.view",
        "announcements.view", "ai.chat",
    ],
}


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. Insert permissions ---
    insert_perm = sa.text("""
        INSERT INTO permissions (id, code, module, action, name, description, created_at, updated_at)
        VALUES (gen_random_uuid(), :code, :module, :action, :name, :description, NOW(), NOW())
        ON CONFLICT (code) DO UPDATE
        SET name = EXCLUDED.name,
            module = EXCLUDED.module,
            action = EXCLUDED.action,
            description = EXCLUDED.description,
            updated_at = NOW()
    """)
    for code, module, action, name, desc in PERMISSIONS:
        bind.execute(insert_perm, {
            "code": code, "module": module, "action": action,
            "name": name, "description": desc,
        })

    # --- 2. Build role-permission links ---
    # Step A: clear existing role_permission rows (so re-running this migration
    # gives a clean matrix — useful if we tweak the spec later)
    bind.execute(sa.text("DELETE FROM role_permission"))

    link = sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r, permissions p
         WHERE r.code = :role_code
           AND p.code = :perm_code
        ON CONFLICT DO NOTHING
    """)
    for role_code, perms in ROLE_PERMISSIONS.items():
        for p in perms:
            bind.execute(link, {"role_code": role_code, "perm_code": p})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permission"))
    bind.execute(sa.text("DELETE FROM permissions"))
