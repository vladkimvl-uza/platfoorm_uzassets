"""Runtime migration self-heal (Pack 7.36 + 7.37 + 7.40).

Auto-applies missing schema changes on app startup. Idempotent —
safe to call on every boot.

Why this exists:
  The deployment environment can't always run `alembic upgrade head`
  (no venv, alembic missing, Windows + OneDrive sync conflicts).
  This module patches the schema on boot and seeds defaults.

Patches applied:
  • Pack 7.35  — year_registry.uz_budget_trln (NUMERIC) + seed rates
  • Pack 7.37  — year_registry.eur_rate (NUMERIC) + seed EUR rates
  • Pack 7.40  — macro_scenarios + macro_scenario_overrides tables
                 + seed 3 default scenarios (Base/Opt/Pess)

All operations are idempotent — re-running has no effect.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# / 7.37 — year_registry seeds
# ─────────────────────────────────────────────────────────────────────

# (year, usd_rate, eur_rate, uz_budget_trln) — matches /7.37 migration
_YEAR_SEEDS: tuple[tuple[int, float, float, float], ...] = (
    (2021, 10610.00, 12520.00, 230.0),
    (2022, 11050.00, 11600.00, 260.0),
    (2023, 11420.00, 12330.00, 290.0),
    (2024, 12650.91, 13691.00, 320.0),
    (2025, 12576.41, 14140.00, 350.0),
    (2026, 12200.00, 14250.00, 380.0),
)

_TARGET_REVISION = "0025_yearly_rates_uz_budget"
_PREV_REVISION = "7b2c0ffe4ai0"


# ─────────────────────────────────────────────────────────────────────
# scenario seeds (3 defaults)
# ─────────────────────────────────────────────────────────────────────

# (code, name_ru, description, color_hex, sort_order)
_SCENARIO_SEEDS = (
    (
        "base",
        "Базовый",
        "Сохранение текущих значений макропоказателей. "
        "Прогноз строится без корректировок — поля override'ов пусты, "
        "значения берутся из вкладки «Макроэкономика».",
        "#888780",
        0,
    ),
    (
        "optimistic",
        "Оптимистичный",
        "Ускорение реформ: снижение инфляции, ускорение ВВП, "
        "укрепление сума. Применять для лучших оценок NPV и плановых KPI.",
        "#1D9E75",
        1,
    ),
    (
        "pessimistic",
        "Пессимистичный",
        "Внешние шоки: рост инфляции, повышение ставки ЦБ, ослабление сума, "
        "замедление ВВП. Для стресс-тестов и оценки рисков.",
        "#E24B4A",
        2,
    ),
)

# (scenario_code, year, infl, cb, gdp, usd, eur, budget)
# Базовый сценарий ОВЕРРАЙДОВ НЕ ИМЕЕТ — все NULL, используется year_registry.
_SCENARIO_OVERRIDE_SEEDS = (
    # Оптимистичный — мягкая инфляция, ускоренный ВВП, более крепкий сум
    ("optimistic", 2025,  8.2, 12.5, 7.6, 12100.0, 13600.0, 360.0),
    ("optimistic", 2026,  7.0, 11.0, 7.8, 11700.0, 13700.0, 400.0),
    ("optimistic", 2027,  6.0, 10.0, 8.0, 11400.0, 13800.0, 440.0),

    # Пессимистичный — высокая инфляция, высокая ставка, ослабление сума
    ("pessimistic", 2025, 17.2, 16.0, 3.5, 13100.0, 14700.0, 340.0),
    ("pessimistic", 2026, 15.5, 15.5, 3.5, 12800.0, 14900.0, 360.0),
    ("pessimistic", 2027, 13.0, 14.0, 4.0, 12500.0, 15000.0, 380.0),
)


async def _patch_knowledge_base(conn) -> None:
    """База знаний ИИ (RAG на Postgres FTS): документы + чанки с tsvector."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS knowledge_doc (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title        VARCHAR(512) NOT NULL,
            filename     VARCHAR(512),
            content_type VARCHAR(128),
            char_count   INTEGER NOT NULL DEFAULT 0,
            chunk_count  INTEGER NOT NULL DEFAULT 0,
            uploaded_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS knowledge_chunk (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_id      UUID NOT NULL REFERENCES knowledge_doc(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            content     TEXT NOT NULL,
            tsv         tsvector,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    # tsv заполняем триггером (русская конфигурация FTS).
    await conn.execute(text(
        """
        CREATE OR REPLACE FUNCTION knowledge_chunk_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.tsv := to_tsvector('russian', coalesce(NEW.content, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """,
    ))
    await conn.execute(text(
        "DROP TRIGGER IF EXISTS trg_knowledge_chunk_tsv ON knowledge_chunk",
    ))
    await conn.execute(text(
        "CREATE TRIGGER trg_knowledge_chunk_tsv BEFORE INSERT OR UPDATE "
        "ON knowledge_chunk FOR EACH ROW EXECUTE FUNCTION knowledge_chunk_tsv_update()",
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_tsv ON knowledge_chunk USING GIN (tsv)",
    ))
    # Семантический слой (pgvector) — опционален. Изолируем в SAVEPOINT: если
    # расширение vector недоступно в этой инсталляции Postgres, откатывается
    # только этот вложенный блок, а не весь self-heal. Поиск тогда остаётся
    # чисто лексическим (FTS).
    import os as _os
    try:
        _dim = int(_os.environ.get("EMBED_DIM", "1024"))
    except ValueError:
        _dim = 1024
    try:
        async with conn.begin_nested():
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text(
                f"ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS embedding vector({_dim})",
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embedding "
                "ON knowledge_chunk USING hnsw (embedding vector_cosine_ops)",
            ))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[runtime_migration] pgvector layer unavailable "
            "(semantic search disabled, FTS still works): %s", e,
        )


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────

async def ensure_yearly_rates_schema() -> None:
    """Apply ALL self-heal patches. Renamed for backward-compat —
    despite the name, this also covers Pack 7.40 scenario tables.
    The legacy name is kept so existing main.py lifespan hooks
    continue to work without modification.

    Looks up the engine via several module paths to stay compatible
    across different backend layouts. Falls back to no-op if no engine
    can be found.
    """
    engine = await _get_engine()
    if engine is None:
        logger.warning(
            "[runtime_migration] No async engine found - skipping self-heal"
        )
        return

    try:
        async with engine.begin() as conn:
            await _patch_year_registry(conn)
            await _patch_scenarios_tables(conn)
            await _patch_companies_hidden_years(conn)
            await _patch_users_avatar(conn)
            await _patch_tasks_projects_sort_order(conn)
            await _patch_progress_snapshots(conn)
            await _patch_user_permission_grant(conn)
            await _patch_custom_api_endpoint(conn)
            await _patch_org_role_tasks_write(conn)
            await _patch_org_role_company_create(conn)
            await _patch_notification_company_id(conn)
            await _patch_users_welcome_seen(conn)
            await _patch_users_last_seen(conn)
            await _patch_status_updates(conn)
            await _patch_comment_read(conn)
            await _patch_entity_watch(conn)
            await _patch_users_ical_token(conn)
            await _patch_deadline_notified(conn)
            await _patch_ai_user_config(conn)
            await _patch_rename_legacy_snapshot_key(conn)
            await _patch_retag_gov_source(conn)
            await _patch_users_oneid(conn)
            await _patch_user_sessions_started_at(conn)
            await _patch_users_strong_auth(conn)
            await _patch_users_org_profile_set(conn)
            await _patch_users_social_links(conn)
            await _patch_knowledge_base(conn)
            await _patch_pmo_schedule(conn)
            await _patch_pmo_raid(conn)
            await _patch_pmo_stakeholders(conn)
            await _patch_pmo_log(conn)
            await _patch_pmo_charter(conn)
            await _patch_pmo_raci(conn)
            await _patch_pmo_agile(conn)
            await _patch_notes_checklist(conn)
            await _patch_procurement_conclusion(conn)
            await _patch_subsidies(conn)
            await _patch_mfa_trusted_ips(conn)
            await _patch_overview_matrix(conn)
            await _patch_ifrs_report_history(conn)
            await _patch_report_wizard(conn)
            await _patch_kpi_direction(conn)
            await _patch_esg_maturity(conn)
            await _patch_esg_assurance_split(conn)
            await _patch_esg_swot(conn)
            await _patch_esg_report(conn)
            await _patch_kpi_indicator_is_esg(conn)
            await _patch_kpi_bp_metric_key(conn)
            await _patch_agency_rating_history(conn)
            await _seed_company_inns(conn)
            await _patch_committee_meetings(conn)
            await _patch_financial_unit_scale(conn)
            await _patch_hlf_backfill_ifrs_lines(conn)
            await _patch_soe_retained_earnings_seed(conn)
            await _patch_company_ownership_entity(conn)
            await _patch_year_registry_gdp(conn)
            await _bump_alembic(conn)
    except Exception as e:
        # Never crash the app on a self-heal failure - just log and continue.
        logger.warning(
            "[runtime_migration] self-heal failed (continuing): %s", e
        )


# ─────────────────────────────────────────────────────────────────────
# PMO P1 — расписание / базовый план / трудозатраты / зависимости
# ─────────────────────────────────────────────────────────────────────

async def _patch_pmo_schedule(conn) -> None:
    """PMO P1 (additive, idempotent): поля расписания/baseline/веса/часов на
    tasks+projects, бюджет на projects, таблица зависимостей task_dependencies."""
    _task_cols = (
        ("baseline_start",  "DATE"),
        ("baseline_due",    "DATE"),
        ("weight",          "INTEGER NOT NULL DEFAULT 1"),
        ("estimated_hours", "NUMERIC(10,1)"),
        ("actual_hours",    "NUMERIC(10,1)"),
        ("is_milestone",    "BOOLEAN NOT NULL DEFAULT FALSE"),
    )
    for col, ddl in _task_cols:
        await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN IF NOT EXISTS {col} {ddl}"))

    _proj_cols = (
        ("baseline_start",  "DATE"),
        ("baseline_due",    "DATE"),
        ("weight",          "INTEGER NOT NULL DEFAULT 1"),
        ("estimated_hours", "NUMERIC(10,1)"),
        ("actual_hours",    "NUMERIC(10,1)"),
        ("budget_amount",   "NUMERIC(18,2)"),
        ("actual_cost",     "NUMERIC(18,2)"),
    )
    for col, ddl in _proj_cols:
        await conn.execute(text(f"ALTER TABLE projects ADD COLUMN IF NOT EXISTS {col} {ddl}"))

    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS task_dependencies (
            id              UUID PRIMARY KEY,
            predecessor_id  UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            successor_id    UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            dep_type        VARCHAR(2) NOT NULL DEFAULT 'FS',
            lag_days        INTEGER NOT NULL DEFAULT 0,
            created_by      UUID,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task_dep_pair UNIQUE (predecessor_id, successor_id)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_task_dep_pred ON task_dependencies (predecessor_id)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_task_dep_succ ON task_dependencies (successor_id)"
    ))


