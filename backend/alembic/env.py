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

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
