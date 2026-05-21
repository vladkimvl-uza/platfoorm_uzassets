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

    _orig_add_column   = op.add_column
    _orig_create_table = op.create_table
    _orig_create_index = op.create_index
    _orig_create_fk    = op.create_foreign_key
    _orig_create_uq    = op.create_unique_constraint
    _orig_drop_column  = op.drop_column
    _orig_drop_index   = op.drop_index
    _orig_drop_table   = op.drop_table

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
        if not _has_table(table):
            return False
        ucs = _insp().get_unique_constraints(table)
        fks = _insp().get_foreign_keys(table)
        return any(c.get("name") == name for c in (ucs + fks))

    def add_column(table_name, column, *args, **kw):
        if _has_column(table_name, column.name):
            log.info("[idempotent] skip add_column %s.%s — exists", table_name, column.name)
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

    op.add_column = add_column
    op.create_table = create_table
    op.create_index = create_index
    op.create_foreign_key = create_foreign_key
    op.create_unique_constraint = create_unique_constraint
    op.drop_column = drop_column
    op.drop_index = drop_index
    op.drop_table = drop_table


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