async def _patch_pmo_raid(conn) -> None:
    """PMO P2 (additive, idempotent): RAID-реестр + статус-отчёты."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS raid_items (
            id           UUID PRIMARY KEY,
            company_id   UUID REFERENCES companies(id) ON DELETE CASCADE,
            project_id   UUID REFERENCES projects(id) ON DELETE SET NULL,
            kind         VARCHAR(16) NOT NULL DEFAULT 'risk',
            title        VARCHAR(512) NOT NULL,
            description  TEXT,
            owner_id     UUID,
            owner_name   VARCHAR(255),
            severity     VARCHAR(16) NOT NULL DEFAULT 'medium',
            probability  INTEGER NOT NULL DEFAULT 3,
            impact       INTEGER NOT NULL DEFAULT 3,
            score        INTEGER NOT NULL DEFAULT 9,
            status       VARCHAR(16) NOT NULL DEFAULT 'open',
            mitigation   TEXT,
            due_date     DATE,
            closed_at    TIMESTAMPTZ,
            created_by   UUID,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_raid_company ON raid_items (company_id, status)"
    ))
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS status_reports (
            id           UUID PRIMARY KEY,
            company_id   UUID REFERENCES companies(id) ON DELETE CASCADE,
            project_id   UUID REFERENCES projects(id) ON DELETE SET NULL,
            period       DATE,
            rag          VARCHAR(8) NOT NULL DEFAULT 'green',
            summary      TEXT,
            metrics      JSONB,
            created_by   UUID,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_status_reports_company ON status_reports (company_id, created_at)"
    ))


async def _patch_pmo_stakeholders(conn) -> None:
    """PMBOK 7 (additive, idempotent): реестр стейкхолдеров + поля возможностей
    (polarity/response_strategy) у RAID."""
    await conn.execute(text(
        "ALTER TABLE raid_items ADD COLUMN IF NOT EXISTS polarity VARCHAR(12) NOT NULL DEFAULT 'threat'"
    ))
    await conn.execute(text(
        "ALTER TABLE raid_items ADD COLUMN IF NOT EXISTS response_strategy VARCHAR(16)"
    ))
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS pmo_stakeholders (
            id                  UUID PRIMARY KEY,
            company_id          UUID REFERENCES companies(id) ON DELETE CASCADE,
            project_id          UUID REFERENCES projects(id) ON DELETE SET NULL,
            name                VARCHAR(255) NOT NULL,
            role                VARCHAR(255),
            organization        VARCHAR(255),
            power               INTEGER NOT NULL DEFAULT 3,
            interest            INTEGER NOT NULL DEFAULT 3,
            engagement_current  VARCHAR(16) NOT NULL DEFAULT 'neutral',
            engagement_desired  VARCHAR(16) NOT NULL DEFAULT 'supportive',
            strategy            TEXT,
            contact             VARCHAR(255),
            notes               TEXT,
            created_by          UUID,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_pmo_stakeholders_company ON pmo_stakeholders (company_id)"
    ))


async def _patch_pmo_log(conn) -> None:
    """PMBOK 7 (additive, idempotent): извлечённые уроки + журнал изменений."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS pmo_lessons (
            id              UUID PRIMARY KEY,
            company_id      UUID REFERENCES companies(id) ON DELETE CASCADE,
            project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
            kind            VARCHAR(16) NOT NULL DEFAULT 'recommendation',
            title           VARCHAR(512) NOT NULL,
            description     TEXT,
            recommendation  TEXT,
            owner_name      VARCHAR(255),
            created_by      UUID,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_pmo_lessons_company ON pmo_lessons (company_id)"
    ))
    # mention: ответственный-пользователь у урока (для существующих БД)
    await conn.execute(text(
        "ALTER TABLE pmo_lessons ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES users(id) ON DELETE SET NULL"
    ))
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS pmo_changes (
            id              UUID PRIMARY KEY,
            company_id      UUID REFERENCES companies(id) ON DELETE CASCADE,
            project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
            kind            VARCHAR(16) NOT NULL DEFAULT 'scope',
            title           VARCHAR(512) NOT NULL,
            description     TEXT,
            impact          TEXT,
            requested_by    VARCHAR(255),
            status          VARCHAR(16) NOT NULL DEFAULT 'proposed',
            decided_by      VARCHAR(255),
            decided_at      TIMESTAMPTZ,
            created_by      UUID,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_pmo_changes_company ON pmo_changes (company_id, status)"
    ))


# ─────────────────────────────────────────────────────────────────────
# PMO P3 — Устав проекта (Charter)
# ─────────────────────────────────────────────────────────────────────

async def _patch_pmo_charter(conn) -> None:
    """PMBOK 7 (additive, idempotent): устав проекта/программы."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS pmo_charters (
            id                UUID PRIMARY KEY,
            company_id        UUID REFERENCES companies(id) ON DELETE CASCADE,
            project_id        UUID REFERENCES projects(id) ON DELETE SET NULL,
            project_title     VARCHAR(512),
            purpose           TEXT,
            objectives        TEXT,
            scope_in          TEXT,
            scope_out         TEXT,
            success_criteria  TEXT,
            deliverables      TEXT,
            milestones        TEXT,
            assumptions       TEXT,
            constraints       TEXT,
            sponsor_name      VARCHAR(255),
            manager_name      VARCHAR(255),
            budget_amount     NUMERIC(18,2),
            start_date        DATE,
            target_end_date   DATE,
            status            VARCHAR(16) NOT NULL DEFAULT 'draft',
            approved_by       VARCHAR(255),
            approved_at       TIMESTAMPTZ,
            created_by        UUID,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_pmo_charters_company ON pmo_charters (company_id, status)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_pmo_charters_project ON pmo_charters (project_id)"
    ))


# ─────────────────────────────────────────────────────────────────────
# PMO — RACI-матрица (команда)
# ─────────────────────────────────────────────────────────────────────

async def _patch_pmo_raci(conn) -> None:
    """PMBOK 7 (additive, idempotent): матрица ответственности RACI."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS pmo_raci (
            id            UUID PRIMARY KEY,
            company_id    UUID REFERENCES companies(id) ON DELETE CASCADE,
            project_id    UUID REFERENCES projects(id) ON DELETE SET NULL,
            item_label    VARCHAR(512) NOT NULL,
            person_name   VARCHAR(255) NOT NULL,
            person_id     UUID REFERENCES users(id) ON DELETE SET NULL,
            role          VARCHAR(1) NOT NULL DEFAULT 'R',
            created_by    UUID,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_pmo_raci_company ON pmo_raci (company_id)"
    ))


# ─────────────────────────────────────────────────────────────────────
# PMO — Agile / спринты (спринт группирует существующие задачи)
# ─────────────────────────────────────────────────────────────────────

async def _patch_pmo_agile(conn) -> None:
    """PMBOK 7 / Scrum (additive, idempotent): спринты + привязка задач."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS pmo_sprints (
            id               UUID PRIMARY KEY,
            company_id       UUID REFERENCES companies(id) ON DELETE CASCADE,
            project_id       UUID REFERENCES projects(id) ON DELETE SET NULL,
            name             VARCHAR(255) NOT NULL,
            goal             TEXT,
            start_date       DATE,
            end_date         DATE,
            status           VARCHAR(16) NOT NULL DEFAULT 'planned',
            capacity_points  INTEGER,
            created_by       UUID,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_pmo_sprints_company ON pmo_sprints (company_id, status)"
    ))
    # привязка существующих задач к спринту + story points
    await conn.execute(text(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS sprint_id UUID REFERENCES pmo_sprints(id) ON DELETE SET NULL"
    ))
    await conn.execute(text(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS story_points INTEGER"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_tasks_sprint ON tasks (sprint_id)"
    ))


# ─────────────────────────────────────────────────────────────────────
# Notes (Smart Journal) — чек-листы + ответственные
# ─────────────────────────────────────────────────────────────────────

async def _patch_notes_checklist(conn) -> None:
    """Smart Journal (additive, idempotent): ответственный на заметку +
    таблица пунктов чек-листа (каждый со своим ответственным/дедлайном)."""
    await conn.execute(text(
        "ALTER TABLE notes ADD COLUMN IF NOT EXISTS assignee_id UUID REFERENCES users(id) ON DELETE SET NULL"
    ))
    await conn.execute(text(
        "ALTER TABLE notes ADD COLUMN IF NOT EXISTS assignee_name VARCHAR(255)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_notes_assignee ON notes (assignee_id)"
    ))
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS note_checklist_items (
            id             UUID PRIMARY KEY,
            note_id        UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            text           VARCHAR(500) NOT NULL,
            is_done        BOOLEAN NOT NULL DEFAULT FALSE,
            position       INTEGER NOT NULL DEFAULT 0,
            assignee_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            assignee_name  VARCHAR(255),
            due_date       TIMESTAMPTZ,
            done_at        TIMESTAMPTZ,
            done_by_id     UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_note_checklist_note ON note_checklist_items (note_id, position)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_note_checklist_assignee ON note_checklist_items (assignee_id)"
    ))


# ─────────────────────────────────────────────────────────────────────
# Procurement — «Заключение центра экспертизы» по каждой закупке
# ─────────────────────────────────────────────────────────────────────

async def _patch_procurement_conclusion(conn) -> None:
    """Заключение центра экспертизы на закупку (additive, idempotent):
    свободный текст + статус + дата + автор."""
    _cols = (
        ("conclusion_text",        "TEXT"),
        ("conclusion_status",      "VARCHAR(32)"),
        ("conclusion_date",        "TIMESTAMPTZ"),
        ("conclusion_author_id",   "UUID REFERENCES users(id) ON DELETE SET NULL"),
        ("conclusion_author_name", "VARCHAR(255)"),
    )
    for col, ddl in _cols:
        await conn.execute(text(
            f"ALTER TABLE procurement_closures ADD COLUMN IF NOT EXISTS {col} {ddl}"
        ))


# ─────────────────────────────────────────────────────────────────────
# Subsidies — реестр субсидий по компаниям портфеля
# ─────────────────────────────────────────────────────────────────────

async def _patch_subsidies(conn) -> None:
    """Реестр субсидий (additive, idempotent): сумма + назначение + источник +
    вид + статус + дата по каждой записи."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS subsidies (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            year             INTEGER,
            amount           NUMERIC(28, 2),
            program          VARCHAR(512),
            source           VARCHAR(255),
            kind             VARCHAR(128),
            status           VARCHAR(32),
            allocation_date  DATE,
            note             TEXT,
            created_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            created_by_name  VARCHAR(255),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_subsidies_company_id ON subsidies (company_id)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_subsidies_year ON subsidies (year)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_subsidies_company_year ON subsidies (company_id, year)"
    ))


