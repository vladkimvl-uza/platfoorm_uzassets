"""Smart Journal API -- 6 endpoints.

GET    /notes                  list с filters
POST   /notes                  create
PATCH  /notes/{id}             partial update
DELETE /notes/{id}             delete
GET    /notes/tags             distinct tags + counts (per company_id)
GET    /notes/by-entity        find notes linked to specific entity
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, ensure_company_access, has_unrestricted_view
from app.models.note import Note, NoteLink
from app.models.user import User
from app.schemas.notes import (
    NoteCreate,
    NoteKind,
    NoteListResponse,
    NoteRead,
    NoteUpdate,
    TagCount,
)

router = APIRouter(prefix="/notes", tags=["notes"])


# ============================================================
# RBAC -- notes endpoints are OPEN to any authenticated user;
# the three _ensure_* helpers below are intentional no-ops.
# (Per-company scope is applied separately via ensure_company_access /
#  allowed_company_ids on the list/create/update/delete handlers.)
# ============================================================
def _ensure_view(user: User) -> None:
    return None  # Notes: открыты всем авторизованным


def _ensure_edit(user: User) -> None:
    return None


def _ensure_delete(user: User) -> None:
    return None


# ============================================================
# Helpers
# ============================================================
async def _load_note_or_404(db: AsyncSession, note_id: UUID) -> Note:
    stmt = (
        select(Note)
        .where(Note.id == note_id)
        .options(selectinload(Note.links))
    )
    res = await db.execute(stmt)
    note = res.scalar_one_or_none()
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "note not found")
    return note


async def _replace_links(
    db: AsyncSession, note: Note, link_data: list
) -> None:
    """Полная замена набора note_links."""
    # Удаляем старые
    await db.execute(delete(NoteLink).where(NoteLink.note_id == note.id))
    # Вставляем новые
    for ld in link_data:
        link = NoteLink(
            note_id=note.id,
            entity_type=ld.entity_type,
            entity_id=ld.entity_id,
            entity_key=ld.entity_key,
            entity_label=ld.entity_label,
        )
        db.add(link)


# ============================================================
# Endpoints
# ============================================================
@router.get("", response_model=NoteListResponse)
async def list_notes(
    company_id: Optional[UUID] = Query(None),
    kind: Optional[List[NoteKind]] = Query(None),
    tag: Optional[List[str]] = Query(None),
    q: Optional[str] = Query(None, description="Search в title+body"),
    only_unresolved: bool = Query(False),
    include_resolved: bool = Query(True),
    pinned_first: bool = Query(True),
    limit: int = Query(500, le=2000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NoteListResponse:
    _ensure_view(user)

    conditions = []
    if company_id is not None:
        await ensure_company_access(db, user, company_id)
        conditions.append(Note.company_id == company_id)
    elif not has_unrestricted_view(user):
        # Scoped user без явного фильтра: ограничиваем выдачу по allowed_companies.
        allowed = await allowed_company_ids(db, user)
        if not allowed:
            return NoteListResponse(items=[], total=0, tag_counts=[])
        conditions.append(Note.company_id.in_(allowed))
    if kind:
        conditions.append(Note.kind.in_(kind))
    if tag:
        # tags &&  -- overlap (любой совпадающий)
        conditions.append(Note.tags.op("&&")(tag))
    if only_unresolved:
        conditions.append(Note.is_resolved == False)  # noqa: E712
    elif not include_resolved:
        conditions.append(Note.is_resolved == False)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                Note.title.ilike(like),
                Note.body.ilike(like),
            )
        )

    # === count ===
    count_stmt = select(func.count(Note.id))
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar_one()

    # === items ===
    stmt = select(Note).options(selectinload(Note.links))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    # Order: pinned -> event_date DESC NULLS LAST -> created_at DESC
    if pinned_first:
        stmt = stmt.order_by(
            Note.is_pinned.desc(),
            Note.event_date.desc().nulls_last(),
            Note.created_at.desc(),
        )
    else:
        stmt = stmt.order_by(
            Note.event_date.desc().nulls_last(),
            Note.created_at.desc(),
        )

    stmt = stmt.limit(limit).offset(offset)
    res = await db.execute(stmt)
    items = list(res.scalars().all())

    # === tag_counts (per current scope, без q/kind/tag фильтров для
    # отображения всех доступных тегов внутри компании/глобального scope) ===
    tag_count_conditions = []
    if company_id is not None:
        tag_count_conditions.append(Note.company_id == company_id)
    elif not has_unrestricted_view(user):
        # Mirror scoped filter, чтобы tag list не светил чужие компании.
        # allowed уже резолвили выше; здесь повторно — не идеально, но дёшево.
        scoped = await allowed_company_ids(db, user)
        if scoped:
            tag_count_conditions.append(Note.company_id.in_(scoped))

    tag_stmt = select(
        func.unnest(Note.tags).label("tag"),
        func.count().label("cnt"),
    )
    if tag_count_conditions:
        tag_stmt = tag_stmt.where(and_(*tag_count_conditions))
    tag_stmt = tag_stmt.group_by(text("tag")).order_by(text("cnt DESC"))

    tag_res = await db.execute(tag_stmt)
    tag_counts = [TagCount(tag=row[0], count=row[1]) for row in tag_res.all()]

    return NoteListResponse(items=items, total=total, tag_counts=tag_counts)


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NoteRead:
    _ensure_edit(user)
    if payload.company_id is not None:
        await ensure_company_access(db, user, payload.company_id)

    note = Note(
        user_id=user.id,
        author_id=user.id,
        company_id=payload.company_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        kind=payload.kind,
        title=payload.title,
        body=payload.body,
        tags=payload.tags,
        color=payload.color,
        is_pinned=payload.is_pinned,
        event_date=payload.event_date,
        due_date=payload.due_date,
    )
    db.add(note)
    await db.flush()

    if payload.links:
        for ld in payload.links:
            db.add(
                NoteLink(
                    note_id=note.id,
                    entity_type=ld.entity_type,
                    entity_id=ld.entity_id,
                    entity_key=ld.entity_key,
                    entity_label=ld.entity_label,
                )
            )

    await db.commit()
    return await _load_note_or_404(db, note.id)


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: UUID,
    payload: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NoteRead:
    _ensure_edit(user)
    note = await _load_note_or_404(db, note_id)
    if note.company_id is not None:
        await ensure_company_access(db, user, note.company_id)
    # Если меняется company_id — проверяем и новое значение.
    new_company_id = getattr(payload, "company_id", None)
    if new_company_id is not None and new_company_id != note.company_id:
        await ensure_company_access(db, user, new_company_id)

    data = payload.model_dump(exclude_unset=True)
    links_data = data.pop("links", None)

    # is_resolved -> resolved_at
    if "is_resolved" in data:
        new_val = bool(data["is_resolved"])
        if new_val and not note.is_resolved:
            note.resolved_at = datetime.now(timezone.utc)
        elif not new_val:
            note.resolved_at = None
        note.is_resolved = new_val
        data.pop("is_resolved", None)

    for k, v in data.items():
        setattr(note, k, v)

    if links_data is not None:
        # links -- объекты Pydantic. data.pop вернёт уже dict-ифицированное.
        # Восстанавливаем через payload.links для type-safety.
        await _replace_links(db, note, payload.links or [])

    await db.commit()
    return await _load_note_or_404(db, note.id)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ensure_delete(user)
    note = await _load_note_or_404(db, note_id)
    if note.company_id is not None:
        await ensure_company_access(db, user, note.company_id)
    await db.delete(note)
    await db.commit()
    return Response(status_code=204)


@router.get("/tags", response_model=List[TagCount])
async def list_tags(
    company_id: Optional[UUID] = Query(None),
    limit: int = Query(200, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[TagCount]:
    _ensure_view(user)

    conditions = []
    if company_id is not None:
        await ensure_company_access(db, user, company_id)
        conditions.append(Note.company_id == company_id)
    elif not has_unrestricted_view(user):
        scoped = await allowed_company_ids(db, user)
        if not scoped:
            return []
        conditions.append(Note.company_id.in_(scoped))

    stmt = select(
        func.unnest(Note.tags).label("tag"),
        func.count().label("cnt"),
    )
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.group_by(text("tag")).order_by(text("cnt DESC")).limit(limit)

    res = await db.execute(stmt)
    return [TagCount(tag=row[0], count=row[1]) for row in res.all()]


@router.get("/by-entity", response_model=List[NoteRead])
async def notes_by_entity(
    entity_type: str = Query(...),
    entity_id: Optional[UUID] = Query(None),
    entity_key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[NoteRead]:
    _ensure_view(user)

    if entity_id is None and entity_key is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "either entity_id or entity_key required",
        )

    link_conditions = [NoteLink.entity_type == entity_type]
    if entity_id is not None:
        link_conditions.append(NoteLink.entity_id == entity_id)
    if entity_key is not None:
        link_conditions.append(NoteLink.entity_key == entity_key)

    sub = (
        select(NoteLink.note_id)
        .where(and_(*link_conditions))
        .distinct()
        .scalar_subquery()
    )

    stmt = (
        select(Note)
        .where(Note.id.in_(sub))
        .options(selectinload(Note.links))
        .order_by(
            Note.is_pinned.desc(),
            Note.event_date.desc().nulls_last(),
            Note.created_at.desc(),
        )
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())
