"""initial schema — all 56 tables + 22-role taxonomy

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-04 12:00:00.000000

Bootstrap migration. Creates the entire schema using `Base.metadata.create_all()`
and seeds reference data: sectors, the 22 platform roles, and the year registry.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database import Base
import app.models  # noqa: F401  -- register all models with Base.metadata


# revision identifiers
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# =====================================================================
# Role catalog — 22 platform roles
# =====================================================================
# Tuple format:
#   (code, category, approval_level, sort_order,
#    name_ru, name_uz, name_en,
#    description_ru, description_uz, description_en)
ROLES = [
    # --- Administrative ---
    ("admin", "admin", None, 10,
     "Администратор",
     "Administrator",
     "Administrator",
     "Полный системный администратор с доступом почти ко всем модулям и настройкам.",
     "Deyarli barcha modullar va sozlamalarga kirish huquqiga ega to‘liq tizim administratori.",
     "Full system administrator with access to almost all modules and settings."),

    ("organization", "organization", None, 20,
     "Пользователь организации",
     "Tashkilot foydalanuvchisi",
     "Organization user",
     "Обычный пользователь организации, работающий преимущественно в рамках данных своей организации.",
     "Asosan o‘z tashkiloti ma’lumotlari doirasida ishlovchi oddiy tashkilot foydalanuvchisi.",
     "A regular organization user working primarily within their organization's data."),

    # --- Domain specialists ---
    ("lawyer", "finance", None, 30,
     "Юрист",
     "Yurist",
     "Lawyer",
     "Юридический пользователь для AR/AP-процессов, связанных с дебиторами/кредиторами, претензиями и судебными делами.",
     "Debitor/kreditor, da’vo va sud bilan bog‘liq AR/AP jarayonlari uchun yuridik foydalanuvchi.",
     "Legal user for AR/AP processes related to debtors/creditors, claims, and litigation."),

    ("financier", "finance", None, 40,
     "Финансист",
     "Moliyachi",
     "Financier",
     "Финансовый специалист по кредитам, финансовым формам, дашбордам и отдельным процессам treasury/procurement.",
     "Kreditlar, moliyaviy shakllar, dashboardlar hamda ayrim treasury/procurement jarayonlari bilan shug‘ullanuvchi moliya mutaxassisi.",
     "Finance specialist working with credits, financial forms, dashboards, and selected treasury/procurement processes."),

    ("debt", "finance", None, 50,
     "Специалист по задолженности",
     "Qarz mutaxassisi",
     "Debt specialist",
     "Специалист реестра задолженности/кредитов, работает с дашбордами долгов, кредитами, импортом и аудитом.",
     "Debt/kredit reyestri mutaxassisi, qarz dashboardlari, kreditlar va import/audit bilan shug‘ullanadi.",
     "Debt/credit registry specialist working with debt dashboards, credits, import and audit."),

    ("investment", "strategic", None, 60,
     "Пользователь инвестиций",
     "Investitsiya foydalanuvchisi",
     "Investment user",
     "Пользователь инвестиционного модуля, ориентированный на инвестиционные страницы и дашборды.",
     "Investitsiya sahifalari va dashboardlariga yo‘naltirilgan investitsiya moduli foydalanuvchisi.",
     "User of the investment module, focused on investment pages and dashboards."),

    ("finmodel", "strategic", None, 70,
     "Пользователь финмодели",
     "Finmodel foydalanuvchisi",
     "Financial model user",
     "Работает со страницами финансовой модели и производственного планирования.",
     "Moliyaviy model va ishlab chiqarish rejalashtirish sahifalari bilan ishlovchi foydalanuvchi.",
     "User working with financial model and production-planning pages."),

    ("monitoring", "audit", None, 80,
     "Мониторинг",
     "Monitoring",
     "Monitoring user",
     "Кросс-модульный пользователь мониторинга/проверки с широкими дашбордами и правом просмотра.",
     "Keng qamrovli dashboardlar va ko‘rib chiqish huquqiga ega bo‘lgan, modullararo monitoring/tekshiruv foydalanuvchisi.",
     "Cross-module monitoring/inspection user with broad dashboards and view rights."),

    ("fid", "strategic", None, 90,
     "FID — стратегические дашборды",
     "FID — strategik dashboardlar",
     "FID — strategic dashboards",
     "Стратегический пользователь дашбордов по инвестициям, кредитам и финмодели; права на редактирование ограничены.",
     "Investitsiya, kredit va finmodel ko‘rinishlari uchun strategik dashboard foydalanuvchisi, tahrirlash huquqlari cheklangan.",
     "Strategic dashboard user for investment, credit, and finmodel views; limited edit rights."),

    # --- Hierarchical approval workflow (department chain) ---
    ("department_worker", "workflow", 1, 100,
     "Сотрудник отдела",
     "Bo‘lim xodimi",
     "Department worker",
     "Сотрудник отдела, создающий и отправляющий заявки на план или закупку.",
     "Reja yoki xarid so‘rovlarini yaratadigan va yuboradigan bo‘lim xodimi.",
     "Department employee who creates and submits planning or purchase requests."),

    ("department_head", "workflow", 2, 110,
     "Руководитель отдела",
     "Bo‘lim rahbari",
     "Department head",
     "Руководитель отдела, утверждающий заявки, отправленные сотрудниками.",
     "Xodim yuborgan so‘rovlarni tasdiqlovchi bo‘lim rahbari.",
     "Department head who approves requests submitted by workers."),

    ("department_director", "workflow", 3, 120,
     "Директор",
     "Direktor",
     "Director",
     "Высокоуровневый утверждающий в процессах, требующих утверждения на уровне директора.",
     "Direktor darajasida tasdiqlash talab qilinadigan jarayonlarda yuqori darajadagi tasdiqlovchi.",
     "High-level approver for processes requiring director-level approval."),

    ("plan_department", "workflow", None, 130,
     "Плановый отдел",
     "Reja bo‘limi",
     "Planning department",
     "Отдел, занимающийся рассмотрением, возвратом и завершением плановых заявок.",
     "Rejalashtirishga oid so‘rovlarni ko‘rib chiqish, qaytarish va yakunlash bilan shug‘ullanuvchi bo‘lim.",
     "Department that reviews, returns, and finalizes planning requests."),

    ("purchase_department", "workflow", None, 140,
     "Отдел закупок (внутренний)",
     "Xarid bo‘limi",
     "Purchase department",
     "Отдел закупок, участвующий или утверждающий в процессах закупок и оплат.",
     "Xarid va to‘lov jarayonlarida ishtirok etuvchi yoki tasdiqlovchi xarid bo‘limi.",
     "Purchase department that participates in or approves procurement and payment processes."),

    ("initiator", "workflow", 0, 150,
     "Инициатор",
     "Tashabbuskor",
     "Initiator",
     "Лицо/роль, инициирующее процесс утверждения или платежа.",
     "Tasdiqlash yoki to‘lov jarayonini boshlovchi shaxs/rol.",
     "Person/role who initiates an approval or payment process."),

    # --- Procurement domain ---
    ("procurement_owner", "procurement", None, 200,
     "Владелец закупок",
     "Xarid egasi",
     "Procurement owner",
     "Владелец закупок: управляет утверждёнными заявками, тендерами, контрактами и связанными платежами.",
     "Tasdiqlangan so‘rovlar, tenderlar, kontraktlar va ular bilan bog‘liq to‘lov jarayonlarini boshqaruvchi procurement egasi.",
     "Procurement owner managing approved requests, tenders, contracts, and related payment processes."),

    # --- Treasury & finance control ---
    ("finance_controller", "treasury", None, 300,
     "Финансовый контролёр",
     "Moliyaviy nazoratchi",
     "Finance controller",
     "Финансовый проверяющий/утверждающий в процессе утверждения платежей по контракту.",
     "Kontrakt bo‘yicha to‘lovlarni tasdiqlash jarayonida moliyaviy tekshiruvchi/tasdiqlovchi.",
     "Financial reviewer/approver in the contract payment approval process."),

    ("treasure_user", "treasury", None, 310,
     "Казначей",
     "Treasury foydalanuvchisi",
     "Treasury user",
     "Оператор казначейства, работающий с платежами, бюджетными базами, отчётами и treasury-процессами.",
     "To‘lovlar, budjet bazalari, hisobotlar va treasury jarayonlari bilan shug‘ullanuvchi treasury operatori.",
     "Treasury operator working with payments, budget bases, reports, and treasury processes."),

    ("mdm_steward", "treasury", None, 320,
     "MDM-стюард",
     "MDM steward",
     "MDM steward",
     "Ответственный за качество мастер-данных и проверки, преимущественно в процессах подтверждения платежей.",
     "Master data sifati va tekshiruvlari uchun javobgar bo‘lgan, asosan to‘lov tasdiqlash jarayonlarida qatnashuvchi rol.",
     "Responsible for master data quality and checks, mainly participating in payment approval processes."),

    ("cfo_department", "treasury", None, 330,
     "CFO-департамент",
     "CFO bo‘limi",
     "CFO department",
     "Роль CFO-департамента, занимающаяся годовыми бюджетными базами, отчётами и распределением бюджетных лимитов.",
     "Yillik budjet bazalari, hisobotlar va budjet limitlarini taqsimlash bilan shug‘ullanuvchi CFO bo‘limi roli.",
     "CFO department role handling annual budget bases, reports, and budget-limit distribution."),

    ("cfo_committee", "treasury", 4, 340,
     "Комиссия CFO",
     "CFO komissiyasi",
     "CFO committee",
     "Утверждающий комиссии CFO в процессах утверждения платежей.",
     "To‘lov tasdiqlash jarayonlarida CFO komissiyasi tasdiqlovchisi.",
     "CFO committee approver in payment approval processes."),

    # --- Audit ---
    ("audit_viewer", "audit", None, 900,
     "Аудит — только просмотр",
     "Audit ko‘ruvchi",
     "Audit viewer",
     "Наблюдатель аудита с правом только просмотра в процессах утверждения.",
     "Tasdiqlash jarayonlarida faqat ko‘rish huquqiga ega audit kuzatuvchisi.",
     "Audit observer with view-only rights in approval processes."),
]


# =====================================================================
# Sectors (industries)
# =====================================================================
SECTORS = [
    ("mining",     "Горнодобывающая",     "Konchilik",           "Mining",       "#7F77DD",  1),
    ("oil_gas",    "Нефть и газ",         "Neft va gaz",         "Oil & Gas",    "#1D9E75",  2),
    ("energy",     "Энергетика",          "Energetika",          "Energy",       "#EF9F27",  3),
    ("transport",  "Транспорт",           "Transport",           "Transport",    "#378ADD",  4),
    ("chemistry",  "Химия",               "Kimyo",               "Chemistry",    "#E24B4A",  5),
    ("metallurgy", "Металлургия",         "Metallurgiya",        "Metallurgy",   "#1E2A4A",  6),
    ("telecom",    "Телекоммуникации",    "Telekommunikatsiya",  "Telecom",      "#9333ea",  7),
    ("finance",    "Финансы",             "Moliya",              "Finance",      "#0891b2",  8),
    ("agro",       "Агропромышленность",  "Agrosanoat",          "Agriculture",  "#65a30d",  9),
    ("other",      "Прочее",              "Boshqa",              "Other",        "#6b7280", 99),
]


def upgrade() -> None:
    """Create all tables, then seed reference data."""
    bind = op.get_bind()

    # --- 0. Required PostgreSQL extensions ---
    # init.sql also creates these on container init, but doing it here too
    # makes the migration runnable against any blank PostgreSQL instance
    # (e.g. uzcloud.uz Coolify deploy).
    bind.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
    bind.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
    bind.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))

    # --- 1. Schema ---
    Base.metadata.create_all(bind)

    # --- 2. Sectors ---
    insert_sector = sa.text(
        """
        INSERT INTO sectors (id, code, name_ru, name_uz, name_en, color_hex, sort_order, created_at, updated_at)
        VALUES (gen_random_uuid(), :code, :ru, :uz, :en, :color, :ord, NOW(), NOW())
        ON CONFLICT (code) DO NOTHING
        """
    )
    for code, ru, uz, en, color, ord_ in SECTORS:
        bind.execute(insert_sector, {"code": code, "ru": ru, "uz": uz, "en": en, "color": color, "ord": ord_})

    # --- 3. Roles (22 platform roles) ---
    insert_role = sa.text(
        """
        INSERT INTO roles (
            id, code, category, approval_level, sort_order,
            name_ru, name_uz, name_en,
            description_ru, description_uz, description_en,
            is_system, is_active, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), :code, :category, :lvl, :ord,
            :name_ru, :name_uz, :name_en,
            :desc_ru, :desc_uz, :desc_en,
            TRUE, TRUE, NOW(), NOW()
        )
        ON CONFLICT (code) DO NOTHING
        """
    )
    for (code, category, lvl, ord_,
         name_ru, name_uz, name_en,
         desc_ru, desc_uz, desc_en) in ROLES:
        bind.execute(insert_role, {
            "code": code, "category": category, "lvl": lvl, "ord": ord_,
            "name_ru": name_ru, "name_uz": name_uz, "name_en": name_en,
            "desc_ru": desc_ru, "desc_uz": desc_uz, "desc_en": desc_en,
        })

    # --- 4. Year registry ---
    bind.execute(
        sa.text(
            """
            INSERT INTO year_registry (id, year, is_closed, created_at, updated_at)
            VALUES
              (gen_random_uuid(), 2023, TRUE,  NOW(), NOW()),
              (gen_random_uuid(), 2024, TRUE,  NOW(), NOW()),
              (gen_random_uuid(), 2025, FALSE, NOW(), NOW()),
              (gen_random_uuid(), 2026, FALSE, NOW(), NOW())
            ON CONFLICT (year) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    """Drop all tables. Destroys all data."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