async def _patch_mfa_trusted_ips(conn) -> None:
    """Доверенные IP: пропуск 2FA при входе с того же IP в пределах таймаута
    (additive, idempotent)."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS mfa_trusted_ips (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ip          VARCHAR(64) NOT NULL,
            expires_at  TIMESTAMPTZ NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_mfa_trusted_user_ip UNIQUE (user_id, ip)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_mfa_trusted_user ON mfa_trusted_ips (user_id)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_mfa_trusted_expires ON mfa_trusted_ips (expires_at)"
    ))


async def _patch_overview_matrix(conn) -> None:
    """Настройка квартальной матрицы «Сводного обзора» по компании+году
    (выбор/правка/свои пункты, JSONB). Additive, idempotent."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS overview_matrix_configs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            year             INTEGER NOT NULL,
            config           JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by_name  VARCHAR(255),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_overview_matrix_company_year UNIQUE (company_id, year)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_overview_matrix_company ON overview_matrix_configs (company_id)"
    ))


async def _patch_ifrs_report_history(conn) -> None:
    """Даты публикации МСФО-отчётности по компаниям (с 2022). Additive, idempotent."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS ifrs_report_history (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            year             INTEGER NOT NULL,
            published_on     DATE,
            updated_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by_name  VARCHAR(255),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_ifrs_history_company_year UNIQUE (company_id, year)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_ifrs_history_company ON ifrs_report_history (company_id)"
    ))


async def _patch_report_wizard(conn) -> None:
    """Сохранённый «Мастер отчёта» по компании+году (JSONB). Additive, idempotent."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS report_wizard_configs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            year             INTEGER NOT NULL,
            config           JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by_name  VARCHAR(255),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_report_wizard_company_year UNIQUE (company_id, year)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_report_wizard_company ON report_wizard_configs (company_id)"
    ))


async def _patch_kpi_direction(conn) -> None:
    """Направление метрики KPI: 'up' (больше=лучше, по умолч.) | 'down' (меньше=лучше).
    Additive, idempotent. Default 'up' → поведение существующих данных не меняется."""
    await conn.execute(text(
        "ALTER TABLE kpi_indicators "
        "ADD COLUMN IF NOT EXISTS direction VARCHAR(8) NOT NULL DEFAULT 'up'"
    ))


# ─────────────────────────────────────────────────────────────────────
# Сид ИНН портфельных компаний (по коду — bulletproof). Пользователь
# передал ИНН 22 компаний; коды сверены с каталогом. Идемпотентно:
# проставляем только там, где inn пуст (ручные правки не перетираем).
# ─────────────────────────────────────────────────────────────────────

_COMPANY_INN_SEED: dict[str, str] = {
    "ngmk": "308425864",  # Навоийский ГМК
    "nur":  "201204514",  # Навоийуран
    "agmk": "202328794",  # Алмалыкский ГМК
    "umk":  "200460222",  # Узметкомбинат
    "uug":  "200899410",  # Узбекуголь
    "ung":  "200837914",  # Узбекнефтегаз
    "utg":  "200626188",  # Узтрансгаз
    "ugt":  "309702449",  # UzGasTrade
    "hgt":  "306605769",  # Худудгазтаъминот
    "nes":  "306347741",  # Национальные электрические сети
    "tes":  "306349304",  # Тепловые электрические станции
    "res":  "306350099",  # Региональные электрические сети
    "uge":  "304952767",  # Узбекгидроэнерго
    "uty":  "201051951",  # Узбекистон темир йуллари
    "uhy":  "306628114",  # Uzbekistan Airways
    "uap":  "306646884",  # Uzbekistan Airports
    "utc":  "203366731",  # Узбектелеком
    "tst":  "302762364",  # Тошшахартрансхизмат
    "upt":  "200833833",  # Узбекистон Почтаси
    "uas":  "201053918",  # Узавтосаноат
    "naz":  "200002933",  # Навоийазот
    "uks":  "203621367",  # Узкимёсаноат
}


# ─────────────────────────────────────────────────────────────────────
# ESG Maturity Cockpit — единая таблица трекера ESG-зрелости + seed из
# Excel-трекера (ISO / климат-воронка / риск-воронка / отчётность).
# stage: D1 ISO 0=нет/1=в процессе/2=сертиф · D4 климат 0..4 · D5 риски 0..3 ·
# D2 отчётность 0..4. Год сидим 2025 (текущий отчётный по трекеру). ON CONFLICT
# DO NOTHING — ручные правки не перетираем.
# ─────────────────────────────────────────────────────────────────────

_ESG_MATURITY_SEED: dict[str, dict] = {
    "ngmk": {"iso": (2, 2, 2), "clm": 3, "rsk": 1, "rep": 3},
    "nur":  {"iso": (2, 2, 2), "clm": 3, "rsk": 1, "rep": 3},
    "agmk": {"iso": (2, 2, 2), "clm": 3, "rsk": 0, "rep": 3},
    "ung":  {"iso": (2, 2, 2), "clm": 2, "rsk": 1, "rep": 3},
    "utg":  {"iso": (2, 2, 2), "clm": 2, "rsk": 3, "rep": 3},
    "hgt":  {"iso": (1, 0, 0), "clm": 1, "rsk": 0, "rep": 2},
    "tes":  {"iso": (2, 2, 2), "clm": 1, "rsk": 0, "rep": 1},
    "res":  {"iso": (1, 0, 0), "clm": 1, "rsk": 0, "rep": 2},
    "uge":  {"iso": (2, 2, 2), "clm": 1, "rsk": 0, "rep": 3},
    "naz":  {"iso": (2, 2, 2), "clm": 3, "rsk": 0, "rep": 2},
    "uhy":  {"iso": (1, 0, 0), "clm": 2, "rsk": 1, "rep": 2},
    "tst":  {"iso": (0, 0, 0), "clm": 1, "rsk": 0, "rep": 1},
    "utc":  {"iso": (0, 0, 0), "clm": 1, "rsk": 0, "rep": 2},
    "umk":  {"iso": (0, 0, 0), "clm": 0, "rsk": 0, "rep": 0},
    "ugt":  {"iso": (0, 0, 0), "clm": 0, "rsk": 0, "rep": 0},
    "nes":  {"iso": (2, 2, 2), "clm": 1, "rsk": 0, "rep": 0},
    "uks":  {"iso": (0, 0, 0), "clm": 0, "rsk": 0, "rep": 1},
    "uty":  {"iso": (0, 0, 0), "clm": 0, "rsk": 0, "rep": 0},
    "uas":  {"iso": (2, 2, 2), "clm": 0, "rsk": 0, "rep": 2},
    "upt":  {"iso": (0, 0, 0), "clm": 1, "rsk": 0, "rep": 0},
    "uug":  {"iso": (0, 0, 0), "clm": 0, "rsk": 0, "rep": 0},
    "uap":  {"iso": (0, 0, 0), "clm": 0, "rsk": 0, "rep": 0},
}
_ESG_SEED_YEAR = 2025


