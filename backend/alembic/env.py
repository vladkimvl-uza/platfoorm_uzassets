"""Alembic environment configuration.

Uses the synchronous DB URL from settings (psycopg) for migrations.
The application itself uses async (asyncpg)."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base

# Force-load all model modules so they register with Base.metadata.
# `app.models.__init__` imports a subset; this auto-discovery walks the whole
# package so cross-table FKs (e.g. users.partner_id → integration_partner)
# resolve cleanly during migration / autogenerate.
import importlib
import pkgutil
import app.models as _models_pkg  # noqa: F401
for _finder, _modname, _ispkg in pkgutil.iter_modules(_models_pkg.__path__):
    try:
        importlib.import_module(f"app.models.{_modname}")
    except Exception:
        # A broken model module shouldn't take alembic down; CI will catch it elsewhere.
        pass

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

# Set up Python logging from .ini config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# =====================================================================
# Idempotent op-patching
# =====================================================================
# 0001_initial использует Base.metadata.create_all → создаёт ВСЕ таблицы
# и колонки по текущим моделям. Потом 0005, 0006, ... пытаются делать
# add_column / create_table / create_index — они падают DuplicateColumn /
# DuplicateTable на свежей БД.
#
# Это известный костыль для гибрида create_all + alembic. Решение:
# обернуть schema-mutating ops чтобы они проверяли существование цели
# и no-op'или если она уже есть.
def _install_idempotent_ops() -> None:
    import logging
    from alembic import op
    from sqlalchemy import inspect

    log = logging.getLogger("alembic.idempotent")

    from sqlalchemy.exc import ProgrammingError, IntegrityError

    _orig_add_column   = op.add_column
    _orig_create_table = op.create_table
    _orig_create_index = op.create_index
    _orig_create_fk    = op.create_foreign_key
    _orig_create_uq    = op.create_unique_constraint
    _orig_create_check = op.create_check_constraint
    _orig_create_pk    = op.create_primary_key
    _orig_drop_column  = op.drop_column
    _orig_drop_index   = op.drop_index
    _orig_drop_table   = op.drop_table
    _orig_drop_constr  = op.drop_constraint
    _orig_execute      = op.execute

    def _insp():
        return inspect(op.get_bind())

    def _has_table(name: str) -> bool:
        return name in _insp().get_table_names()

    def _has_column(table: str, col: str) -> bool:
        if not _has_table(table):
            return False
        return any(c["name"] == col for c in _insp().get_columns(table))

    def _has_index(table: str, idx: str) -> bool:
        if not _has_table(table):
            return False
        return any(i["name"] == idx for i in _insp().get_indexes(table))

    def _has_constraint(table: str, name: str) -> bool:
        """True если constraint с таким именем существует в таблице
        (unique / foreign-key / check / primary-key — все типы)."""
        if not _has_table(table):
            return False
        try:
            ucs    = _insp().get_unique_constraints(table)
            fks    = _insp().get_foreign_keys(table)
            checks = _insp().get_check_constraints(table)
            pk     = _insp().get_pk_constraint(table)
        except Exception:
            return False
        all_names = []
        for c in ucs + fks + checks:
            n = c.get("name")
            if n:
                all_names.append(n)
        if pk and pk.get("name"):
            all_names.append(pk["name"])
        return name in all_names

    def add_column(table_name, column, *args, **kw):
        if _has_column(table_name, column.name):
            log.info("[idempotent] skip add_column %s.%s — exists", table_name, column.name)
            # Если в спеке был server_default, применим его на существующую
            # колонку (create_all в 0001 его не выставил — он берётся только
            # из server_default атрибута модели).
            sd = getattr(column, "server_default", None)
            if sd is not None:
                try:
                    from sqlalchemy import text
                    default_expr = sd.arg if hasattr(sd, "arg") else str(sd)
                    if hasattr(default_expr, "text"):
                        default_expr = default_expr.text
                    bind = op.get_bind()
                    sp = bind.begin_nested()
                    try:
                        bind.execute(text(
                            f'ALTER TABLE "{table_name}" '
                            f'ALTER COLUMN "{column.name}" '
                            f'SET DEFAULT {default_expr}'
                        ))
                        sp.commit()
                        log.info("[idempotent] set default for %s.%s", table_name, column.name)
                    except Exception as e:
                        sp.rollback()
                        log.warning("[idempotent] could not set default: %s", e)
                except Exception:
                    pass
            return
        return _orig_add_column(table_name, column, *args, **kw)

    def create_table(name, *cols, **kw):
        if _has_table(name):
            log.info("[idempotent] skip create_table %s — exists", name)
            return
        return _orig_create_table(name, *cols, **kw)

    def create_index(name, table_name, *args, **kw):
        if _has_index(table_name, name):
            log.info("[idempotent] skip create_index %s on %s — exists", name, table_name)
            return
        return _orig_create_index(name, table_name, *args, **kw)

    def create_foreign_key(name, source, *args, **kw):
        if name and _has_constraint(source, name):
            log.info("[idempotent] skip create_fk %s on %s — exists", name, source)
            return
        return _orig_create_fk(name, source, *args, **kw)

    def create_unique_constraint(name, source, *args, **kw):
        if name and _has_constraint(source, name):
            log.info("[idempotent] skip create_uq %s on %s — exists", name, source)
            return
        return _orig_create_uq(name, source, *args, **kw)

    def drop_column(table_name, column_name, *args, **kw):
        if not _has_column(table_name, column_name):
            log.info("[idempotent] skip drop_column %s.%s — gone", table_name, column_name)
            return
        return _orig_drop_column(table_name, column_name, *args, **kw)

    def drop_index(name, table_name=None, *args, **kw):
        if table_name and not _has_index(table_name, name):
            log.info("[idempotent] skip drop_index %s — gone", name)
            return
        try:
            return _orig_drop_index(name, table_name, *args, **kw)
        except Exception as e:
            log.warning("[idempotent] drop_index %s soft-fail: %s", name, e)

    def drop_table(name, *args, **kw):
        if not _has_table(name):
            log.info("[idempotent] skip drop_table %s — gone", name)
            return
        return _orig_drop_table(name, *args, **kw)

    def create_check_constraint(name, source, *args, **kw):
        if name and _has_constraint(source, name):
            log.info("[idempotent] skip create_check %s on %s — exists", name, source)
            return
        return _orig_create_check(name, source, *args, **kw)

    def create_primary_key(name, source, *args, **kw):
        if name and _has_constraint(source, name):
            log.info("[idempotent] skip create_pk %s on %s — exists", name, source)
            return
        return _orig_create_pk(name, source, *args, **kw)

    def drop_constraint(name, table_name, *args, **kw):
        if not _has_constraint(table_name, name):
            log.info("[idempotent] skip drop_constraint %s on %s — gone", name, table_name)
            return
        try:
            return _orig_drop_constr(name, table_name, *args, **kw)
        except Exception as e:
            log.warning("[idempotent] drop_constraint %s soft-fail: %s", name, e)

    def execute(sql, *args, **kw):
        """SAVEPOINT-wrapped op.execute. Если raw SQL ссылается на
        несуществующие колонки/таблицы (часто случается с data-backfill
        миграциями на свежей БД, где create_all создал только финальную
        схему) — откатываем savepoint, логируем warning, не падаем."""
        bind = op.get_bind()
        sp = bind.begin_nested()
        try:
            result = _orig_execute(sql, *args, **kw)
            sp.commit()
            return result
        except (ProgrammingError, IntegrityError) as e:
            orig = getattr(e, "orig", None)
            orig_name = type(orig).__name__ if orig else type(e).__name__
            sp.rollback()
            # Конкретно эти классы ошибок — следствие гибрида create_all+alembic,
            # все остальные пробрасываем.
            tolerable = {
                "UndefinedColumn", "UndefinedTable", "UndefinedObject",
                "DuplicateObject", "DuplicateColumn", "DuplicateTable",
                "DuplicateIndex", "DuplicateAlias", "InFailedSqlTransaction",
            }
            if orig_name in tolerable:
                snippet = str(sql).strip()[:120].replace("\n", " ")
                log.warning("[idempotent] skip op.execute (%s): %s…", orig_name, snippet)
                return None
            raise

    op.add_column = add_column
    op.create_table = create_table
    op.create_index = create_index
    op.create_foreign_key = create_foreign_key
    op.create_unique_constraint = create_unique_constraint
    op.create_check_constraint = create_check_constraint
    op.create_primary_key = create_primary_key
    op.drop_column = drop_column
    op.drop_index = drop_index
    op.drop_table = drop_table
    op.drop_constraint = drop_constraint
    op.execute = execute


def run_migrations_offline() -> None:
    """Generate migration SQL without a live DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        # Wire idempotent ops AFTER context is configured (op.get_bind needs it).
        _install_idempotent_ops()

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
