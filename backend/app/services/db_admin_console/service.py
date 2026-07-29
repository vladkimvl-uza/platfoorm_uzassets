"""DB-admin console use-cases (Pack 149).

Folder name `db_admin_console/` to keep symbol path clean and avoid any
collision with the storage_admin pattern.

Owner / is_admin only. Every operation writes to audit_log via the
HMAC chain on the REGULAR (least-privilege) session — even when DDL runs
on the superuser connection.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, Request
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.models.user import User
from app.repositories.db_admin_repository import MAX_ROWS, DbAdminRepository

log = logging.getLogger(__name__)

# MAX_ROWS определён в repo (data-слой) и реэкспортится здесь для обратной
# совместимости публичного API пакета (db_admin_console.__init__).
STATEMENT_TIMEOUT_SECONDS = 30


# ─── Schemas ──────────────────────────────────────────────────────

class ColumnInfo(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str] = None
    character_maximum_length: Optional[int] = None
    is_pk: bool = False
    is_fk: bool = False
    fk_references: Optional[str] = None


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
    # Разрешены ли write/DDL (DB_ADMIN_ALLOW_WRITES). Фронт по этому флагу
    # показывает read-only баннер и дизейблит выполнение write-запросов,
    # вместо молчаливого 403 после «страшного» подтверждения.
    allow_writes: bool = False


class QueryRequest(BaseModel):
    sql: str = Field(..., max_length=100_000)
    dry_run: bool = False  # wrap in tx, no commit — for sanity-check


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: float
    command: str  # SELECT / INSERT / UPDATE / DELETE / DDL / OTHER


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


# ─── Helpers ──────────────────────────────────────────────────────

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMMAND_RE = re.compile(
    r"^\s*(?:--[^\n]*\n|/\*.*?\*/)*\s*([A-Za-z]+)", re.DOTALL,
)


def _validate_identifier(name: str) -> None:
    if not _IDENTIFIER_RE.match(name):
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"Недопустимый идентификатор: {name!r}",
        )


def _classify_sql(sql: str) -> str:
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


def _serialize(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, str | int | float | bool):
        return val
    if isinstance(val, UUID):
        return str(val)
    if isinstance(val, bytes | bytearray | memoryview):
        return f"<{len(val)} bytes>"
    try:
        from decimal import Decimal
        if isinstance(val, Decimal):
            return float(val)
    except Exception:
        pass
    if isinstance(val, list | dict):
        return val
    return str(val)


def _serialize_dict(d: dict) -> dict:
    return {k: _serialize(v) for k, v in d.items()}


def _require_db_admin(user: User) -> None:
    """Владелец или платформенный администратор (роль admin).

    Раньше проверялось поле `user.is_admin`, КОТОРОГО НЕ СУЩЕСТВУЕТ ни в модели
    User, ни в таблице users — getattr всегда возвращал False, и консоль базы
    данных была доступна ИСКЛЮЧИТЕЛЬНО владельцу. Отказ был тихим: ни ошибки,
    ни записи в лог, просто 403 у администратора. Сверяемся с единой точкой
    is_super_admin (owner ИЛИ роль admin), как весь остальной бэкенд.
    """
    from app.core.security import is_super_admin
    if is_super_admin(user):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Доступ к DB-консоли только для owner/admin",
    )


def _client_ip(request: Request) -> Optional[str]:
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


@dataclass
class DbAdminService:
    async def _audit(
        self,
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

    async def get_schema(
        self, db: AsyncSession, user: User, request: Request,
    ) -> SchemaOverview:
        _require_db_admin(user)
        repo = DbAdminRepository()

        meta = await repo.db_meta()
        raw_tables = await repo.list_tables()
        raw_cols = await repo.list_columns()
        raw_pks = await repo.list_pks()
        raw_fks = await repo.list_fks()
        raw_idx = await repo.list_indexes()

        cols_by_table: dict[tuple[str, str], list[ColumnInfo]] = {}
        for row in raw_cols:
            cols_by_table.setdefault((row[0], row[1]), []).append(
                ColumnInfo(
                    name=row[2],
                    data_type=row[3],
                    is_nullable=(row[4] == "YES"),
                    column_default=row[5],
                    character_maximum_length=row[6],
                )
            )

        pks: set[tuple[str, str, str]] = {(r[0], r[1], r[2]) for r in raw_pks}
        fks: dict[tuple[str, str, str], str] = {
            (r[0], r[1], r[2]): f"{r[3]}.{r[4]}.{r[5]}" for r in raw_fks
        }

        for (schema, table), cols in cols_by_table.items():
            for col in cols:
                if (schema, table, col.name) in pks:
                    col.is_pk = True
                if (schema, table, col.name) in fks:
                    col.is_fk = True
                    col.fk_references = fks[(schema, table, col.name)]

        idx_by_table: dict[tuple[str, str], list[IndexInfo]] = {}
        for row in raw_idx:
            idx_by_table.setdefault((row[0], row[1]), []).append(
                IndexInfo(
                    name=row[2], definition=row[3],
                    is_unique=bool(row[4]), is_primary=bool(row[5]),
                )
            )

        tables: list[TableInfo] = []
        for row in raw_tables:
            key = (row[0], row[1])
            tables.append(TableInfo(
                schema=row[0], name=row[1],
                row_count=int(row[2]) if row[2] is not None else None,
                size_bytes=int(row[3]) if row[3] is not None else None,
                columns=cols_by_table.get(key, []),
                indexes=idx_by_table.get(key, []),
            ))

        await self._audit(
            db, user, request,
            action="db_admin.schema_viewed",
            notes=f"{len(tables)} tables introspected",
        )
        from app.config import settings as _s
        return SchemaOverview(
            tables=tables,
            db_size_bytes=meta["size_bytes"],
            db_version=meta["version"],
            allow_writes=bool(getattr(_s, "DB_ADMIN_ALLOW_WRITES", False)),
        )

    async def execute_query(
        self,
        body: QueryRequest,
        db: AsyncSession,
        user: User,
        request: Request,
    ) -> QueryResponse:
        _require_db_admin(user)
        sql = body.sql.strip()
        if not sql:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Пустой SQL")

        command = _classify_sql(sql)

        # 2026-05-26 hardening: writes blocked by default to prevent
        # owner-compromise → full-DB-corruption scenario. Set
        # DB_ADMIN_ALLOW_WRITES=true in env to enable (intentional, audited).
        from app.config import settings as _s
        is_write = command in {"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "DDL"}
        if is_write and not getattr(_s, "DB_ADMIN_ALLOW_WRITES", False) and not body.dry_run:
            # Audit the rejected attempt (forensic trail)
            await self._audit(
                db, user, request,
                action="db_admin.query_rejected",
                payload={"sql": sql[:8000], "command": command},
                is_critical=True,
                notes=f"WRITE rejected · {command} · DB_ADMIN_ALLOW_WRITES=false",
            )
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                f"Write operations ({command}) запрещены через /admin/db/query. "
                f"Используйте dry_run=true для проверки или alembic migration "
                f"для постоянных изменений. Env var DB_ADMIN_ALLOW_WRITES=true "
                f"включает writes (требует deploy/restart).",
            )

        started = time.monotonic()
        columns: list[str] = []
        rows: list[list[Any]] = []
        truncated = False
        error_msg: Optional[str] = None
        row_count = 0

        try:
            result = await DbAdminRepository().execute_raw(
                sql,
                dry_run=body.dry_run,
                statement_timeout_seconds=STATEMENT_TIMEOUT_SECONDS,
            )
            columns = result["columns"]
            rows = [
                [_serialize(v) for v in row] for row in result["rows"]
            ]
            row_count = result["row_count"]
            truncated = result["truncated"]
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            log.warning(
                "[db_admin] query failed by %s: %s", user.email, error_msg,
            )

        duration_ms = round((time.monotonic() - started) * 1000, 2)

        is_critical = command in {"DELETE", "DDL", "TRUNCATE"}
        audit_payload: dict[str, Any] = {
            "sql": sql[:8000],
            "command": command,
            "row_count": row_count,
            "truncated": truncated,
            "duration_ms": duration_ms,
            "dry_run": body.dry_run,
        }
        if error_msg:
            audit_payload["error"] = error_msg[:1000]

        await self._audit(
            db, user, request,
            action="db_admin.query",
            payload=audit_payload,
            is_critical=is_critical,
            notes=(
                f"{command} · {row_count} rows · {duration_ms} ms"
                + (" · DRY-RUN" if body.dry_run else "")
                + (f" · ERROR: {error_msg[:200]}" if error_msg else "")
            ),
        )

        if error_msg:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, error_msg)

        return QueryResponse(
            columns=columns,
            rows=rows,
            row_count=row_count,
            truncated=truncated,
            duration_ms=duration_ms,
            command=command,
        )

    async def browse_table(
        self,
        name: str,
        db: AsyncSession,
        user: User,
        request: Request,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: Optional[str] = None,
        order_dir: str = "ASC",
    ) -> TableRowsResponse:
        _require_db_admin(user)
        _validate_identifier(name)
        if order_by:
            _validate_identifier(order_by)
        order_dir = order_dir.upper()
        if order_dir not in {"ASC", "DESC"}:
            order_dir = "ASC"
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))

        repo = DbAdminRepository()
        total = await repo.count_table(name)
        cols, rows_raw = await repo.browse_table(
            name, limit=limit, offset=offset,
            order_by=order_by, order_dir=order_dir,
        )
        rows_data = [
            {col: _serialize(val) for col, val in zip(cols, row, strict=False)}
            for row in rows_raw
        ]

        await self._audit(
            db, user, request,
            action="db_admin.browse",
            entity_id=name,
            notes=f"{name} · {len(rows_data)}/{total} rows",
        )
        return TableRowsResponse(
            columns=cols, rows=rows_data,
            total=total, limit=limit, offset=offset,
        )

    async def update_row(
        self,
        name: str,
        body: RowMutateRequest,
        db: AsyncSession,
        user: User,
        request: Request,
    ) -> dict[str, Any]:
        _require_db_admin(user)
        _validate_identifier(name)
        _validate_identifier(body.pk_column)
        if not body.values:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "values пуст")
        for k in body.values.keys():
            _validate_identifier(k)

        # 2026-05-26: writes gated behind DB_ADMIN_ALLOW_WRITES (see execute_query).
        from app.config import settings as _s
        if not getattr(_s, "DB_ADMIN_ALLOW_WRITES", False):
            await self._audit(
                db, user, request,
                action="db_admin.row_update_rejected",
                entity_id=f"{name}/{body.pk_value}",
                payload={"table": name, "pk": str(body.pk_value)},
                is_critical=True,
                notes="UPDATE rejected · DB_ADMIN_ALLOW_WRITES=false",
            )
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "UPDATE row через /admin/db запрещён. Включите DB_ADMIN_ALLOW_WRITES=true.",
            )

        updated = await DbAdminRepository().update_row(
            table=name,
            pk_column=body.pk_column,
            pk_value=body.pk_value,
            values=body.values,
            statement_timeout_seconds=STATEMENT_TIMEOUT_SECONDS,
        )

        await self._audit(
            db, user, request,
            action="db_admin.row_update",
            entity_id=f"{name}/{body.pk_value}",
            payload={
                "table": name,
                "pk": str(body.pk_value),
                "changes": body.values,
            },
            is_critical=True,
            notes=f"UPDATE {name} WHERE {body.pk_column}={body.pk_value}",
        )
        return {"updated": _serialize_dict(updated) if updated else None}

    async def delete_row(
        self,
        name: str,
        pk_column: str,
        pk_value: str,
        db: AsyncSession,
        user: User,
        request: Request,
    ) -> dict[str, Any]:
        _require_db_admin(user)
        _validate_identifier(name)
        _validate_identifier(pk_column)
        if not pk_value:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, "pk_value обязателен",
            )

        # 2026-05-26: writes gated.
        from app.config import settings as _s
        if not getattr(_s, "DB_ADMIN_ALLOW_WRITES", False):
            await self._audit(
                db, user, request,
                action="db_admin.row_delete_rejected",
                entity_id=f"{name}/{pk_value}",
                payload={"table": name, "pk_column": pk_column, "pk_value": pk_value},
                is_critical=True,
                notes="DELETE rejected · DB_ADMIN_ALLOW_WRITES=false",
            )
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "DELETE row через /admin/db запрещён. Включите DB_ADMIN_ALLOW_WRITES=true.",
            )

        deleted = await DbAdminRepository().delete_row(
            table=name, pk_column=pk_column, pk_value=pk_value,
            statement_timeout_seconds=STATEMENT_TIMEOUT_SECONDS,
        )
        await self._audit(
            db, user, request,
            action="db_admin.row_delete",
            entity_id=f"{name}/{pk_value}",
            payload={
                "table": name, "pk_column": pk_column, "pk_value": pk_value,
            },
            is_critical=True,
            notes=(
                f"DELETE {name} WHERE {pk_column}={pk_value} · {deleted} rows"
            ),
        )
        return {"deleted": deleted}