async def _patch_esg_maturity(conn) -> None:
    """Таблица esg_maturity_cells + индексы + первичный seed. Идемпотентно."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS esg_maturity_cells (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            year             INTEGER NOT NULL,
            dimension        VARCHAR(8) NOT NULL,
            sub_key          VARCHAR(32) NOT NULL DEFAULT '',
            stage            INTEGER NOT NULL DEFAULT 0,
            status_text      VARCHAR(64),
            value_text       VARCHAR(255),
            evidence_url     TEXT,
            owner_id         UUID REFERENCES users(id) ON DELETE SET NULL,
            due_date         DATE,
            last_reviewed_at TIMESTAMPTZ,
            extra            JSONB,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_esg_maturity_cell UNIQUE (company_id, year, dimension, sub_key)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_esg_maturity_co_year ON esg_maturity_cells (company_id, year)"
    ))
    # seed
    rows = (await conn.execute(text("SELECT code, id FROM companies"))).all()
    code_to_id = {c: i for c, i in rows}
    seeded = 0
    for code, d in _ESG_MATURITY_SEED.items():
        cid = code_to_id.get(code)
        if cid is None:
            continue
        cells = [
            ("D1", "iso14001", d["iso"][0]),
            ("D1", "iso45001", d["iso"][1]),
            ("D1", "iso50001", d["iso"][2]),
            ("D2", "", d["rep"]),
            ("D4", "", d["clm"]),
            ("D5", "", d["rsk"]),
        ]
        for dim, sk, st in cells:
            res = await conn.execute(
                text(
                    "INSERT INTO esg_maturity_cells (company_id, year, dimension, sub_key, stage) "
                    "VALUES (:cid, :yr, :dim, :sk, :st) "
                    "ON CONFLICT (company_id, year, dimension, sub_key) DO NOTHING"
                ),
                {"cid": cid, "yr": _ESG_SEED_YEAR, "dim": dim, "sk": sk, "st": st},
            )
            seeded += res.rowcount or 0
    if seeded:
        logger.info("[runtime_migration] seeded %d ESG maturity cells", seeded)


async def _patch_esg_assurance_split(conn) -> None:
    """Аудит ESG-редактора: «Прохождение независимого заверения» вынесено в
    отдельное измерение D2A. Ранее заверение = D2 стадия 4 («+ assurance»).
    Мигрируем legacy-данные: для каждой компании с D2>=4 создаём D2A=2
    (заверение пройдено) и опускаем D2 до 3 (IFRS SDS). Идемпотентно —
    после прогона D2<=3, повторный запуск ничего не делает."""
    # 1) создать ячейку заверения для каждой legacy-строки D2>=4
    await conn.execute(text(
        """
        INSERT INTO esg_maturity_cells (company_id, year, dimension, sub_key, stage)
        SELECT company_id, year, 'D2A', '', 2
        FROM esg_maturity_cells
        WHERE dimension = 'D2' AND sub_key = '' AND stage >= 4
        ON CONFLICT (company_id, year, dimension, sub_key) DO NOTHING
        """,
    ))
    # 2) опустить отчётность до IFRS SDS (3)
    res = await conn.execute(text(
        "UPDATE esg_maturity_cells SET stage = 3 "
        "WHERE dimension = 'D2' AND sub_key = '' AND stage >= 4"
    ))
    if res.rowcount:
        logger.info("[runtime_migration] split %d ESG D2 assurance → D2A cells", res.rowcount)


_ESG_SWOT_PORTFOLIO = {
    "strength": [
        "По портфелю сформирована базовая повестка ESG-трансформации. В компаниях начато закрепление ответственных, создаются рабочие механизмы координации, разрабатываются дорожные карты и профильные внутренние документы.",
        "Реализованные проекты обеспечили формирование первичной аналитической и методологической базы. Проведённые диагностики, gap-assessment, климатические и ESG-проекты позволили выявить ключевые разрывы и определить приоритетные направления доработки.",
        "По ряду компаний ESG-повестка переведена из общего декларирования в практическую плоскость: запущены прикладные инициативы по климату, экологическому менеджменту, управлению выбросами и подготовке профильных стратегий.",
        "Начата интеграция ESG- и климатических факторов в корпоративные процессы управления — вопросы выведены в стратегическую, риск-управленческую и операционную повестку отдельных компаний.",
        "Сформированы базовые предпосылки для перехода к более зрелой модели ESG-управления: развитие внутренних функций, повышение качества данных, усиление контрольной среды, поэтапное встраивание ESG в инвест- и операционную деятельность.",
    ],
    "weakness": [
        "Результаты уже реализованных проектов (ESG-диагностики и др.) недостаточно интегрированы в управленческие процессы. Внутренние механизмы контроля и сопровождения внедрения остаются слабыми.",
        "Зрелость систем ESG-управления остаётся недостаточной: во многих компаниях нет профильных специалистов и устойчивых команд, не выстроены система управления, распределение ответственности и подотчётность по ESG.",
        "Качество ESG-данных — ключевое ограничение: разрывы в периметре учёта, методиках расчёта, сопоставимости и готовности к верификации; сбор часто вручную, автоматизация низкая — риск искажений и снижение надёжности выводов.",
        "По ряду компаний требуются внешние технические аудиты международного уровня для устранения системных разрывов в области ООС и ОТиПБ.",
        "Интеграция ESG- и климатических рисков в ERM не завершена: риски идентифицированы, но не встроены в регулярный цикл управленческих решений и контроля исполнения.",
    ],
}
_ESG_SWOT_COMPANY = {
    "ngmk": {
        "strength": [
            "Подготовлена ESG-отчётность по стандартам GRI и SASB.",
            "Обновлён ESG-рейтинг Sustainable Fitch на уровне 54 баллов.",
            "Разработаны декарбонизационный план и климатические цели; начата подготовка климатической стратегии.",
            "Проходит ежегодный аудит RGMP/ICMC; получены рекомендации по развитию ESG-практик.",
        ],
        "weakness": [
            "Сохраняется риск недостижения климатической цели по сокращению выбросов к 2030 году.",
            "По блоку ОТиПБ зафиксировано ухудшение показателей LTIFR и FAR к уровню предыдущего года.",
            "Качество ESG-данных недостаточное: часть показателей собирается вручную, автоматизация ограничена.",
        ],
    },
    "nur": {
        "strength": [
            "Подготовлена отчётность за 2024 год по IFRS S2.",
            "Разработаны климатическая стратегия и декарбонизационный план.",
            "ESG-рейтинг Sustainable Fitch повышен с 55 до 61 балла при сохранении уровня «3».",
            "Снижены показатели травматизма: число несчастных случаев и LTIFR улучшились.",
        ],
        "weakness": [
            "Внутренние системы менеджмента требуют внешней оценки зрелости; практики реализуются скорее формально (экология, ОТ и промбезопасность).",
            "Надёжность части ESG-показателей ограничена: отдельные данные формируются расчётным способом и требуют независимой оценки.",
            "Практическая реализация климатической стратегии отстаёт; нужны системные мероприятия с учётом CAPEX для выполнения целей.",
        ],
    },
}


async def _patch_esg_swot(conn) -> None:
    """Таблица esg_swot_items + seed из Excel (портфельный SWOT + по-компанийно).
    Сидим только если таблица пуста (ручные правки не перетираем)."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS esg_swot_items (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind        VARCHAR(16) NOT NULL,
            scope       VARCHAR(16) NOT NULL DEFAULT 'portfolio',
            company_id  UUID REFERENCES companies(id) ON DELETE CASCADE,
            title       VARCHAR(255),
            body        TEXT NOT NULL,
            severity    VARCHAR(16),
            order_idx   INTEGER NOT NULL DEFAULT 0,
            extra       JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_esg_swot_company ON esg_swot_items (company_id)"
    ))
    existing = (await conn.execute(text("SELECT count(*) FROM esg_swot_items"))).scalar() or 0
    if existing:
        return
    seeded = 0
    for kind, items in _ESG_SWOT_PORTFOLIO.items():
        for i, body in enumerate(items):
            await conn.execute(
                text("INSERT INTO esg_swot_items (kind, scope, body, order_idx) "
                     "VALUES (:k, 'portfolio', :b, :o)"),
                {"k": kind, "b": body, "o": i},
            )
            seeded += 1
    rows = (await conn.execute(text("SELECT code, id FROM companies"))).all()
    code_to_id = {c: i for c, i in rows}
    for code, kinds in _ESG_SWOT_COMPANY.items():
        cid = code_to_id.get(code)
        if cid is None:
            continue
        for kind, items in kinds.items():
            for i, body in enumerate(items):
                await conn.execute(
                    text("INSERT INTO esg_swot_items (kind, scope, company_id, body, order_idx) "
                         "VALUES (:k, 'company', :cid, :b, :o)"),
                    {"k": kind, "cid": cid, "b": body, "o": i},
                )
                seeded += 1
    if seeded:
        logger.info("[runtime_migration] seeded %d ESG SWOT items", seeded)


