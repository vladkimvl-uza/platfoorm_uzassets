"""Persistence helpers for /admin/db console (Pack 149).

Owns the superuser AsyncEngine + introspection / row-mutate primitives.
The session passed to `_audit` (regular least-privilege role) stays in the
route — it's not this repo's responsibility.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)

from app.config import settings


# ─── Admin engine (DATABASE_URL_ADMIN, superuser — нужно для DDL) ─

_ADMIN_DB_URL = (
    os.environ.get("DATABASE_URL_ADMIN")
    or os.environ.get("DATABASE_URL")
    or settings.DATABASE_URL
)
if _ADMIN_DB_URL.startswith("postgresql+psycopg://"):
    _ADMIN_DB_URL = _ADMIN_DB_URL.replace(
        "postgresql+psycopg://", "postgresql+asyncpg://", 1,
    )
elif _ADMIN_DB_URL.startswith("postgresql://"):
    _ADMIN_DB_URL = _ADMIN_DB_URL.replace(
        "postgresql://", "postgresql+asyncpg://", 1,
    )

_admin_engine = create_async_engine(
    _ADMIN_DB_URL,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=2,
    echo=False,
)
_AdminSession = async_sessionmaker(_admin_engine, expire_on_commit=False)


def admin_session() -> AsyncSession:
    """Return a fresh AsyncSession bound to the superuser engine."""
    return _AdminSession()


# ─── Introspection ────────────────────────────────────────────────

_SCHEMA_TABLES_SQL = """
    SELECT
        n.nspname AS schema,
        c.relname AS name,
        c.reltuples::bigint AS row_count_est,
        pg_total_relation_size(c.oid) AS size_bytes
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r'
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    ORDER BY n.nspname, c.relname
"""

_SCHEMA_COLUMNS_SQL = """
    SELECT
        c.table_schema, c.table_name, c.column_name,
        c.data_type, c.is_nullable, c.column_default,
        c.character_maximum_length
    FROM information_schema.columns c
    WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY c.table_schema, c.table_name, c.ordinal_position
"""

_SCHEMA_PK_SQL = """
    SELECT tc.table_schema, tc.table_name, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
"""

_SCHEMA_FK_SQL = """
    SELECT
        tc.table_schema, tc.table_name, kcu.column_name,
        ccu.table_schema AS foreign_schema,
        ccu.table_name   AS foreign_table,
        ccu.column_name  AS foreign_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name
     AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
"""

_SCHEMA_IDX_SQL = """
    SELECT
        n.nspname AS schema,
        c.relname AS table,
        i.relname AS index_name,
        pg_get_indexdef(ix.indexrelid) AS definition,
        ix.indisunique AS is_unique,
        ix.indisprimary AS is_primary
    FROM pg_index ix
    JOIN pg_class c  ON c.oid  = ix.indrelid
    JOIN pg_class i  ON i.oid  = ix.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
    ORDER BY n.nspname, c.relname, i.relname
"""


class DbAdminRepository:
    """Wrapper that opens its OWN superuser AsyncSession per call.

    Unlike most other repos in this codebase, this repo does NOT share the
    request's regular session — its work needs DDL/DELETE rights only the
    superuser DATABASE_URL_ADMIN has.
    """

    async def db_meta(self) -> dict:
        async with admin_session() as adb:
            db_size = (await adb.execute(
                text("SELECT pg_database_size(current_database())")
            )).scalar()
            ver = (await adb.execute(text("SELECT version()"))).scalar()
            return {
                "size_bytes": int(db_size) if db_size else None,
                "version": str(ver) if ver else None,
            }

    async def list_tables(self) -> list:
        async with admin_session() as adb:
            return (await adb.execute(text(_SCHEMA_TABLES_SQL))).fetchall()

    async def list_columns(self) -> list:
        async with admin_session() as adb:
            return (await adb.execute(text(_SCHEMA_COLUMNS_SQL))).fetchall()

    async def list_pks(self) -> list:
        async with admin_session() as adb:
            return (await adb.execute(text(_SCHEMA_PK_SQL))).fetchall()

    async def list_fks(self) -> list:
        async with admin_session() as adb:
            return (await adb.execute(text(_SCHEMA_FK_SQL))).fetchall()

    async def list_indexes(self) -> list:
        async with admin_session() as adb:
            return (await adb.execute(text(_SCHEMA_IDX_SQL))).fetchall()

    async def count_table(self, table: str) -> int:
        async with admin_session() as adb:
            return int((await adb.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            )).scalar() or 0)

    async def browse_table(
        self,
        table: str,
        *,
        limit: int,
        offset: int,
        order_by: Optional[str],
        order_dir: str,
    ) -> tuple[list[str], list]:
        order_clause = (
            f'ORDER BY "{order_by}" {order_dir}' if order_by else ""
        )
        async with admin_session() as adb:
            rows_q = await adb.execute(
                text(
                    f'SELECT * FROM "{table}" {order_clause} '
                    f'LIMIT :lim OFFSET :off'
                ),
                {"lim": limit, "off": offset},
            )
            cols = list(rows_q.keys())
            rows = rows_q.fetchall()
            return cols, rows

    async def update_row(
        self,
        *,
        table: str,
        pk_column: str,
        pk_value: Any,
        values: dict[str, Any],
        statement_timeout_seconds: int,
    ) -> Optional[dict]:
        set_clauses = ", ".join([f'"{k}" = :{k}' for k in values.keys()])
        sql = (
            f'UPDATE "{table}" SET {set_clauses} '
            f'WHERE "{pk_column}" = :_pk RETURNING *'
        )
        async with admin_session() as adb:
            await adb.execute(
                text(f"SET LOCAL statement_timeout = '{statement_timeout_seconds}s'")
            )
            result = await adb.execute(
                text(sql), {**values, "_pk": pk_value},
            )
            updated: Optional[dict] = None
            if result.returns_rows:
                row_data = result.fetchone()
                if row_data:
                    updated = dict(row_data._mapping)
            await adb.commit()
            return updated

    async def delete_row(
        self,
        *,
        table: str,
        pk_column: str,
        pk_value: str,
        statement_timeout_seconds: int,
    ) -> int:
        sql = f'DELETE FROM "{table}" WHERE "{pk_column}" = :_pk'
        async with admin_session() as adb:
            await adb.execute(
                text(f"SET LOCAL statement_timeout = '{statement_timeout_seconds}s'")
            )
            result = await adb.execute(text(sql), {"_pk": pk_value})
            await adb.commit()
            return int(result.rowcount or 0)

    async def execute_raw(
        self, sql: str, *, dry_run: bool, statement_timeout_seconds: int,
    ) -> dict:
        """Run arbitrary SQL on the admin engine. Returns columns/rows/
        rowcount; commits unless `dry_run=True`."""
        async with admin_session() as adb:
            await adb.execute(
                text(f"SET LOCAL statement_timeout = '{statement_timeout_seconds}s'")
            )
            result = await adb.execute(text(sql))
            out: dict = {
                "columns": [],
                "rows": [],
                "row_count": 0,
                "truncated": False,
            }
            if result.returns_rows:
                out["columns"] = list(result.keys())
                from app.services.db_admin_console.service import MAX_ROWS
                fetched = result.fetchmany(MAX_ROWS + 1)
                if len(fetched) > MAX_ROWS:
                    out["truncated"] = True
                    fetched = fetched[:MAX_ROWS]
                out["rows"] = [list(row) for row in fetched]
                out["row_count"] = len(out["rows"])
            else:
                out["row_count"] = result.rowcount or 0
            if dry_run:
                await adb.rollback()
            else:
                await adb.commit()
            return out
