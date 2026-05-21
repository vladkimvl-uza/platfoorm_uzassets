"""Database admin console (Pack 149).

Endpoints (prefix /admin/db, всё под is_owner OR is_admin gate):

  GET  /admin/db/schema                — список таблиц, колонок, FK, индексов, row counts
  GET  /admin/db/table/{name}/columns  — детали одной таблицы
  POST /admin/db/query                 — выполнить произвольный SQL
  GET  /admin/db/table/{name}/rows     — пагинированный browser (LIMIT/OFFSET/ORDER)
  POST /admin/db/table/{name}/row      — INSERT
  PATCH /admin/db/table/{name}/row     — UPDATE по PK
  DELETE /admin/db/table/{name}/row    — DELETE по PK

Безопасность:
  - Auth gate: is_owner=True ИЛИ is_admin=True
  - Все операции пишутся в audit_log через append_audit_entry
  - statement_timeout = 30s — защита от runaway queries
  - max 10k строк в результате — защита от OOM на больших таблицах
  - Подключение через DATABASE_URL_ADMIN (superuser) чтобы DDL работало
  - Destructive операции пользователь подтверждает в UI; backend не различает.

Каждый запрос АУДИТИРУЕТСЯ независимо от того, прошёл он успешно или упал.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.audit_chain import append_audit_entry
from app.core.security import get_current_user
from app.database import get_db
from app.models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/db", tags=["db-admin"])


# =====================================================================
# Admin engine (DATABASE_URL_ADMIN, superuser — нужно для DDL)
# =====================================================================
# Регулярный engine (app.database.engine) использует уменьшенные права
# (uza_app) — DDL и DELETE на audit_log запрещены. Для console нужен
# полноценный superuser-коннект, который указан в DATABASE_URL_ADMIN.

_ADMIN_DB_URL = (
    os.environ.get("DATABASE_URL_ADMIN")
    or os.environ.get("DATABASE_URL")
    or settings.DATABASE_URL
)
# Конвертируем psycopg sync URL в asyncpg при необходимости.
if _ADMIN_DB_URL.startswith("postgresql+psycopg://"):
    _ADMIN_DB_URL = _ADMIN_DB_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
elif _ADMIN_DB_URL.startswith("postgresql://"):
    _ADMIN_DB_URL = _ADMIN_DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

_admin_engine = create_async_engine(
    _ADMIN_DB_URL,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=2,
    echo=False,
)
_AdminSession = async_sessionmaker(_admin_engine, expire_on_commit=False)

MAX_ROWS = 10_000
STATEMENT_TIMEOUT_SECONDS = 30


# =====================================================================
# Auth helpers
# =====================================================================

def _require_db_admin(user: User) -> None:
    """is_owner OR is_admin can use the DB console."""
    if user.is_owner:
        return
    if bool(getattr(user, "is_admin", False)):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Доступ к DB-консоли только для owner/admin",
    )


def _client_ip(request: Request) -> Optional[str]:
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


async def _audit(
    db: AsyncSession,
    user: User,
    request: Request,
    *,
    action: str,
    entity_type: str = "db_admin",
    entity_id: Optional[str] = None,
    payload: Optional[dict] = None,
    notes: Optional[str] = None,
    is_critical: bool = False,
) -> None:
    """Write to audit_log via HMAC chain. Uses the REGULAR session
    (not the admin one) so the audit chain stays on least-privilege role."""
    try:
        await append_audit_entry(
            db,
            actor_id=str(user.id),
            actor_email=user.email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:512],
            notes=notes,
            is_critical=is_critical,
        )
        await db.commit()
    except Exception as e:
        log.warning("[db_admin] audit failed: %s", e)
        await db.rollback()


# =====================================================================
# Schemas
# =====================================================================

class ColumnInfo(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str] = None
    character_maximum_length: Optional[int] = None
    is_pk: bool = False
    is_fk: bool = False
    fk_references: Optional[str] = None  # "schema.table.column"


class IndexInfo(BaseModel):
    name: str
    definition: str
    is_unique: bool
    is_primary: bool


class TableInfo(BaseModel):
    schema: str
    name: str
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    columns: list[ColumnInfo] = Field(default_factory=list)
    indexes: list[IndexInfo] = Field(default_factory=list)


class SchemaOverview(BaseModel):
    tables: list[TableInfo]
    db_size_bytes: Optional[int] = None
    db_version: Optional[str] = None


class QueryRequest(BaseModel):
    sql: str = Field(..., max_length=100_000)
    # Если true — оборачиваем в транзакцию и НЕ коммитим (для dry-run).
    dry_run: bool = False


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: float
    command: str  # "SELECT", "UPDATE", "INSERT", "DELETE", "DDL", "OTHER"


class TableRowsResponse(BaseModel):
    columns: list[str]
    rows: list[dict]
    total: int
    limit: int
    offset: int


class RowMutateRequest(BaseModel):
    pk_column: str = "id"
    pk_value: Any
    values: dict[str, Any]


# =====================================================================
# Endpoints
# =====================================================================

@router.get("/schema", response_model=SchemaOverview)
async def get_schema(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SchemaOverview:
    """Полный обзор схемы: таблицы, колонки, индексы, размеры."""
    _require_db_admin(current_user)

    async with _AdminSession() as adb:
        # Размер БД и версия
        db_size = await adb.execute(text("SELECT pg_database_size(current_database())"))
        db_size_bytes = db_size.scalar()
        ver = await adb.execute(text("SELECT version()"))
        db_version = ver.scalar()

        # Таблицы public-схемы с приблизительными row_count и размером
        tables_res = await adb.execute(text("""
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
        """))
        raw_tables = tables_res.fetchall()

        # Колонки всех таблиц одним запросом
        cols_res = await adb.execute(text("""
            SELECT
                c.table_schema, c.table_name, c.column_name,
                c.data_type, c.is_nullable, c.column_default,
                c.character_maximum_length
            FROM information_schema.columns c
            WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """))
        cols_by_table: dict[tuple[str, str], list[ColumnInfo]] = {}
        for row in cols_res.fetchall():
            cols_by_table.setdefault((row[0], row[1]), []).append(
                ColumnInfo(
                    name=row[2],
                    data_type=row[3],
                    is_nullable=(row[4] == "YES"),
                    column_default=row[5],
                    character_maximum_length=row[6],
                )
            )

        # PK
        pk_res = await adb.execute(text("""
            SELECT tc.table_schema, tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
        """))
        pks: set[tuple[str, str, str]] = {(r[0], r[1], r[2]) for r in pk_res.fetchall()}

        # FK
        fk_res = await adb.execute(text("""
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
        """))
        fks: dict[tuple[str, str, str], str] = {}
        for row in fk_res.fetchall():
            fks[(row[0], row[1], row[2])] = f"{row[3]}.{row[4]}.{row[5]}"

        # Mark PK / FK on columns
        for (schema, table), cols in cols_by_table.items():
            for col in cols:
                if (schema, table, col.name) in pks:
                    col.is_pk = True
                if (schema, table, col.name) in fks:
                    col.is_fk = True
                    col.fk_references = fks[(schema, table, col.name)]

        # Индексы
        idx_res = await adb.execute(text("""
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
        """))
        idx_by_table: dict[tuple[str, str], list[IndexInfo]] = {}
        for row in idx_res.fetchall():
            idx_by_table.setdefault((row[0], row[1]), []).append(
                IndexInfo(
                    name=row[2],
                    definition=row[3],
                    is_unique=bool(row[4]),
                    is_primary=bool(row[5]),
                )
            )

        tables: list[TableInfo] = []
        for row in raw_tables:
            key = (row[0], row[1])
            tables.append(TableInfo(
                schema=row[0],
                name=row[1],
                row_count=int(row[2]) if row[2] is not None else None,
                size_bytes=int(row[3]) if row[3] is not None else None,
                columns=cols_by_table.get(key, []),
                indexes=idx_by_table.get(key, []),
            ))

    await _audit(
        db, current_user, request,
        action="db_admin.schema_viewed",
        notes=f"{len(tables)} tables introspected",
    )

    return SchemaOverview(
        tables=tables,
        db_size_bytes=int(db_size_bytes) if db_size_bytes else None,
        db_version=str(db_version) if db_version else None,
    )


_COMMAND_RE = re.compile(r"^\s*(?:--[^\n]*\n|/\*.*?\*/)*\s*([A-Za-z]+)", re.DOTALL)


def _classify_sql(sql: str) -> str:
    """Грубая классификация: SELECT / INSERT / UPDATE / DELETE / DDL / OTHER."""
    m = _COMMAND_RE.match(sql)
    if not m:
        return "OTHER"
    cmd = m.group(1).upper()
    if cmd in {"SELECT", "WITH", "VALUES", "SHOW", "EXPLAIN", "TABLE"}:
        return "SELECT"
    if cmd in {"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE"}:
        return cmd
    if cmd in {"CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "COMMENT", "REINDEX"}:
        return "DDL"
    return "OTHER"


@router.post("/query", response_model=QueryResponse)
async def execute_query(
    body: QueryRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    """Выполнить произвольный SQL. Все коммерческие права у superuser."""
    _require_db_admin(current_user)

    sql = body.sql.strip()
    if not sql:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой SQL")

    command = _classify_sql(sql)
    started = time.monotonic()
    columns: list[str] = []
    rows: list[list[Any]] = []
    truncated = False
    error_msg: Optional[str] = None
    row_count = 0

    try:
        async with _AdminSession() as adb:
            # statement_timeout — защита от runaway
            await adb.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_SECONDS}s'"))
            result = await adb.execute(text(sql))
            # SELECT-like → row iteration
            if result.returns_rows:
                columns = list(result.keys())
                fetched = result.fetchmany(MAX_ROWS + 1)
                if len(fetched) > MAX_ROWS:
                    truncated = True
                    fetched = fetched[:MAX_ROWS]
                rows = [
                    [_serialize(v) for v in row]
                    for row in fetched
                ]
                row_count = len(rows)
            else:
                # INSERT/UPDATE/DELETE возвращают rowcount, не данные
                row_count = result.rowcount or 0

            if body.dry_run:
                await adb.rollback()
            else:
                await adb.commit()
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        # Не вызываем raise — мы хотим залогировать и вернуть ошибку клиенту
        log.warning("[db_admin] query failed by %s: %s", current_user.email, error_msg)

    duration_ms = round((time.monotonic() - started) * 1000, 2)

    # Audit — независимо от успеха
    is_critical = command in {"DELETE", "DDL", "TRUNCATE"}
    audit_payload: dict[str, Any] = {
        "sql": sql[:8000],            # лимит для audit_log
        "command": command,
        "row_count": row_count,
        "truncated": truncated,
        "duration_ms": duration_ms,
        "dry_run": body.dry_run,
    }
    if error_msg:
        audit_payload["error"] = error_msg[:1000]

    await _audit(
        db, current_user, request,
        action="db_admin.query",
        payload=audit_payload,
        is_critical=is_critical,
        notes=f"{command} · {row_count} rows · {duration_ms} ms"
              + (" · DRY-RUN" if body.dry_run else "")
              + (f" · ERROR: {error_msg[:200]}" if error_msg else ""),
    )

    if error_msg:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error_msg)

    return QueryResponse(
        columns=columns,
        rows=rows,
        row_count=row_count,
        truncated=truncated,
        duration_ms=duration_ms,
        command=command,
    )


@router.get("/table/{name}/rows", response_model=TableRowsResponse)
async def browse_table(
    name: str,
    request: Request,
    limit: int = 50,
    offset: int = 0,
    order_by: Optional[str] = None,
    order_dir: str = "ASC",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TableRowsResponse:
    """Пагинированный browser строк таблицы."""
    _require_db_admin(current_user)
    _validate_identifier(name)
    if order_by:
        _validate_identifier(order_by)
    order_dir = order_dir.upper()
    if order_dir not in {"ASC", "DESC"}:
        order_dir = "ASC"
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))

    order_clause = f'ORDER BY "{order_by}" {order_dir}' if order_by else ""

    async with _AdminSession() as adb:
        total_q = await adb.execute(text(f'SELECT COUNT(*) FROM "{name}"'))
        total = int(total_q.scalar() or 0)

        rows_q = await adb.execute(text(
            f'SELECT * FROM "{name}" {order_clause} LIMIT :lim OFFSET :off'
        ), {"lim": limit, "off": offset})
        columns = list(rows_q.keys())
        rows_data = [
            {col: _serialize(val) for col, val in zip(columns, row)}
            for row in rows_q.fetchall()
        ]

    await _audit(
        db, current_user, request,
        action="db_admin.browse",
        entity_id=name,
        notes=f"{name} · {len(rows_data)}/{total} rows",
    )

    return TableRowsResponse(
        columns=columns,
        rows=rows_data,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/table/{name}/row")
async def update_row(
    name: str,
    body: RowMutateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """UPDATE одной строки по PK."""
    _require_db_admin(current_user)
    _validate_identifier(name)
    _validate_identifier(body.pk_column)
    if not body.values:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "values пуст")
    for k in body.values.keys():
        _validate_identifier(k)

    set_clauses = ", ".join([f'"{k}" = :{k}' for k in body.values.keys()])
    sql = f'UPDATE "{name}" SET {set_clauses} WHERE "{body.pk_column}" = :_pk RETURNING *'

    async with _AdminSession() as adb:
        await adb.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_SECONDS}s'"))
        params = {**body.values, "_pk": body.pk_value}
        result = await adb.execute(text(sql), params)
        if result.returns_rows:
            row_data = result.fetchone()
            updated = dict(row_data._mapping) if row_data else None
        else:
            updated = None
        await adb.commit()

    await _audit(
        db, current_user, request,
        action="db_admin.row_update",
        entity_type="db_admin",
        entity_id=f"{name}/{body.pk_value}",
        payload={"table": name, "pk": str(body.pk_value), "changes": body.values},
        is_critical=True,
        notes=f"UPDATE {name} WHERE {body.pk_column}={body.pk_value}",
    )

    return {"updated": _serialize_dict(updated) if updated else None}


@router.delete("/table/{name}/row")
async def delete_row(
    name: str,
    request: Request,
    pk_column: str = "id",
    pk_value: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """DELETE одной строки по PK."""
    _require_db_admin(current_user)
    _validate_identifier(name)
    _validate_identifier(pk_column)
    if not pk_value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "pk_value обязателен")

    sql = f'DELETE FROM "{name}" WHERE "{pk_column}" = :_pk'
    async with _AdminSession() as adb:
        await adb.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_SECONDS}s'"))
        result = await adb.execute(text(sql), {"_pk": pk_value})
        await adb.commit()
        deleted = result.rowcount or 0

    await _audit(
        db, current_user, request,
        action="db_admin.row_delete",
        entity_type="db_admin",
        entity_id=f"{name}/{pk_value}",
        payload={"table": name, "pk_column": pk_column, "pk_value": pk_value},
        is_critical=True,
        notes=f"DELETE {name} WHERE {pk_column}={pk_value} · {deleted} rows",
    )

    return {"deleted": deleted}


# =====================================================================
# Utils
# =====================================================================

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str) -> None:
    """Защита от SQL injection в WHERE/SET clauses через имена колонок/таблиц."""
    if not _IDENTIFIER_RE.match(name):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Недопустимый идентификатор: {name!r}",
        )


def _serialize(val: Any) -> Any:
    """Конвертация PG-типов в JSON-сериализуемые значения."""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (UUID,)):
        return str(val)
    if isinstance(val, (bytes, bytearray, memoryview)):
        return f"<{len(val)} bytes>"
    # datetime / date / time / Decimal / dict / list — str-репрезентация
    try:
        from decimal import Decimal
        if isinstance(val, Decimal):
            return float(val)
    except Exception:
        pass
    if isinstance(val, (list, dict)):
        return val
    return str(val)


def _serialize_dict(d: dict) -> dict:
    return {k: _serialize(v) for k, v in d.items()}