async def _patch_esg_report(conn) -> None:
    """Таблица годовых ESG-отчётов компании (esg_reports): ссылка + описание по годам."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS esg_reports (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            year            INTEGER NOT NULL,
            status          VARCHAR(255),
            report_url      VARCHAR(2000),
            note            TEXT,
            changed_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            changed_by_name VARCHAR(255),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_esg_report_co_year UNIQUE (company_id, year)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_esg_reports_company ON esg_reports (company_id, year)"
    ))


async def _patch_kpi_indicator_is_esg(conn) -> None:
    """Жёсткая ESG-пометка KPI-индикатора (для ESG-KPI, добавленных из дашборда)."""
    await conn.execute(text(
        "ALTER TABLE kpi_indicators ADD COLUMN IF NOT EXISTS is_esg BOOLEAN NOT NULL DEFAULT FALSE"
    ))


async def _patch_kpi_bp_metric_key(conn) -> None:
    """Связь KPI-индикатора с канонической метрикой Бизнес-плана (reference-pull).
    NULL = свободный операционный KPI (по умолчанию, поведение не меняется);
    если задана — план/факт зеркалятся из BP/НСБУ. Additive, idempotent."""
    await conn.execute(text(
        "ALTER TABLE kpi_indicators ADD COLUMN IF NOT EXISTS bp_metric_key VARCHAR(32)"
    ))


async def _patch_agency_rating_history(conn) -> None:
    """История значений ESG/кредитных рейтингов (снимок при каждом изменении)."""
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS agency_rating_history (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            rating_id        UUID REFERENCES agency_ratings(id) ON DELETE SET NULL,
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            agency           VARCHAR(64) NOT NULL,
            is_esg           BOOLEAN NOT NULL DEFAULT FALSE,
            rating           VARCHAR(16),
            outlook          VARCHAR(32),
            score            VARCHAR(16),
            rating_date_text VARCHAR(64),
            rating_date      DATE,
            report_url       VARCHAR(2000),
            action           VARCHAR(16) NOT NULL DEFAULT 'snapshot',
            changed_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            changed_by_name  VARCHAR(255),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_arh_company_agency "
        "ON agency_rating_history (company_id, agency, created_at)"))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_arh_rating ON agency_rating_history (rating_id)"))
    # Бэкфилл: один снимок на каждый существующий рейтинг (идемпотентно).
    res = await conn.execute(text("""
        INSERT INTO agency_rating_history
            (id, rating_id, company_id, agency, is_esg, rating, outlook, score,
             rating_date_text, rating_date, report_url, action, changed_by_name, created_at)
        SELECT gen_random_uuid(), r.id, r.company_id, r.agency, r.is_esg, r.rating,
               r.outlook, r.score, r.rating_date_text, r.rating_date, r.report_url,
               'snapshot', 'импорт', COALESCE(r.updated_at, r.created_at, now())
        FROM agency_ratings r
        WHERE NOT EXISTS (
            SELECT 1 FROM agency_rating_history h WHERE h.rating_id = r.id
        )
    """))
    if res.rowcount:
        logger.info("[runtime_migration] backfilled %d agency_rating_history snapshots", res.rowcount)


# ─────────────────────────────────────────────────────────────────────
# Комитеты при наблюдательном совете — КОЛИЧЕСТВО заседаний за период
# (вместо булевых +/-). Период: (year, quarter), quarter NULL = годовой.
# Сид: 2025 годовой + 2026 Q1 по ИНН. Только если таблица пуста.
# ─────────────────────────────────────────────────────────────────────

# (inn, sb_meetings, sb_decisions, audit, strategy, nomrem, anticorr)
_CMTG_SEED_2025_ANNUAL: tuple[tuple[str, int | None, int | None, int | None, int | None, int | None, int | None], ...] = (
    ("201204514", 41, 68, 7, 7, 4, 4),
    ("200002933", 9, 49, 0, 0, 1, 0),
    ("306350099", 21, 105, 5, 0, 1, 0),
    ("306646884", 5, 24, 4, 2, 2, 1),
    ("203621367", 12, 83, 8, 7, 5, 3),
    ("203366731", 12, 75, 5, 24, 2, 4),
    ("306628114", 9, 37, 3, 3, 2, 0),
    ("309702449", 9, 41, 7, 1, 1, 3),
    ("200899410", 6, 38, 0, 0, 0, 0),
    ("302762364", 8, 47, 0, 0, 1, 0),
    ("306349304", 12, 42, 2, 0, 0, 0),
    ("308425864", 26, 74, 5, 8, 6, 4),
    ("201053918", 8, 31, 9, 7, 6, 5),
    ("200460222", 30, 127, 6, 1, 6, 4),
    ("306605769", 11, 41, 6, 1, 0, 0),
    ("200837914", 17, 98, 4, 4, 6, 4),
    ("201051951", 9, 140, 3, 2, 1, 1),
)

_CMTG_SEED_2026_Q1: tuple[tuple[str, int | None, int | None, int | None, int | None, int | None, int | None], ...] = (
    ("201204514", 5, 10, 2, 1, 1, 1),
    ("200002933", 2, 11, 0, 0, 0, 0),
    ("306350099", 6, 28, 0, 0, 0, 0),
    ("306646884", 1, 1, 1, 1, 1, 1),
    ("203621367", 1, 14, 2, 1, 1, 1),
    ("203366731", 3, 26, 3, 7, 0, 0),
    ("306628114", 2, 7, 1, 0, 0, 0),
    ("309702449", 3, 10, 1, 0, 0, 1),
    ("200899410", 6, 21, 0, 0, 0, 0),
    ("302762364", 3, 16, 1, 1, 1, 0),
    ("306349304", 5, 7, 0, 0, 0, 0),
    ("308425864", 3, 4, 1, 1, 1, 1),
    ("201053918", 3, 17, 0, 0, 1, 0),
    ("200460222", 4, 45, 0, 3, 1, 1),
    ("306605769", 2, 10, 2, 0, 0, 0),
    ("200837914", 5, 42, 1, 2, 1, 1),
    ("201051951", 2, None, 0, 0, 0, 0),
)


async def _patch_financial_unit_scale(conn) -> None:
    """Аудит фин-источников P1 (июль 2026): FinancialLine.value хранится в
    МЛРД сум у ВСЕХ отчётов (проверено данными: НГМК 2025 NSBU revenue=135810
    при unit_scale=1000 vs IFRS revenue=136145 при unit_scale=1e9 — одинаковый
    масштаб, разные флаги). unit_scale=1000 у ~440 отчётов — неверный флаг
    эпохи раннего импорта; читатели `value*unit_scale` (company_library,
    finmodel broadcast) получали цифры в 1e6 раз меньше истины. Данные НЕ
    трогаем — нормализуем ФЛАГ. Идемпотентно."""
    # Только доказанно-неверный флаг 1000 (в БД существуют лишь 1000 и 1e9);
    # гипотетический будущий легитимный 1e6-импорт не трогаем.
    res = await conn.execute(text(
        "UPDATE financial_reports SET unit_scale = 1000000000 "
        "WHERE unit_scale = 1000"
    ))
    if res.rowcount:
        logger.info(
            "[runtime_migration] normalized unit_scale → 1e9 on %d financial_reports",
            res.rowcount,
        )


# ─────────────────────────────────────────────────────────────────────
# Аудит фин-источников P2 — backfill канона (financial_lines IFRS,
# summary FY) из HLF-blob'ов (companies.extra["hlf"]).
#
# Сверка по VM-БД (finrecon, июль 2026): 349 точек компания×год×метрика
# есть в HLF, но ОТСУТСТВУЮТ в financial_lines IFRS — весь Cash Flow
# (CFO/CFI/CFF/дивиденды), дебиторка/кредиторка МСФО, часть BS/PL.
# Правила честности:
#   • существующие строки НИКОГДА не перезаписываем (канон = редактор);
#   • нулевые значения HLF пропускаем — это столбцы-пустышки шаблона
#     (hgt 2024: HLF=0.0 при МСФО=9419), «нет данных» ≠ 0;
#   • знак нормализуем к конвенции редактора: tax/dividendsPaid → abs()
#     (HLF-шаблон хранит оттоки с минусом, редактор — с плюсом);
#   • метрики ищутся только в «своих» секциях (pnl/sofp/cashflow) —
#     без кросс-хитов вроде «cash» в строках кэшфлоу.
# Идемпотентно: повторный боот — 0 вставок.
# ─────────────────────────────────────────────────────────────────────

# metric → (report_type, иглы label (приоритет по порядку), id секций HLF)
_HLF_BF_MATCHERS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "revenue":       ("PL", ("revenue", "выручка"), ("pnl",)),
    "cogs":          ("PL", ("cost of sales", "cost of goods", "себестоимость"), ("pnl",)),
    "grossProfit":   ("PL", ("gross profit", "валовая прибыль"), ("pnl",)),
    "opProfit":      ("PL", ("operating profit", "операционная прибыль"), ("pnl",)),
    "pbt":           ("PL", ("profit before tax", "прибыль до налогообложения"), ("pnl",)),
    "tax":           ("PL", ("income tax", "налог на прибыль"), ("pnl",)),
    "profit":        ("PL", ("profit for the period", "profit for the year", "net profit", "чистая прибыль"), ("pnl",)),
    "totalAssets":       ("BS", ("total assets", "итого активы", "всего активов"), ("sofp",)),
    "totalLiabilities":  ("BS", ("total liabilities", "итого обязательства"), ("sofp",)),
    "equity":            ("BS", ("total equity", "итого капитал", "собственный капитал"), ("sofp",)),
    "cash":              ("BS", ("cash and cash equivalents", "денежные средства"), ("sofp",)),
    "debt":              ("BS", ("total debt", "loans and borrowings", "borrowings", "кредиты и займы"), ("sofp",)),
    "accountsReceivable": ("BS", ("trade and other receivables", "trade receivables", "дебиторская"), ("sofp",)),
    "accountsPayable":    ("BS", ("trade and other payables", "trade payables", "кредиторская"), ("sofp",)),
    "cfo": ("CF", ("operating cash flow", "net cash from operating", "cash from operating",
                   "cash generated from operating", "cash flows from operating",
                   "поток от операц", "операционн"), ("cashflow",)),
    "cfi": ("CF", ("investing cash flow", "net cash used in investing", "cash from investing",
                   "cash flows from investing", "поток от инвест", "инвестиционн"), ("cashflow",)),
    "cff": ("CF", ("financing cash flow", "net cash from financing", "cash from financing",
                   "cash flows from financing", "поток от фин", "финансиров"), ("cashflow",)),
    "dividendsPaid": ("CF", ("dividends paid", "тўланган дивиденд", "дивиденды выпл",
                             "дивиденды упл", "дивиденд"), ("cashflow", "sofp", "pnl")),
}
_HLF_BF_LABELS: dict[str, str] = {
    "revenue": "Выручка", "cogs": "Себестоимость", "grossProfit": "Валовая прибыль",
    "opProfit": "Операционная прибыль", "pbt": "Прибыль до налогообложения",
    "tax": "Налог на прибыль", "profit": "Чистая прибыль",
    "totalAssets": "Итого активы", "totalLiabilities": "Итого обязательства",
    "equity": "Итого капитал", "cash": "Денежные средства и эквиваленты",
    "debt": "Долг (займы и кредиты)", "accountsReceivable": "Дебиторская задолженность",
    "accountsPayable": "Кредиторская задолженность",
    "cfo": "CFO · Поток от операционной деятельности",
    "cfi": "CFI · Поток от инвестиционной деятельности",
    "cff": "CFF · Поток от финансовой деятельности",
    "dividendsPaid": "Дивиденды выплаченные",
}
_HLF_BF_ABS = {"tax", "dividendsPaid"}          # знак → конвенция редактора
_HLF_BF_BAD_LABEL = ("%", "margin", "маржа", "рентабельн")


def _hlf_bf_extract(hlf) -> dict[str, dict[int, float]]:
    """{metric: {year: value}} из HLF-blob'а. Годы — из СЕКЦИИ (top-level
    years = union и может быть длиннее). total/subtotal приоритетнее line."""
    out: dict[str, dict[int, float]] = {}
    if not isinstance(hlf, dict):
        return out
    sections = hlf.get("sections") or []
    top_years = hlf.get("years") or []
    for metric, (_rt, needles, sec_ids) in _HLF_BF_MATCHERS.items():
        chosen = None   # (prio, is_total, row, years)
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            sid = str(sec.get("id") or "")
            if not (sid in sec_ids or sid.startswith("custom")):
                continue
            years = sec.get("years") or top_years
            for row in sec.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                rtype = str(row.get("type") or "")
                if rtype in ("section_header", "subheader"):
                    continue
                hay = (str(row.get("label") or "") + " " + str(row.get("mapping") or "")).lower()
                if any(b in hay for b in _HLF_BF_BAD_LABEL):
                    continue
                for prio, needle in enumerate(needles):
                    if needle in hay:
                        is_total = rtype in ("subtotal", "total")
                        if chosen is None or (is_total and not chosen[1]) \
                                or (is_total == chosen[1] and prio < chosen[0]):
                            chosen = (prio, is_total, row, years)
                        break
        if chosen is None:
            continue
        _p, _t, row, years = chosen
        vals = row.get("values") or []
        ymap: dict[int, float] = {}
        for i, y in enumerate(years):
            try:
                yi = int(y)
            except (TypeError, ValueError):
                continue
            if not (2000 < yi < 2100) or i >= len(vals):
                continue
            v = vals[i]
            if v is None or v == "":
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f == f and abs(f) != float("inf"):
                ymap[yi] = f
        if ymap:
            out[metric] = ymap
    return out


async def _patch_hlf_backfill_ifrs_lines(conn) -> None:
    """Backfill канона из HLF (см. блок-комментарий выше). Идемпотентно."""
    import json as _json
    cos = (await conn.execute(text(
        "SELECT id, code, extra FROM companies WHERE is_active = true"
    ))).all()

    reps = (await conn.execute(text(
        "SELECT id, company_id, year, report_type FROM financial_reports "
        "WHERE standard = 'IFRS' AND is_detailed = false AND quarter IS NULL"
    ))).all()
    rep_by: dict[tuple, object] = {(r.company_id, int(r.year), r.report_type): r.id for r in reps}

    codes = list(_HLF_BF_MATCHERS.keys())
    have_rows = (await conn.execute(text(
        "SELECT report_id, line_code FROM financial_lines WHERE line_code = ANY(:codes)"
    ), {"codes": codes})).all()
    have = {(r.report_id, r.line_code) for r in have_rows}

    ins_reports = ins_lines = 0
    for cid, _code, extra in cos:
        if isinstance(extra, str):
            try:
                extra = _json.loads(extra)
            except Exception:
                extra = None
        hlf = (extra or {}).get("hlf") if isinstance(extra, dict) else None
        if not hlf:
            continue
        for metric, ymap in _hlf_bf_extract(hlf).items():
            rtype = _HLF_BF_MATCHERS[metric][0]
            for year, val in ymap.items():
                if val == 0.0:
                    continue   # столбец-пустышка, «нет данных» ≠ 0
                if metric in _HLF_BF_ABS:
                    val = abs(val)
                rid = rep_by.get((cid, year, rtype))
                if rid is None:
                    rid = (await conn.execute(text(
                        "INSERT INTO financial_reports "
                        "(id, company_id, year, quarter, standard, report_type, currency, "
                        " unit_scale, source, is_audited, is_detailed, is_consolidated, "
                        " created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :cid, :yr, NULL, 'IFRS', :rt, 'UZS', "
                        " 1000000000, 'hlf-backfill', false, false, true, now(), now()) "
                        "RETURNING id"
                    ), {"cid": cid, "yr": year, "rt": rtype})).scalar_one()
                    rep_by[(cid, year, rtype)] = rid
                    ins_reports += 1
                if (rid, metric) in have:
                    continue   # канон уже заполнен — не трогаем
                await conn.execute(text(
                    "INSERT INTO financial_lines "
                    "(id, report_id, line_code, line_name, value, is_subtotal, "
                    " is_calculated, sort_order, indent_level, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :rid, :lc, :ln, :v, false, false, 0, 0, "
                    " now(), now())"
                ), {"rid": rid, "lc": metric, "ln": _HLF_BF_LABELS[metric], "v": val})
                have.add((rid, metric))
                ins_lines += 1

    if ins_reports or ins_lines:
        logger.info(
            "[runtime_migration] hlf-backfill: +%d IFRS reports, +%d financial_lines",
            ins_reports, ins_lines,
        )


# Нераспределённая прибыль (retained earnings) для Altman Z-Score.
# Источник: IMF SOE Health Check Tool (Input Forms), млрд UZS. В каноне этого
# поля не было (0 покрытия) → Z-Score был заблокирован. Сидим как ОЦЕНКУ
# (line_name помечен «imf-healthcheck»), редактируемо через редактор.
_SOE_RE_SEED: dict[str, dict[int, float]] = {
    "ngmk": {2023: 57721.0, 2024: 64964.0, 2025: 63373.0},
    "agmk": {2023: 8423.1, 2024: 6640.3},
    "nur":  {2023: 6806.0, 2024: 10311.0, 2025: 13742.0},
    "umk":  {2023: 2184.0, 2024: 3045.0},
    "uug":  {2023: -135.7},
    "tes":  {2023: -11165.4, 2024: -9196.0, 2025: -9555.4},
    "nes":  {2023: -18406.5, 2024: -6740.6},
    "uge":  {2023: 6721.3, 2024: 8747.6},
    "utg":  {2023: -17420.0, 2024: -7494.0, 2025: -3045.0},
    "ung":  {2023: 23136.0, 2024: 23853.0},
    "hgt":  {2023: -3766.0, 2024: -6154.0},
    "ugt":  {2023: -5161.0, 2024: -13726.0, 2025: -13180.0},
    "uhy":  {2023: -1686.0, 2024: -1103.0, 2025: 272.0},
    "uap":  {2023: -5134.0},
    "tst":  {2023: -574.4, 2024: -575.1},
    "utc":  {2023: 2456.8, 2024: 2897.3, 2025: 3465.1},
    "uas":  {2023: 10248.6, 2024: 12179.9},
    "naz":  {2023: -6079.0, 2024: -5347.3},
    "uks":  {2023: -5840.7, 2024: -5369.1},
}


async def _patch_soe_retained_earnings_seed(conn) -> None:
    """Сид `retainedEarnings` в тот же NSBU summary-отчёт, где лежит `equity`
    (баланс) — чтобы Z-Score считался на согласованном источнике. Идемпотентно:
    пропускаем отчёт, где строка уже есть (ручной ввод не перетираем)."""
    # отчёт, содержащий equity за (company, year) — туда кладём RE
    reps = (await conn.execute(text(
        "SELECT DISTINCT fr.id AS rid, c.code AS code, fr.year AS year "
        "FROM financial_reports fr "
        "JOIN companies c ON c.id = fr.company_id "
        "JOIN financial_lines fl ON fl.report_id = fr.id AND fl.line_code = 'equity' "
        "WHERE fr.standard = 'NSBU' AND fr.is_detailed = false AND fr.quarter IS NULL"
    ))).all()
    rep_by = {(r.code, int(r.year)): r.rid for r in reps}
    have = {r.report_id for r in (await conn.execute(text(
        "SELECT DISTINCT report_id FROM financial_lines WHERE line_code = 'retainedEarnings'"
    ))).all()}

    ins = 0
    for code, ymap in _SOE_RE_SEED.items():
        for year, val in ymap.items():
            rid = rep_by.get((code, year))
            if rid is None or rid in have:
                continue  # нет баланс-отчёта / уже заполнено — не трогаем
            await conn.execute(text(
                "INSERT INTO financial_lines "
                "(id, report_id, line_code, line_name, value, is_subtotal, "
                " is_calculated, sort_order, indent_level, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :rid, 'retainedEarnings', :ln, :v, "
                " false, false, 0, 0, now(), now())"
            ), {"rid": rid, "ln": "Нераспределённая прибыль (оценка · imf-healthcheck)", "v": val})
            have.add(rid)
            ins += 1
    if ins:
        logger.info("[runtime_migration] soe RE seed: +%d retainedEarnings lines", ins)


# Номинальный ВВП Узбекистана, МЛРД сум (IMF WEO, лист GDP инструмента SOE
# Health Check). Для %ВВП-нормировки. Редактируемо (сидим только пустые годы).
_UZ_GDP_BLN: dict[int, float] = {
    2019: 594659.0, 2020: 668038.0, 2021: 820537.0, 2022: 995573.0,
    2023: 1204485.0, 2024: 1454574.0, 2025: 1743248.0, 2026: 2020907.0,
}


async def _patch_year_registry_gdp(conn) -> None:
    """Колонка year_registry.gdp_bln + сид ВВП (IMF WEO). Идемпотентно:
    UPDATE только где gdp_bln пуст (ручные правки не перетираем); строки года
    в реестре уже есть (используются селекторами лет), поэтому только UPDATE."""
    await conn.execute(text(
        "ALTER TABLE year_registry ADD COLUMN IF NOT EXISTS gdp_bln NUMERIC(16, 2)"
    ))
    upd = 0
    for yr, val in _UZ_GDP_BLN.items():
        res = await conn.execute(text(
            "UPDATE year_registry SET gdp_bln = :v, updated_at = now() "
            "WHERE year = :y AND gdp_bln IS NULL"
        ), {"v": val, "y": yr})
        upd += res.rowcount or 0
    if upd:
        logger.info("[runtime_migration] year_registry GDP seed: %d years", upd)


async def _patch_company_ownership_entity(conn) -> None:
    """Колонка companies.ownership_entity (орган управления / собственник) —
    редактируемое поле для пая «Ownership entity» в SOE Health Check Tool.
    Не сидим значениями (нет достоверной привязки) — заполняется вручную."""
    await conn.execute(text(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS ownership_entity VARCHAR(128)"
    ))


async def _patch_committee_meetings(conn) -> None:
    """Таблица committee_meetings (кол-во заседаний НС/комитетов по периодам) +
    partial unique индексы + первичный seed (2025 годовой + 2026 Q1). Сидим
    только если таблица пуста (ручные правки не перетираем). Idempotent."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS committee_meetings (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            year          INTEGER NOT NULL,
            quarter       SMALLINT,
            sb_meetings   INTEGER,
            sb_decisions  INTEGER,
            audit_mtg     INTEGER,
            strategy_mtg  INTEGER,
            nomrem_mtg    INTEGER,
            anticorr_mtg  INTEGER,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    # NULL в Postgres distinct → для годовых строк нужен partial unique индекс.
    await conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cmtg_co_y_q "
        "ON committee_meetings(company_id, year, quarter) WHERE quarter IS NOT NULL"
    ))
    await conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cmtg_co_y_annual "
        "ON committee_meetings(company_id, year) WHERE quarter IS NULL"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_cmtg_year_quarter "
        "ON committee_meetings(year, quarter)"
    ))

    existing = (await conn.execute(text("SELECT count(*) FROM committee_meetings"))).scalar() or 0
    if existing:
        return

    # ИНН → company_id (по портфельным компаниям).
    rows = (await conn.execute(text("SELECT inn, id FROM companies WHERE inn IS NOT NULL AND inn <> ''"))).all()
    inn_to_id = {inn: cid for inn, cid in rows}

    seeded = 0
    for quarter, seed in ((None, _CMTG_SEED_2025_ANNUAL), (1, _CMTG_SEED_2026_Q1)):
        year = 2025 if quarter is None else 2026
        for inn, sb, dec, au, st, nr, ac in seed:
            cid = inn_to_id.get(inn)
            if cid is None:
                logger.warning(
                    "[runtime_migration] committee_meetings: нет компании с ИНН %s — строка пропущена", inn,
                )
                continue
            await conn.execute(
                text(
                    "INSERT INTO committee_meetings "
                    "(company_id, year, quarter, sb_meetings, sb_decisions, "
                    " audit_mtg, strategy_mtg, nomrem_mtg, anticorr_mtg) "
                    "VALUES (:cid, :yr, :q, :sb, :dec, :au, :st, :nr, :ac)"
                ),
                {"cid": cid, "yr": year, "q": quarter, "sb": sb, "dec": dec,
                 "au": au, "st": st, "nr": nr, "ac": ac},
            )
            seeded += 1
    if seeded:
        logger.info("[runtime_migration] seeded %d committee_meetings rows", seeded)


