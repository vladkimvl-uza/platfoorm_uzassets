"""Pack 7.69 — Финансовая модель — Firebase RTDB-style storage endpoint.

Backs the monolith-lifted JS code which expects Firebase RTDB-style paths like:
    GET  /finModel.json                                      → full _db.finModel
    PUT  /finModel.json                                      → replaces full doc
    PUT  /finModel/{co}/{scenario}/assumptions.json          → partial write

The monolith code does:
    var url = FB_URL().replace(/\\.json.*$/, '') + '/finModel.json';
    fetch(url, {method:'PUT', body: JSON.stringify(_db.finModel)});

We make FB_URL() return `/api/finmodel-storage/root.json` so after the regex strip
+ append, requests land at `/api/finmodel-storage/root/finModel.json` etc.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User


router = APIRouter(prefix="/finmodel-storage", tags=["finmodel-storage"])


# ─── Helpers ─────────────────────────────────────────────────────────────

async def _load_doc(db: AsyncSession) -> dict:
    """Read the single-row finmodel_storage.data JSONB.

    Returns empty dict gracefully if table doesn't exist yet (migration 0027 not applied).
    """
    try:
        q = await db.execute(text("SELECT data FROM finmodel_storage WHERE id = 1"))
        row = q.first()
    except Exception as e:
        # Table likely doesn't exist (migration not applied) — return empty so frontend stays functional
        msg = str(e).lower()
        if "finmodel_storage" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            return {}
        # Other DB errors — re-raise so user sees them
        raise
    if not row:
        # Insert empty row if it doesn't exist
        try:
            await db.execute(text("INSERT INTO finmodel_storage (id, data) VALUES (1, '{}'::jsonb) ON CONFLICT DO NOTHING"))
            await db.commit()
        except Exception:
            pass
        return {}
    return row[0] or {}


async def _save_doc(db: AsyncSession, data: dict, user_email: str) -> None:
    """Replace the entire finmodel_storage.data JSONB. Raises HTTPException if migration not applied."""
    try:
        await db.execute(
            text("UPDATE finmodel_storage SET data = CAST(:data AS jsonb), updated_at = NOW(), updated_by = :user WHERE id = 1"),
            {"data": _json_str(data), "user": user_email},
        )
        # If id=1 row doesn't exist, INSERT it
        await db.execute(
            text("""INSERT INTO finmodel_storage (id, data, updated_by) VALUES (1, CAST(:data AS jsonb), :user)
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW(), updated_by = EXCLUDED.updated_by"""),
            {"data": _json_str(data), "user": user_email},
        )
        await db.commit()
    except Exception as e:
        msg = str(e).lower()
        if "finmodel_storage" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            raise HTTPException(
                http_status.HTTP_503_SERVICE_UNAVAILABLE,
                "Таблица finmodel_storage не создана. Выполни: docker exec uza-backend alembic upgrade head",
            )
        raise


def _json_str(d: Any) -> str:
    """Compact JSON for PostgreSQL JSONB insert."""
    import json
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def _nav(doc: dict, path_parts: list[str]) -> Any:
    """Navigate to nested key. Returns None if any segment missing."""
    cur = doc
    for part in path_parts:
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_nested(doc: dict, path_parts: list[str], value: Any) -> dict:
    """Set nested key, creating intermediate dicts as needed. Mutates `doc`."""
    if not path_parts:
        # Empty path = replace whole document
        return value if isinstance(value, dict) else {}
    cur = doc
    for part in path_parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[path_parts[-1]] = value
    return doc


def _path_from_url_rest(rest: str) -> list[str]:
    """Convert URL tail like 'finModel/UAP/base/assumptions.json' → ['finModel', 'UAP', 'base', 'assumptions'].

    Strips leading slashes, splits on /, removes '.json' suffix from last segment.
    URL-decodes each segment (for company codes with special chars).
    """
    from urllib.parse import unquote
    rest = rest.lstrip("/")
    if rest.endswith(".json"):
        rest = rest[: -len(".json")]
    if not rest:
        return []
    return [unquote(p) for p in rest.split("/") if p]


# ─── Endpoints ───────────────────────────────────────────────────────────

@router.get("/root/{rest:path}")
async def get_path(
    rest: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """GET request — return JSON at the given path. Returns null if path doesn't exist."""
    doc = await _load_doc(db)
    parts = _path_from_url_rest(rest)
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
    """PUT — replace JSON at the given path with request body. Mirrors Firebase RTDB semantics."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Invalid JSON body")
    doc = await _load_doc(db)
    parts = _path_from_url_rest(rest)
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
    """PATCH — merge JSON object at the given path. Mirrors Firebase RTDB shallow-merge semantics."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "PATCH body must be a JSON object")
    doc = await _load_doc(db)
    parts = _path_from_url_rest(rest)
    target = _nav(doc, parts)
    if target is None or not isinstance(target, dict):
        # Create at this path
        _set_nested(doc, parts, body)
    else:
        target.update(body)
    await _save_doc(db, doc, user.email)
    return body


@router.delete("/root/{rest:path}")
async def delete_path(
    rest: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """DELETE — remove the key at the given path. Firebase RTDB delete = set to null."""
    doc = await _load_doc(db)
    parts = _path_from_url_rest(rest)
    if not parts:
        await _save_doc(db, {}, user.email)
        return {"deleted": True, "path": ""}
    # Navigate to parent, delete leaf
    parent = doc
    for part in parts[:-1]:
        if not isinstance(parent, dict) or part not in parent:
            return {"deleted": False, "path": "/".join(parts)}
        parent = parent[part]
    if isinstance(parent, dict):
        parent.pop(parts[-1], None)
    await _save_doc(db, doc, user.email)
    return {"deleted": True, "path": "/".join(parts)}
