"""Unified global search (Spotlight-style).

Один эндпоинт ищет по всем основным сущностям сразу:
компании · проекты · задачи · консультанты · пользователи · заметки.
RBAC: company-bound сущности фильтруются по allowed_company_ids (scoped-юзер
видит только свои компании; owner/companies.view_all — всё).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.i18n import current_locale, tr
from app.core.security import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def global_search(
    q: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(6, ge=1, le=15),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    term = (q or "").strip()
    if not term:
        return {"results": []}
    like = f"%{term}%"
    allowed = await allowed_company_ids(db, user)  # None=all, []=none, [...]=scoped
    locale = current_locale()

    # Фрагмент company-scope для колонки `col`.
    cids: Optional[list[str]] = (
        [str(c) for c in allowed] if isinstance(allowed, list) else None
    )

    def scope(col: str) -> str:
        if allowed == []:
            return " AND false "
        if cids is None:
            return ""
        return f" AND {col}::text = ANY(:cids) "

    base = {"like": like, "lim": limit}
    if cids is not None:
        base["cids"] = cids

    results: list[dict] = []

    # — Компании —
    rows = (await db.execute(text(
        f"SELECT id::text, name_short, name_ru, code FROM companies "
        f"WHERE (name_ru ILIKE :like OR name_short ILIKE :like OR code ILIKE :like)"
        f"{scope('id')} ORDER BY name_ru LIMIT :lim"
    ), base)).all()
    for r in rows:
        results.append({
            "type": "company", "id": r[0], "title": r[1] or r[2],
            "subtitle": r[3] or tr("Компания", locale), "link": f"/library/companies/{r[0]}",
        })

    # — Проекты / Задачи —
    for etype, tbl in (("project", "projects"), ("task", "tasks")):
        rows = (await db.execute(text(
            f"SELECT e.id::text, e.title, e.num, c.name_short FROM {tbl} e "
            f"LEFT JOIN companies c ON c.id = e.company_id "
            f"WHERE e.is_archived = false AND (e.title ILIKE :like OR e.num ILIKE :like)"
            f"{scope('e.company_id')} ORDER BY e.title LIMIT :lim"
        ), base)).all()
        for r in rows:
            fallback = tr("Проект", locale) if etype == "project" else tr("Задача", locale)
            sub = (f"№{r[2]} · " if r[2] else "") + (r[3] or fallback)
            results.append({
                "type": etype, "id": r[0], "title": r[1], "subtitle": sub,
                "link": f"/{tbl}/{r[0]}",
            })

    # — Консультанты — (без company-scope)
    rows = (await db.execute(text(
        "SELECT id::text, name_ru, name_en FROM consultants "
        "WHERE name_ru ILIKE :like OR name_en ILIKE :like ORDER BY name_ru LIMIT :lim"
    ), {"like": like, "lim": limit})).all()
    for r in rows:
        results.append({
            "type": "consultant", "id": r[0], "title": r[1] or r[2],
            "subtitle": tr("Консультант", locale), "link": "/consultants",
        })

    # — Пользователи — (активные)
    rows = (await db.execute(text(
        "SELECT id::text, full_name, email FROM users "
        "WHERE is_active = true AND (full_name ILIKE :like OR email ILIKE :like) "
        "ORDER BY full_name NULLS LAST LIMIT :lim"
    ), {"like": like, "lim": limit})).all()
    for r in rows:
        results.append({
            "type": "user", "id": r[0], "title": r[1] or r[2],
            "subtitle": r[2] or tr("Пользователь", locale), "link": "/admin/rbac-v3",
        })

    # — Заметки —
    rows = (await db.execute(text(
        f"SELECT id::text, COALESCE(NULLIF(title, ''), left(body, 60)), company_id::text "
        f"FROM notes WHERE (title ILIKE :like OR body ILIKE :like)"
        f"{scope('company_id')} ORDER BY created_at DESC LIMIT :lim"
    ), base)).all()
    for r in rows:
        results.append({
            "type": "note", "id": r[0], "title": r[1] or tr("Заметка", locale),
            "subtitle": tr("Заметка", locale), "link": "/calendar",
        })

    return {"results": results, "query": term}