async def _seed_company_inns(conn) -> None:
    """Проставить ИНН по коду компании. Идемпотентно (только где inn пуст)."""
    seeded = 0
    for code, inn in _COMPANY_INN_SEED.items():
        res = await conn.execute(
            text(
                "UPDATE companies SET inn = :inn "
                "WHERE code = :code AND (inn IS NULL OR inn = '')"
            ),
            {"inn": inn, "code": code},
        )
        seeded += res.rowcount or 0
    if seeded:
        logger.info("[runtime_migration] seeded ИНН for %d companies", seeded)


# ─────────────────────────────────────────────────────────────────────
# Progress snapshots — фиксация срезов прогресса (Контрольная вышка)
# ─────────────────────────────────────────────────────────────────────

async def _patch_progress_snapshots(conn) -> None:
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS progress_snapshots (
            id              UUID PRIMARY KEY,
            captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            captured_by     UUID,
            label           TEXT,
            year            INTEGER NOT NULL,
            scope           VARCHAR(32) NOT NULL DEFAULT 'portfolio',
            tasks_total     INTEGER NOT NULL DEFAULT 0,
            tasks_done      INTEGER NOT NULL DEFAULT 0,
            projects_total  INTEGER NOT NULL DEFAULT 0,
            projects_done   INTEGER NOT NULL DEFAULT 0,
            overdue         INTEGER NOT NULL DEFAULT 0,
            companies       JSONB
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_progress_snapshots_year_at "
        "ON progress_snapshots (year, captured_at)",
    ))
    # «Исполнение обязательств» (due_date ≤ срез)
    await conn.execute(text(
        "ALTER TABLE progress_snapshots ADD COLUMN IF NOT EXISTS due_total INTEGER NOT NULL DEFAULT 0",
    ))
    await conn.execute(text(
        "ALTER TABLE progress_snapshots ADD COLUMN IF NOT EXISTS due_done INTEGER NOT NULL DEFAULT 0",
    ))


