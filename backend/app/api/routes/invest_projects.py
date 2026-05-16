"""Pack 8.0 — Invest Projects — Firebase RTDB-style storage endpoint.

Mirrors the finmodel_storage pattern: single-row JSONB doc, navigation by URL path.

Routes:
    GET   /invest-projects-storage/root/{path}.json   → returns JSON at nested path
    PUT   /invest-projects-storage/root/{path}.json   → replaces JSON at path
    PATCH /invest-projects-storage/root/{path}.json   → shallow-merges JSON at path

Scope (C3b):
    Owner / `companies.view_all` — без ограничений.
    Остальные юзеры могут читать/писать только в namespace
    `companies/<company_code>/...`, где `<company_code>` входит
    в их `allowed_companies`. Root-листинг и любые другие ветки
    им недоступны (403). Это договорённость о форме хранения:
    фронт пишет данные конкретной компании под её код.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.database import get_db
from app.models.company import Company
from app.models.user import User


router = APIRouter(prefix="/invest-projects-storage", tags=["invest-projects-storage"])


async def _load_doc(db: AsyncSession) -> dict:
    try:
        q = await db.execute(text("SELECT data FROM invest_projects_storage WHERE id = 1"))
        row = q.first()
    except Exception as e:
        msg = str(e).lower()
        if "invest_projects_storage" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            return {}
        raise
    if not row:
        try:
            await db.execute(text("INSERT INTO invest_projects_storage (id, data) VALUES (1, '{}'::jsonb) ON CONFLICT DO NOTHING"))
            await db.commit()
        except Exception:
            pass
        return {}
    return row[0] or {}


async def _save_doc(db: AsyncSession, data: dict, user_email: str) -> None:
    try:
        await db.execute(
            text("""INSERT INTO invest_projects_storage (id, data, updated_by) VALUES (1, CAST(:data AS jsonb), :user)
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW(), updated_by = EXCLUDED.updated_by"""),
            {"data": _json_str(data), "user": user_email},
        )
        await db.commit()
    except Exception as e:
        msg = str(e).lower()
        if "invest_projects_storage" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            raise HTTPException(
                http_status.HTTP_503_SERVICE_UNAVAILABLE,
                "Таблица invest_projects_storage не создана. Выполни: docker exec uza-backend alembic upgrade head",
            )
        raise


def _json_str(d: Any) -> str:
    import json
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def _path_from_rest(rest: str) -> list[str]:
    from urllib.parse import unquote
    rest = rest.lstrip("/")
    if rest.endswith(".json"):
        rest = rest[: -len(".json")]
    if not rest:
        return []
    return [unquote(p) for p in rest.split("/") if p]


def _nav(doc: dict, parts: list[str]) -> Any:
    cur = doc
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _set_nested(doc: dict, parts: list[str], value: Any) -> dict:
    if not parts:
        return value if isinstance(value, dict) else {}
    cur = doc
    for p in parts[:-1]:
        if not isinstance(cur.get(p), dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
    return doc


async def _enforce_path_scope(
    db: AsyncSession,
    user: User,
    parts: list[str],
) -> None:
    """Allow access only to `companies/<allowed_code>/...` for scoped users.

    Admin / owner / companies.view_all — bypass. Любые другие пути для scoped
    юзеров → 403, чтобы не светить чужие компании или общие ветки.
    """
    if has_unrestricted_view(user):
        return

    if len(parts) < 2 or parts[0] != "companies":
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Доступ только к ветке companies/<your_company_code>/...",
        )

    scope_ids = await allowed_company_ids(db, user)
    if not scope_ids:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступных компаний")

    code_q = await db.execute(
        select(Company.code).where(Company.id.in_(scope_ids))
    )
    allowed_codes = {(c or "").lower() for (c,) in code_q.all() if c}

    requested = (parts[1] or "").lower()
    if requested not in allowed_codes:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            f"Нет доступа к данным компании {parts[1]}",
        )


@router.get("/root/{rest:path}")
async def get_path(
    rest: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    parts = _path_from_rest(rest)
    await _enforce_path_scope(db, user, parts)
    doc = await _load_doc(db)
    if not parts:
        return doc
    return _nav(doc, parts)


@router.put("/root/{rest:path}")
async def put_path(
    rest: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    parts = _path_from_rest(rest)
    await _enforce_path_scope(db, user, parts)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Invalid JSON body")
    doc = await _load_doc(db)
    updated = _set_nested(doc, parts, body)
    await _save_doc(db, updated, user.email)
    return body


@router.patch("/root/{rest:path}")
async def patch_path(
    rest: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    parts = _path_from_rest(rest)
    await _enforce_path_scope(db, user, parts)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "PATCH body must be a JSON object")
    doc = await _load_doc(db)
    target = _nav(doc, parts)
    if target is None or not isinstance(target, dict):
        _set_nested(doc, parts, body)
    else:
        target.update(body)
    await _save_doc(db, doc, user.email)
    return body
