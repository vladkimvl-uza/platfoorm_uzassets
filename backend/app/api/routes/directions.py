"""Directions — lookup + admin CRUD (Pack 149).

GET   /directions          — list all (any user with tasks.view)
POST  /directions          — create custom direction (admin / companies.edit)
PATCH /directions/{id}     — rename / re-sort
DELETE /directions/{id}    — remove custom direction (only is_custom=True)

Built-in directions (11 canonical: strategy, finance, etc.) are seeded
by migration and cannot be deleted — only renamed via PATCH.
"""
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import _has_permission, has_effective_permission
from app.models.company import Direction
from app.models.user import User


router = APIRouter(prefix="/directions", tags=["directions"])


_DIR_COLORS = {
    "strategy": "#1e2787", "finance": "#D97706", "procurement": "#3B6D11",
    "orgdev": "#534AB7", "digital": "#1D9E75", "operations": "#EF4444",
    "governance": "#72243E", "esg": "#1D9E75", "pr": "#D4537E",
    "pmo": "#2563EB", "analytics": "#7C3AED",
}

_CANONICAL_CODES = set(_DIR_COLORS.keys())
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class DirectionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: Optional[str] = Field(None, max_length=32)
    name_ru: str = Field(..., min_length=1, max_length=128)
    name_uz: Optional[str] = Field(None, max_length=128)
    name_en: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    sort_order: int = 999
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class DirectionPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name_ru: Optional[str] = Field(None, min_length=1, max_length=128)
    name_uz: Optional[str] = Field(None, max_length=128)
    name_en: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    sort_order: Optional[int] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


def _serialize(d: Direction) -> dict:
    return {
        "id": str(d.id),
        "code": d.code,
        "label": d.name_ru,
        "name_uz": d.name_uz,
        "name_en": d.name_en,
        "description": d.description,
        "color": _DIR_COLORS.get(d.code, "#7F77DD"),
        "sort_order": d.sort_order,
        "is_custom": d.is_custom,
        "is_canonical": d.code in _CANONICAL_CODES,
    }


def _require_admin(db: AsyncSession, user: User):
    """Admin gate for direction mutations. Owner OR companies.edit OR admin role."""
    if user.is_owner:
        return
    if _has_permission(user, "companies.edit") or _has_permission(user, "tasks.manage"):
        return
    raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: companies.edit")


def _slugify_code(name: str) -> str:
    """Derive a short ASCII code from a Russian/UZ name."""
    # Очень простая транслитерация для русских — для prod лучше polyglot/transliterate
    table = str.maketrans({
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    })
    base = name.lower().translate(table)
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:24]
    if not base:
        base = "dir"
    if not _CODE_RE.match(base):
        base = "dir_" + uuid.uuid4().hex[:8]
    return base


@router.get("")
async def list_directions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    res = await db.execute(
        select(Direction).order_by(Direction.sort_order, Direction.name_ru)
    )
    return {"directions": [_serialize(d) for d in res.scalars().all()]}


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_direction(
    payload: DirectionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user)
    code = (payload.code or _slugify_code(payload.name_ru)).lower()
    if not _CODE_RE.match(code):
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "code must match ^[a-z][a-z0-9_]{1,31}$ — explicit or derived from name",
        )
    # Uniqueness check
    exists = (await db.execute(
        select(Direction).where(Direction.code == code)
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Direction with code '{code}' already exists",
        )
    d = Direction(
        code=code,
        name_ru=payload.name_ru,
        name_uz=payload.name_uz,
        name_en=payload.name_en,
        description=payload.description,
        sort_order=payload.sort_order,
        is_custom=True,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    # Color is admin-supplied for custom dirs (stored separately later if needed —
    # for now uses default #7F77DD via _DIR_COLORS fallback).
    if payload.color:
        _DIR_COLORS[code] = payload.color
    return _serialize(d)


@router.patch("/{direction_id}")
async def update_direction(
    direction_id: uuid.UUID,
    payload: DirectionPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user)
    d = (await db.execute(
        select(Direction).where(Direction.id == direction_id)
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Direction not found")
    changes = payload.model_dump(exclude_unset=True)
    color = changes.pop("color", None)
    for k, v in changes.items():
        setattr(d, k, v)
    if color:
        _DIR_COLORS[d.code] = color
    await db.commit()
    await db.refresh(d)
    return _serialize(d)


@router.get("/{direction_id}/usage")
async def direction_usage(
    direction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return how many tasks/projects still reference this direction code."""
    _require_admin(db, user)
    d = (await db.execute(
        select(Direction).where(Direction.id == direction_id)
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Direction not found")
    from sqlalchemy import text as _text
    t_cnt = (await db.execute(_text(
        "SELECT count(*) FROM tasks WHERE extra->>'direction' = :c"
    ), {"c": d.code})).scalar() or 0
    p_cnt = (await db.execute(_text(
        "SELECT count(*) FROM projects WHERE extra->>'direction' = :c"
    ), {"c": d.code})).scalar() or 0
    return {"tasks": int(t_cnt), "projects": int(p_cnt), "code": d.code, "label": d.name_ru}


@router.delete("/{direction_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_direction(
    direction_id: uuid.UUID,
    reassign_to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a direction (custom OR built-in).

    Query params:
      reassign_to=<code>  — if provided, reassign tasks/projects to that
                            code before delete; otherwise the direction
                            field is set to NULL on those rows.

    Front-end is expected to call /directions/{id}/usage first and show
    the count to the user in a confirmation modal.
    """
    _require_admin(db, user)
    d = (await db.execute(
        select(Direction).where(Direction.id == direction_id)
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Direction not found")

    # Validate reassign target
    target_code: Optional[str] = None
    if reassign_to:
        target = (await db.execute(
            select(Direction).where(Direction.code == reassign_to.lower())
        )).scalar_one_or_none()
        if not target:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                                f"reassign_to: direction code '{reassign_to}' not found")
        if target.id == d.id:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                                "reassign_to cannot equal the direction being deleted")
        target_code = target.code

    # Migrate referencing rows
    from sqlalchemy import text as _text
    if target_code:
        await db.execute(_text(
            "UPDATE tasks SET extra = jsonb_set(extra, '{direction}', to_jsonb(:t::text)) "
            "WHERE extra->>'direction' = :c"
        ), {"t": target_code, "c": d.code})
        await db.execute(_text(
            "UPDATE projects SET extra = jsonb_set(extra, '{direction}', to_jsonb(:t::text)) "
            "WHERE extra->>'direction' = :c"
        ), {"t": target_code, "c": d.code})
    else:
        await db.execute(_text(
            "UPDATE tasks SET extra = extra - 'direction' WHERE extra->>'direction' = :c"
        ), {"c": d.code})
        await db.execute(_text(
            "UPDATE projects SET extra = extra - 'direction' WHERE extra->>'direction' = :c"
        ), {"c": d.code})

    await db.delete(d)
    await db.commit()
