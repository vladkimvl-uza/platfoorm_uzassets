"""Конструктор API + диспетчер пользовательских endpoint'ов.

Админ собирает endpoint (источник + фильтры + колонки) в /admin/api →
сохраняется в custom_api_endpoint. Диспетчер `/api/v1/custom/{slug}` отдаёт
данные read-only: проверяет required_permission (JWT/API-key scope) и
применяет company-scope вызывающего.
"""
from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.i18n import current_locale, tr
from app.core.security import get_current_user, has_effective_permission, require_permission
from app.database import get_db
from app.models.custom_api import CustomApiEndpoint
from app.models.user import User
from app.services import custom_api_registry as reg

router = APIRouter(prefix="/custom-api", tags=["custom-api"])
# Диспетчер живёт под отдельным префиксом — стабильный публичный путь.
dispatch_router = APIRouter(prefix="/api/v1/custom", tags=["custom-api-dispatch"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


# ─── schemas ───────────────────────────────────────────────────────

class EndpointConfig(BaseModel):
    columns: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    standard: Optional[str] = None
    limit: int = 2000


class EndpointIn(BaseModel):
    slug: str = Field(..., min_length=3, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    source: str
    config: EndpointConfig = Field(default_factory=EndpointConfig)
    is_active: bool = True


class EndpointPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    config: Optional[EndpointConfig] = None
    is_active: Optional[bool] = None


class EndpointOut(BaseModel):
    id: str
    slug: str
    title: str
    description: Optional[str]
    source: str
    config: dict
    required_permission: str
    is_active: bool
    url: str


class PreviewIn(BaseModel):
    source: str
    config: EndpointConfig = Field(default_factory=EndpointConfig)


def _out(e: CustomApiEndpoint) -> EndpointOut:
    return EndpointOut(
        id=str(e.id), slug=e.slug, title=e.title, description=e.description,
        source=e.source, config=e.config or {}, required_permission=e.required_permission,
        is_active=e.is_active, url=f"/api/v1/custom/{e.slug}",
    )


# ─── builder UI: источники ─────────────────────────────────────────

@router.get("/sources")
async def list_sources(_u: User = Depends(require_permission("api_catalog.read"))):
    return {"items": reg.catalog()}


# ─── live preview (без сохранения) ─────────────────────────────────

@router.post("/preview")
async def preview(
    body: PreviewIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("api_catalog.read")),
):
    if body.source not in reg.SOURCES:
        raise HTTPException(
            422,
            tr("Неизвестный источник: {source}", current_locale(), source=body.source),
        )
    scope = None if has_unrestricted_view(user) else (await allowed_company_ids(db, user) or [])
    rows = await reg.run_source(
        db, body.source, company_ids=scope, year=body.config.year,
        standard=body.config.standard, columns=body.config.columns,
        limit=min(body.config.limit or 50, 50),
    )
    return {"count": len(rows), "sample": rows[:50], "columns": reg.SOURCES[body.source]["columns"]}


# ─── CRUD endpoints ────────────────────────────────────────────────

@router.get("/endpoints")
async def list_endpoints(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_catalog.read")),
):
    rows = (await db.execute(select(CustomApiEndpoint).order_by(CustomApiEndpoint.created_at.desc()))).scalars().all()
    return {"items": [_out(e) for e in rows]}


@router.post("/endpoints", response_model=EndpointOut, status_code=201)
async def create_endpoint(
    body: EndpointIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("companies.edit")),
):
    slug = body.slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(422, "slug: a-z, 0-9, дефис; 3–64 символа")
    src = reg.SOURCES.get(body.source)
    if src is None:
        raise HTTPException(
            422,
            tr("Неизвестный источник: {source}", current_locale(), source=body.source),
        )
    if (await db.execute(select(CustomApiEndpoint).where(CustomApiEndpoint.slug == slug))).scalar_one_or_none():
        raise HTTPException(
            409,
            tr("Endpoint со slug «{slug}» уже существует", current_locale(), slug=slug),
        )
    e = CustomApiEndpoint(
        slug=slug, title=body.title, description=body.description, source=body.source,
        config=body.config.model_dump(), required_permission=src["permission"],
        is_active=body.is_active, created_by_id=user.id,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return _out(e)


@router.patch("/endpoints/{endpoint_id}", response_model=EndpointOut)
async def update_endpoint(
    endpoint_id: UUID,
    body: EndpointPatch,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("companies.edit")),
):
    e = (await db.execute(select(CustomApiEndpoint).where(CustomApiEndpoint.id == endpoint_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(404, "Endpoint не найден")
    if body.title is not None:
        e.title = body.title
    if body.description is not None:
        e.description = body.description
    if body.config is not None:
        e.config = body.config.model_dump()
    if body.is_active is not None:
        e.is_active = body.is_active
    await db.commit()
    await db.refresh(e)
    return _out(e)


@router.delete("/endpoints/{endpoint_id}", status_code=204)
async def delete_endpoint(
    endpoint_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("companies.edit")),
):
    await db.execute(delete(CustomApiEndpoint).where(CustomApiEndpoint.id == endpoint_id))
    await db.commit()


# ─── ДИСПЕТЧЕР: публичный data-endpoint ────────────────────────────

@dispatch_router.get("/{slug}")
async def dispatch(
    slug: str,
    year: Optional[int] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отдаёт данные сохранённого custom-endpoint.

    Доступ: нужно право required_permission (через роль/группу ИЛИ scope API-ключа)
    + company-scope вызывающего применяется к данным.
    """
    e = (await db.execute(
        select(CustomApiEndpoint).where(CustomApiEndpoint.slug == slug.lower())
    )).scalar_one_or_none()
    if e is None or not e.is_active:
        raise HTTPException(404, "Endpoint не найден или отключён")

    if not await has_effective_permission(db, user, e.required_permission):
        raise HTTPException(
            403,
            tr(
                "Нужно право: {permission}",
                current_locale(),
                permission=e.required_permission,
            ),
        )

    cfg = e.config or {}
    scope = None if has_unrestricted_view(user) else (await allowed_company_ids(db, user) or [])
    rows = await reg.run_source(
        db, e.source,
        company_ids=scope,
        year=year if year is not None else cfg.get("year"),
        standard=cfg.get("standard"),
        columns=cfg.get("columns") or None,
        limit=min(limit or cfg.get("limit") or 2000, 5000),
    )
    return {
        "endpoint": e.slug, "source": e.source, "title": e.title,
        "count": len(rows), "data": rows,
    }