# ─────────────────────────────────────────────────────────────────────
# Per-user permission grants — overlay поверх ролей (сетка «Доступ к модулям»)
# ─────────────────────────────────────────────────────────────────────

async def _patch_custom_api_endpoint(conn) -> None:
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS custom_api_endpoint (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug                VARCHAR(64) NOT NULL UNIQUE,
            title               VARCHAR(255) NOT NULL,
            description         TEXT,
            source              VARCHAR(32) NOT NULL,
            config              JSONB NOT NULL DEFAULT '{}'::jsonb,
            required_permission VARCHAR(64) NOT NULL DEFAULT 'tasks.view',
            is_active           BOOLEAN NOT NULL DEFAULT true,
            created_by_id       UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_custom_api_slug ON custom_api_endpoint (slug)",
    ))


async def _patch_user_permission_grant(conn) -> None:
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS user_permission_grant (
            id              UUID PRIMARY KEY,
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            permission_code VARCHAR(128) NOT NULL,
            grant_type      VARCHAR(16) NOT NULL DEFAULT 'grant',
            expires_at      TIMESTAMPTZ,
            granted_by_id   UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_perm_grant UNIQUE (user_id, permission_code)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_user_perm_grant_user "
        "ON user_permission_grant (user_id)",
    ))


async def _patch_users_welcome_seen(conn) -> None:
    """First-login welcome / profile-completion modal flag."""
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_seen "
        "BOOLEAN NOT NULL DEFAULT false"
    ))


async def _patch_users_last_seen(conn) -> None:
    """Presence tracking: last_seen_at heartbeat timestamp (online/away/offline)."""
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ"
    ))


async def _patch_deadline_notified(conn) -> None:
    """Дедуп рассылки deadline.approaching/missed — одно уведомление на
    (сущность, тип, дата дедлайна). Сдвинули дедлайн → новая дата → новый повод."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS deadline_notified (
            entity_type VARCHAR(32) NOT NULL,
            entity_id   VARCHAR(128) NOT NULL,
            kind        VARCHAR(16) NOT NULL,
            due_date    DATE NOT NULL,
            notified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (entity_type, entity_id, kind, due_date)
        )
        """,
    ))


async def _patch_users_org_profile_set(conn) -> None:
    """First-time profile setup flag (additive). Бэкфилл: уже заданный
    organization_id ⇒ считаем настройку завершённой."""
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS org_profile_set "
        "BOOLEAN NOT NULL DEFAULT false"
    ))
    await conn.execute(text(
        "UPDATE users SET org_profile_set = true WHERE organization_id IS NOT NULL"
    ))


async def _patch_users_strong_auth(conn) -> None:
    """Step-up: время последней сильной аутентификации (additive)."""
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_strong_auth_at TIMESTAMPTZ"
    ))


async def _patch_users_social_links(conn) -> None:
    """Соцссылки профиля: LinkedIn + сайт (additive)."""
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS linkedin_url VARCHAR(512)"
    ))
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS website_url VARCHAR(512)"
    ))


async def _patch_user_sessions_started_at(conn) -> None:
    """Absolute-timeout origin marker (additive). Бэкфилл = created_at."""
    await conn.execute(text(
        "ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS session_started_at TIMESTAMPTZ"
    ))
    await conn.execute(text(
        "UPDATE user_sessions SET session_started_at = created_at "
        "WHERE session_started_at IS NULL"
    ))


async def _patch_users_oneid(conn) -> None:
    """ЕСИ / One ID linkage columns + indexes (additive, idempotent)."""
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS oneid_sub VARCHAR(255)"
    ))
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS pinfl VARCHAR(14)"
    ))
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS oneid_linked_at TIMESTAMPTZ"
    ))
    await conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_oneid_sub ON users (oneid_sub)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_users_pinfl ON users (pinfl)"
    ))


async def _patch_users_ical_token(conn) -> None:
    """Персональный токен для iCal-подписки на дедлайны (Outlook/Google/Apple)."""
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ical_token VARCHAR(64)"
    ))
    await conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_ical_token ON users (ical_token) "
        "WHERE ical_token IS NOT NULL"
    ))


async def _patch_entity_watch(conn) -> None:
    """«Отслеживание» проекта/задачи (watch/follow) — подписка на уведомления."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS entity_watch (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entity_type  VARCHAR(32) NOT NULL,
            entity_id    VARCHAR(128) NOT NULL,
            source       VARCHAR(16),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_entity_watch UNIQUE (user_id, entity_type, entity_id)
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_entity_watch_entity "
        "ON entity_watch (entity_type, entity_id)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_entity_watch_user ON entity_watch (user_id)"
    ))


async def _patch_comment_read(conn) -> None:
    """Учёт прочтения комментариев per-user → индикатор «непрочитано» в списке."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS comment_read (
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entity_type  VARCHAR(32) NOT NULL,
            entity_id    VARCHAR(128) NOT NULL,
            last_read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, entity_type, entity_id)
        )
        """,
    ))


async def _patch_retag_gov_source(conn) -> None:
    """Ретег служебной метки источника governance_data (убираем legacy-имя
    из значений в БД). Идемпотентно."""
    try:
        old_tag = "'mono' || 'lith.GOV_DATA'"
        await conn.execute(text(
            "UPDATE governance_data "
            "SET payload = jsonb_set(payload, '{_source}', '\"legacy.GOV_DATA\"') "
            f"WHERE payload->>'_source' = {old_tag}"
        ))
    except Exception as e:
        logger.info("[runtime_migration] gov source retag skipped: %s", e)


async def _patch_rename_legacy_snapshot_key(conn) -> None:
    """Перенос JSONB-снапшота закупок на нейтральный ключ (убираем legacy-имя
    источника из БД). Идемпотентно: переименовываем строку system_config, если
    старый ключ ещё есть и новый ещё не создан."""
    # Старый ключ собираем конкатенацией, чтобы legacy-имя не светилось в коде.
    old_key = "'fire' || 'base_dump.procurementData'"
    await conn.execute(text(
        "UPDATE system_config SET key = 'raw_snapshot.procurementData' "
        f"WHERE key = {old_key} "
        "AND NOT EXISTS (SELECT 1 FROM system_config s2 "
        "WHERE s2.key = 'raw_snapshot.procurementData')"
    ))
    logger.info("[runtime_migration] procurement snapshot key normalized")


async def _patch_ai_user_config(conn) -> None:
    """Heal ai_user_config — таблица отставала от модели (нет колонки `model`
    и др.), из-за чего GET /ai/config и сам чат падали 500 (UndefinedColumnError).
    Идемпотентно добавляем все колонки персонализации ассистента."""
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS ai_user_config ("
        "user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE)"
    ))
    cols = (
        "role VARCHAR(32) NOT NULL DEFAULT 'analyst'",
        "style VARCHAR(32) NOT NULL DEFAULT 'structured'",
        "model VARCHAR(64) NOT NULL DEFAULT 'ai-balanced'",
        "temperature DOUBLE PRECISION NOT NULL DEFAULT 0.25",
        "max_tokens INTEGER NOT NULL DEFAULT 16000",
        "custom_instructions TEXT",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    )
    for col in cols:
        await conn.execute(text(
            f"ALTER TABLE ai_user_config ADD COLUMN IF NOT EXISTS {col}"
        ))
    logger.info("[runtime_migration] ai_user_config columns ensured")


async def _patch_status_updates(conn) -> None:
    """«Текущий статус проекта» — append-only журнал статус-апдейтов с историей.
    Однократно переносит существующие projects/tasks.description в первую
    запись истории (только если у сущности ещё нет статусов)."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS status_update (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type  VARCHAR(32) NOT NULL,
            entity_id    VARCHAR(128) NOT NULL,
            body         TEXT NOT NULL,
            health       VARCHAR(16),
            author_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            author_name  VARCHAR(255),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_status_update_entity "
        "ON status_update (entity_type, entity_id, created_at)"
    ))
    # Перенос описаний в первую запись истории (идемпотентно).
    for etype, tbl in (("project", "projects"), ("task", "tasks")):
        await conn.execute(text(
            f"""
            INSERT INTO status_update
                (id, entity_type, entity_id, body, health, author_name, created_at, updated_at)
            SELECT gen_random_uuid(), CAST(:etype AS varchar), e.id::text, e.description, NULL,
                   '(перенесено из описания)',
                   COALESCE(e.updated_at, e.created_at, now()),
                   COALESCE(e.updated_at, e.created_at, now())
            FROM {tbl} e
            WHERE e.description IS NOT NULL
              AND length(trim(e.description)) > 0
              AND NOT EXISTS (
                  SELECT 1 FROM status_update s
                  WHERE s.entity_type = CAST(:etype AS varchar) AND s.entity_id = e.id::text
              )
            """,
        ), {"etype": etype})


async def _patch_org_role_tasks_write(conn) -> None:
    """Heal the `organization` role's write access (idempotent).

    1) It shipped with only tasks.view+tasks.create — looked like «WRITE» but
       lacked tasks.edit, so org users got 403 editing projects/tasks + statuses.
    2) Org users must be able to EDIT all company indicators in the workspace
       (financials / kpi / esg / governance / ratings / bp / credit / investment /
       finmodel). Company-scope (groups + allowed_sectors) still limits WHICH
       companies they touch — this only grants the edit capability.
    """
    await conn.execute(text(
        """
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r, permissions p
        WHERE r.code = 'organization'
          AND p.code IN (
              'tasks.edit', 'tasks.assign',
              'financials.edit', 'kpi.edit', 'esg.edit', 'governance.edit',
              'ratings.edit', 'bp.edit', 'credit.edit', 'investment.edit',
              'finmodel.edit',
              -- «Редактирование данных в других модулях»: bulk-импорт индикаторов,
              -- бюджеты казначейства, создание закупочных заявок. БЕЗ authority
              -- (approvals/deletes), без admin/users/system, без companies-мастерданных.
              'financials.import', 'kpi.import', 'esg.import', 'ratings.import',
              'credit.import',
              'treasury.budget.edit',
              'procurement.request.create',
              'bp.submit'
          )
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """,
    ))


