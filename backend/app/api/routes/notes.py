"""Notes (Smart Journal) API — thin HTTP layer (refactored 2026-05-25).

Endpoints:
  GET    /notes                  list with filters
  POST   /notes                  create
  PATCH  /notes/{id}             partial update
  DELETE /notes/{id}             delete
  GET    /notes/tags             distinct tags + counts
  GET    /notes/by-entity        find notes linked to specific entity

RBAC: notes are open to any authenticated user (per-company scope is enforced).
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import (
    allowed_company_ids, ensure_company_access, has_unrestricted_view,
)
from app.dependencies.notes import NotesServiceDep
from app.models.user import User
from app.schemas.notes import (
    NoteCreate, NoteKind, NoteListResponse, NoteRead, NoteUpdate, TagCount,
)


router = APIRouter(prefix="/notes", tags=["notes"])


async def _scoped_ids(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


@router.get("", response_model=NoteListResponse)
async def list_notes(
    service: NotesServiceDep,
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
    if company_id is not None:
        await ensure_company_access(db, user, company_id)
    return await service.list_notes(
        company_id=company_id,
        scoped_company_ids=await _scoped_ids(db, user) if company_id is None else None,
        kind=kind, tag=tag, query=q,
        only_unresolved=only_unresolved, include_resolved=include_resolved,
        pinned_first=pinned_first, limit=limit, offset=offset,
    )


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate,
    service: NotesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NoteRead:
    if payload.company_id is not None:
        await ensure_company_access(db, user, payload.company_id)
    return await service.create_note(payload, author_id=user.id)


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: UUID,
    payload: NoteUpdate,
    service: NotesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NoteRead:
    pre = await service.get_for_scope_check(note_id)
    if pre.company_id is not None:
        await ensure_company_access(db, user, pre.company_id)
    new_company_id = getattr(payload, "company_id", None)
    if new_company_id is not None and new_company_id != pre.company_id:
        await ensure_company_access(db, user, new_company_id)
    return await service.update_note(note_id, payload)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_note(
    note_id: UUID,
    service: NotesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pre = await service.get_for_scope_check(note_id)
    if pre.company_id is not None:
        await ensure_company_access(db, user, pre.company_id)
    await service.delete_note(note_id)
    return Response(status_code=204)


@router.get("/tags", response_model=List[TagCount])
async def list_tags(
    service: NotesServiceDep,
    company_id: Optional[UUID] = Query(None),
    limit: int = Query(200, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[TagCount]:
    if company_id is not None:
        await ensure_company_access(db, user, company_id)
    return await service.list_tags(
        company_id=company_id,
        scoped_company_ids=await _scoped_ids(db, user) if company_id is None else None,
        limit=limit,
    )


@router.get("/by-entity", response_model=List[NoteRead])
async def notes_by_entity(
    service: NotesServiceDep,
    entity_type: str = Query(...),
    entity_id: Optional[UUID] = Query(None),
    entity_key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[NoteRead]:
    return await service.notes_by_entity(
        entity_type=entity_type, entity_id=entity_id, entity_key=entity_key,
    )
