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
# Pack 7.35 / 7.37 — year_registry seeds
# ─────────────────────────────────────────────────────────────────────

# (year, usd_rate, eur_rate, uz_budget_trln) — matches Pack 7.35/7.37 migration
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
# Pack 7.40 — scenario seeds (3 defaults)
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
            await _patch_users_welcome_seen(conn)
            await _patch_users_last_seen(conn)
            await _patch_status_updates(conn)
            await _patch_comment_read(conn)
            await _patch_entity_watch(conn)
            await _patch_users_ical_token(conn)
            await _patch_deadline_notified(conn)
            await _bump_alembic(conn)
    except Exception as e:
        # Never crash the app on a self-heal failure - just log and continue.
        logger.warning(
            "[runtime_migration] self-heal failed (continuing): %s", e
        )


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
# Pack 7.35 / 7.37 patch
# ─────────────────────────────────────────────────────────────────────

async def _patch_year_registry(conn) -> None:
    """Pack 7.35: uz_budget_trln + Pack 7.37: eur_rate + seed defaults."""
    # Probe whether uz_budget_trln (Pack 7.35) already exists
    res = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'year_registry' "
            "  AND column_name = 'uz_budget_trln'"
        )
    )
    has_budget = res.scalar_one_or_none() is not None

    # Probe whether eur_rate (Pack 7.37) already exists
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
# Pack 7.40 patch — scenario tables
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