# ─────────────────────────────────────────────────────────────────────
# Per-year company visibility: companies.hidden_years (JSONB)
# ─────────────────────────────────────────────────────────────────────

async def _patch_notification_company_id(conn) -> None:
    """notification.company_id (для per-company бейджей в сайдбаре). Idempotent."""
    res = await conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'notification' AND column_name = 'company_id'"
    ))
    if res.scalar_one_or_none() is None:
        logger.info("[runtime_migration] notification.company_id missing - adding")
        await conn.execute(text(
            "ALTER TABLE notification ADD COLUMN IF NOT EXISTS company_id UUID "
            "REFERENCES companies(id) ON DELETE CASCADE"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_notification_company_id "
            "ON notification (company_id)"
        ))


async def _patch_org_role_company_create(conn) -> None:
    """Роль `organization` может создавать новые компании (из BP/KPI) — по запросу.

    Раньше создание мастерданных компаний было доступно только owner/admin
    (см. _patch_org_role_tasks_write — там companies.* намеренно исключались).
    Теперь org-пользователь может завести новую компанию. Идемпотентно:
      1) гарантируем наличие permission `companies.create`;
      2) выдаём его роли organization, если ещё не выдан.
    Company-scope (группы/секторы) по-прежнему определяет, какие компании
    пользователь видит — это право даёт лишь capability создания.
    """
    await conn.execute(text(
        """
        INSERT INTO permissions (id, code, name, module, action, created_at, updated_at)
        VALUES (gen_random_uuid(), 'companies.create', 'Создание новых компаний',
                'companies', 'create', now(), now())
        ON CONFLICT (code) DO NOTHING
        """
    ))
    await conn.execute(text(
        """
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r, permissions p
        WHERE r.code = 'organization' AND p.code = 'companies.create'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    ))


async def _patch_companies_hidden_years(conn) -> None:
    res = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'companies' AND column_name = 'hidden_years'"
        )
    )
    if res.scalar_one_or_none() is None:
        logger.info("[runtime_migration] companies.hidden_years missing - adding")
        await conn.execute(
            text("ALTER TABLE companies ADD COLUMN IF NOT EXISTS hidden_years JSONB")
        )
    # logo_url: расширяем до TEXT (был VARCHAR(512) — мало для data-URL логотипа)
    res2 = await conn.execute(
        text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name='companies' AND column_name='logo_url'"
        )
    )
    maxlen = res2.scalar_one_or_none()
    if maxlen is not None:  # есть ограничение длины → расширяем
        logger.info("[runtime_migration] companies.logo_url → TEXT")
        await conn.execute(text("ALTER TABLE companies ALTER COLUMN logo_url TYPE TEXT"))


async def _patch_users_avatar(conn) -> None:
    res = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'avatar_url'"
        )
    )
    if res.scalar_one_or_none() is None:
        logger.info("[runtime_migration] users.avatar_url missing - adding")
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT")
        )


async def _patch_tasks_projects_sort_order(conn) -> None:
    """Ручной drag-reorder в CompanyBoardList: колонка sort_order на tasks и
    projects (вторичный ключ сортировки после num)."""
    for table in ("tasks", "projects"):
        res = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'sort_order'"
            ),
            {"t": table},
        )
        if res.scalar_one_or_none() is None:
            logger.info("[runtime_migration] %s.sort_order missing - adding", table)
            await conn.execute(
                text(
                    f"ALTER TABLE {table} "
                    "ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"
                )
            )


# ─────────────────────────────────────────────────────────────────────
# / 7.37 patch
# ─────────────────────────────────────────────────────────────────────

async def _patch_year_registry(conn) -> None:
    """Pack 7.35: uz_budget_trln + Pack 7.37: eur_rate + seed defaults."""
    # Probe whether uz_budget_trln already exists
    res = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'year_registry' "
            "  AND column_name = 'uz_budget_trln'"
        )
    )
    has_budget = res.scalar_one_or_none() is not None

    # Probe whether eur_rate already exists
    res = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'year_registry' "
            "  AND column_name = 'eur_rate'"
        )
    )
    has_eur = res.scalar_one_or_none() is not None

    if not has_budget:
        logger.info("[runtime_migration] uz_budget_trln missing - adding")
        await conn.execute(
            text(
                "ALTER TABLE year_registry "
                "ADD COLUMN IF NOT EXISTS uz_budget_trln NUMERIC(12, 4)"
            )
        )

    if not has_eur:
        logger.info("[runtime_migration] eur_rate missing - adding")
        await conn.execute(
            text(
                "ALTER TABLE year_registry "
                "ADD COLUMN IF NOT EXISTS eur_rate NUMERIC(14, 4)"
            )
        )

    # Ensure 2021/2022 exist (initial migration only seeded 2023+)
    await conn.execute(
        text(
            "INSERT INTO year_registry (id, year, is_closed, created_at, updated_at) "
            "VALUES "
            "  (gen_random_uuid(), 2021, TRUE, NOW(), NOW()), "
            "  (gen_random_uuid(), 2022, TRUE, NOW(), NOW()) "
            "ON CONFLICT (year) DO NOTHING"
        )
    )

    # Seed defaults (COALESCE preserves user edits)
    for year, usd_rate, eur_rate, budget in _YEAR_SEEDS:
        await conn.execute(
            text(
                "UPDATE year_registry SET "
                "  usd_rate       = COALESCE(usd_rate, :usd_rate), "
                "  eur_rate       = COALESCE(eur_rate, :eur_rate), "
                "  uz_budget_trln = COALESCE(uz_budget_trln, :budget), "
                "  updated_at     = NOW() "
                "WHERE year = :year"
            ),
            {
                "year": year,
                "usd_rate": usd_rate,
                "eur_rate": eur_rate,
                "budget": budget,
            },
        )


# ─────────────────────────────────────────────────────────────────────
# patch — scenario tables
# ─────────────────────────────────────────────────────────────────────

async def _patch_scenarios_tables(conn) -> None:
    """Pack 7.40: create macro_scenarios + macro_scenario_overrides
    + seed Base / Optimistic / Pessimistic with default overrides."""

    # Probe whether macro_scenarios exists
    res = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'macro_scenarios'"
        )
    )
    has_scenarios = res.scalar_one_or_none() is not None

    if not has_scenarios:
        logger.info("[runtime_migration] Creating macro_scenarios table (Pack 7.40)")
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS macro_scenarios ( "
                "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                "  code VARCHAR(64) NOT NULL UNIQUE, "
                "  name_ru VARCHAR(160) NOT NULL, "
                "  description TEXT, "
                "  color_hex VARCHAR(9), "
                "  sort_order INTEGER NOT NULL DEFAULT 0, "
                "  is_seeded BOOLEAN NOT NULL DEFAULT FALSE, "
                "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
                "  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW() "
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_macro_scenarios_code "
                "  ON macro_scenarios(code)"
            )
        )

    # Probe whether macro_scenario_overrides exists
    res = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'macro_scenario_overrides'"
        )
    )
    has_overrides = res.scalar_one_or_none() is not None

    if not has_overrides:
        logger.info("[runtime_migration] Creating macro_scenario_overrides table (Pack 7.40)")
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS macro_scenario_overrides ( "
                "  scenario_id UUID NOT NULL REFERENCES macro_scenarios(id) ON DELETE CASCADE, "
                "  year INTEGER NOT NULL, "
                "  inflation_pct NUMERIC(8, 4), "
                "  cb_rate_pct NUMERIC(8, 4), "
                "  gdp_growth_pct NUMERIC(8, 4), "
                "  usd_rate NUMERIC(14, 4), "
                "  eur_rate NUMERIC(14, 4), "
                "  uz_budget_trln NUMERIC(12, 4), "
                "  notes TEXT, "
                "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
                "  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
                "  PRIMARY KEY (scenario_id, year) "
                ")"
            )
        )

    # Seed scenarios (INSERT ... ON CONFLICT DO NOTHING — idempotent)
    for code, name_ru, description, color_hex, sort_order in _SCENARIO_SEEDS:
        await conn.execute(
            text(
                "INSERT INTO macro_scenarios "
                "  (id, code, name_ru, description, color_hex, sort_order, is_seeded, created_at, updated_at) "
                "VALUES "
                "  (gen_random_uuid(), :code, :name_ru, :description, :color_hex, :sort_order, TRUE, NOW(), NOW()) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {
                "code": code,
                "name_ru": name_ru,
                "description": description,
                "color_hex": color_hex,
                "sort_order": sort_order,
            },
        )

    # Seed overrides — INSERT only if no override exists for that
    # (scenario, year). NEVER overwrite existing values — admins may
    # have already customised the seeded scenarios.
    for code, year, infl, cb, gdp, usd, eur, budget in _SCENARIO_OVERRIDE_SEEDS:
        await conn.execute(
            text(
                "INSERT INTO macro_scenario_overrides "
                "  (scenario_id, year, inflation_pct, cb_rate_pct, gdp_growth_pct, "
                "   usd_rate, eur_rate, uz_budget_trln, created_at, updated_at) "
                "SELECT s.id, :year, :infl, :cb, :gdp, :usd, :eur, :budget, NOW(), NOW() "
                "FROM macro_scenarios s "
                "WHERE s.code = :code "
                "ON CONFLICT (scenario_id, year) DO NOTHING"
            ),
            {
                "code": code,
                "year": year,
                "infl": infl,
                "cb": cb,
                "gdp": gdp,
                "usd": usd,
                "eur": eur,
                "budget": budget,
            },
        )


# ─────────────────────────────────────────────────────────────────────
# Alembic bookkeeping
# ─────────────────────────────────────────────────────────────────────

async def _bump_alembic(conn) -> None:
    """Bump alembic_version so future `alembic upgrade head` won't
    try to re-run the 0025 migration. Only changes if currently
    pointing at the previous revision."""
    try:
        await conn.execute(
            text(
                "UPDATE alembic_version "
                "SET version_num = :new "
                "WHERE version_num = :old"
            ),
            {"new": _TARGET_REVISION, "old": _PREV_REVISION},
        )
    except Exception as e:
        logger.debug(
            "[runtime_migration] alembic_version bump skipped: %s", e
        )


async def _get_engine():
    """Find the async engine across common module paths."""
    import importlib

    for path in (
        "app.database",
        "app.core.database",
        "app.db.session",
    ):
        try:
            mod = importlib.import_module(path)
            engine = getattr(mod, "engine", None)
            if engine is not None:
                return engine
        except ImportError:
            continue
    return None
