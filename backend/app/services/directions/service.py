"""Directions lookup + admin CRUD use-cases (Pack 149).

Built-in directions (11 canonical) are seeded by migration; cannot be deleted
but can be renamed via PATCH.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import _has_permission, has_effective_permission
from app.models.company import Direction
from app.models.user import User
from app.repositories.directions_repository import DirectionsRepository

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
        "color": d.color or _DIR_COLORS.get(d.code, "#7F77DD"),
        "sort_order": d.sort_order,
        "is_custom": d.is_custom,
        "is_canonical": d.code in _CANONICAL_CODES,
    }


def _require_admin(user: User) -> None:
    if user.is_owner:
        return
    if (_has_permission(user, "companies.edit")
        or _has_permission(user, "tasks.manage")):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: companies.edit",
    )


def _slugify_code(name: str) -> str:
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


@dataclass
class DirectionsService:
    async def list_directions(self, db: AsyncSession, user: User) -> dict:
        if not await has_effective_permission(db, user, "tasks.view"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "tasks.view required"
            )
        rows = await DirectionsRepository(db).list_all()
        return {"directions": [_serialize(d) for d in rows]}

    async def create_direction(
        self, payload: DirectionIn, db: AsyncSession, user: User,
    ) -> dict:
        _require_admin(user)
        code = (payload.code or _slugify_code(payload.name_ru)).lower()
        if not _CODE_RE.match(code):
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "code must match ^[a-z][a-z0-9_]{1,31}$ — explicit or derived from name",
            )
        repo = DirectionsRepository(db)
        if await repo.get_by_code(code):
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
            color=payload.color,   # ПЕРСИСТ в БД
        )
        repo.add(d)
        await db.commit()
        await repo.refresh(d)
        return _serialize(d)

    async def update_direction(
        self,
        direction_id: uuid.UUID,
        payload: DirectionPatch,
        db: AsyncSession,
        user: User,
    ) -> dict:
        _require_admin(user)
        repo = DirectionsRepository(db)
        d = await repo.get_by_id(direction_id)
        if not d:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, "Direction not found"
            )
        changes = payload.model_dump(exclude_unset=True)
        for k, v in changes.items():
            setattr(d, k, v)   # включая color → ПЕРСИСТ в БД (переживает рестарт)
        await db.commit()
        await repo.refresh(d)
        return _serialize(d)

    async def direction_usage(
        self, direction_id: uuid.UUID, db: AsyncSession, user: User,
    ) -> dict:
        _require_admin(user)
        repo = DirectionsRepository(db)
        d = await repo.get_by_id(direction_id)
        if not d:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, "Direction not found"
            )
        return {
            "tasks": await repo.count_tasks_with_code(d.code),
            "projects": await repo.count_projects_with_code(d.code),
            "code": d.code,
            "label": d.name_ru,
        }

    async def delete_direction(
        self,
        direction_id: uuid.UUID,
        reassign_to: Optional[str],
        db: AsyncSession,
        user: User,
    ) -> None:
        _require_admin(user)
        repo = DirectionsRepository(db)
        d = await repo.get_by_id(direction_id)
        if not d:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, "Direction not found"
            )
        target_code: Optional[str] = None
        if reassign_to:
            target = await repo.get_by_code(reassign_to.lower())
            if not target:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"reassign_to: direction code '{reassign_to}' not found",
                )
            if target.id == d.id:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    "reassign_to cannot equal the direction being deleted",
                )
            target_code = target.code
        if target_code:
            await repo.reassign_tasks(from_code=d.code, to_code=target_code)
            await repo.reassign_projects(from_code=d.code, to_code=target_code)
        else:
            await repo.strip_tasks(d.code)
            await repo.strip_projects(d.code)
        await repo.delete(d)
        await db.commit()
