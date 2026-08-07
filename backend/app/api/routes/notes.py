"""Notes (Smart Journal) API — thin HTTP layer (refactored 2026-05-25).

Endpoints:
  GET    /notes                  list with filters
  POST   /notes                  create
  PATCH  /notes/{id}             partial update
  DELETE /notes/{id}             delete
  GET    /notes/tags             distinct tags + counts
  GET    /notes/by-entity        find notes linked to specific entity

RBAC: чтение — любому аутентифицированному в пределах своей области компаний;
ЗАПИСЬ требует `tasks.edit` (см. _require_notes_write).
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import (
    allowed_company_ids,
    ensure_company_access,
    has_unrestricted_view,
)
from app.dependencies.notes import NotesServiceDep
from app.models.user import User
from app.schemas.notes import (
    ChecklistItemPatch,
    NoteCreate,
    NoteKind,
    NoteListResponse,
    NoteRead,
    NoteUpdate,
    TagCount,
)
from app.services.moderation_service import gate_or_apply
from app.services.notes.notifications import (
    diff_new_checklist_assignees,
    notify_checklist_assignment,
    notify_note_assignment,
)

log = logging.getLogger(__name__)


async def _require_notes_write(db: AsyncSession, user: User) -> None:
    """Заметки/календарь — данные компании, а не личный блокнот: они видны всем,
    у кого есть доступ к компании, и попадают в её календарь.

    До 29.07.2026 запись не спрашивала никакого права (в докстринге модуля так и
    стояло: «open to any authenticated user») — роль «Наблюдатель» создавала
    заметки, проверено на проде (POST /notes → 201). Право то же, что у задач:
    tasks.edit."""
    from app.core.security import has_effective_permission
    if await has_effective_permission(db, user, "tasks.edit"):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Недостаточно прав: изменение заметок требует права tasks.edit",
    )

router = APIRouter(prefix="/notes", tags=["notes"])


async def _scoped_ids(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


async def _dispatch_assignments(
    db: AsyncSession,
    *,
    before,
    after: NoteRead,
    actor: User,
) -> None:
    """Best-effort: уведомить вновь назначенных ответственных (заметка + пункты
    чек-листа). Никогда не ломает основной запрос."""
    try:
        old_assignee = getattr(before, "assignee_id", None) if before is not None else None
        if after.assignee_id and after.assignee_id != actor.id and after.assignee_id != old_assignee:
            await notify_note_assignment(db, note=after, actor=actor, recipient_id=after.assignee_id)
        for aid, item_text in diff_new_checklist_assignees(before, after, actor.id):
            await notify_checklist_assignment(
                db, note=after, item_text=item_text, actor=actor, recipient_id=aid,
            )
    except Exception as e:  # noqa: BLE001
        log.warning("notes assignment notify failed: %s", e)


@router.get("", response_model=NoteListResponse)
async def list_notes(
    service: NotesServiceDep,
    company_id: Optional[UUID] = Query(None),
    kind: Optional[list[NoteKind]] = Query(None),
    tag: Optional[list[str]] = Query(None),
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
    await _require_notes_write(db, user)
    if payload.company_id is not None:
        await ensure_company_access(db, user, payload.company_id)
    # Модерация (deny-by-default): внешний автор → в очередь. Scope компании
    # проверен ВЫШЕ, чтобы внешний автор не заводил заметку вне своего доступа.
    # Новой заметки ещё нет → entity_id=None; apply-хендлер создаёт и штампует id.
    queued, sub = await gate_or_apply(
        db, user=user, module="notes", action="create",
        entity_id=None, entity_label=(payload.title or "Заметка"),
        company_id=payload.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Создание заметки: {payload.title or payload.body[:80]}",
    )
    if queued:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    created = await service.create_note(payload, author_id=user.id)
    await _dispatch_assignments(db, before=None, after=created, actor=user)
    return created


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: UUID,
    payload: NoteUpdate,
    service: NotesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NoteRead:
    await _require_notes_write(db, user)
    pre = await service.get_for_scope_check(note_id)
    if pre.company_id is not None:
        await ensure_company_access(db, user, pre.company_id)
    new_company_id = getattr(payload, "company_id", None)
    if new_company_id is not None and new_company_id != pre.company_id:
        await ensure_company_access(db, user, new_company_id)
    # Модерация: scope обеих компаний (текущей и целевой) проверен ВЫШЕ.
    # exclude_unset — правим только присланные поля (apply зеркалит exclude_unset
    # в update_note; полный дамп затёр бы неприсланные поля в None).
    gate_company = new_company_id if new_company_id is not None else pre.company_id
    queued, sub = await gate_or_apply(
        db, user=user, module="notes", action="edit",
        entity_id=str(note_id), entity_label=(pre.title or "Заметка"),
        company_id=gate_company, sector_id=None, year=None,
        payload=payload.model_dump(mode="json", exclude_unset=True),
        diff_summary=f"Правка заметки: {pre.title or ''}".strip(),
    )
    if queued:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    updated = await service.update_note(note_id, payload)
    await _dispatch_assignments(db, before=pre, after=updated, actor=user)
    return updated


@router.patch("/checklist/{item_id}", response_model=NoteRead)
async def patch_checklist_item(
    item_id: UUID,
    payload: ChecklistItemPatch,
    service: NotesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NoteRead:
    """Точечное обновление пункта чек-листа (галочка с карточки / inline-правка
    текста, ответственного, дедлайна)."""
    await _require_notes_write(db, user)
    company_id, _ = await service.checklist_item_context(item_id)
    if company_id is not None:
        await ensure_company_access(db, user, company_id)
    # Модерация: второй edit-роут заметок. Дискриминатор checklist_item_id
    # отличает точечную правку пункта от правки самой заметки в apply-хендлере;
    # exclude_unset — правим только присланные поля пункта (см. update_note).
    queued, sub = await gate_or_apply(
        db, user=user, module="notes", action="edit",
        entity_id=str(item_id), entity_label="Пункт чек-листа заметки",
        company_id=company_id, sector_id=None, year=None,
        payload={"checklist_item_id": str(item_id),
                 "patch": payload.model_dump(mode="json", exclude_unset=True)},
        diff_summary="Правка пункта чек-листа заметки",
    )
    if queued:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    note, newly_assigned = await service.patch_checklist_item(
        item_id, payload, actor_id=user.id,
    )
    if newly_assigned:
        item = next((c for c in note.checklist if c.id == item_id), None)
        try:
            await notify_checklist_assignment(
                db, note=note, item_text=(item.text if item else ""),
                actor=user, recipient_id=newly_assigned,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("checklist assignment notify failed: %s", e)
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_note(
    note_id: UUID,
    service: NotesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_notes_write(db, user)
    pre = await service.get_for_scope_check(note_id)
    if pre.company_id is not None:
        await ensure_company_access(db, user, pre.company_id)
    # Модерация: scope компании заметки проверен ВЫШЕ. Роут отдаёт 204, поэтому
    # при постановке в очередь возвращаем JSONResponse(202), чтобы FastAPI
    # пропустил тело сквозь response_class=Response.
    queued, sub = await gate_or_apply(
        db, user=user, module="notes", action="delete",
        entity_id=str(note_id), entity_label=(pre.title or "Заметка"),
        company_id=pre.company_id, sector_id=None, year=None,
        payload={"note_id": str(note_id)},
        diff_summary=f"Удаление заметки: {pre.title or ''}".strip(),
    )
    if queued:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    await service.delete_note(note_id)
    return Response(status_code=204)


@router.get("/tags", response_model=list[TagCount])
async def list_tags(
    service: NotesServiceDep,
    company_id: Optional[UUID] = Query(None),
    limit: int = Query(200, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TagCount]:
    if company_id is not None:
        await ensure_company_access(db, user, company_id)
    return await service.list_tags(
        company_id=company_id,
        scoped_company_ids=await _scoped_ids(db, user) if company_id is None else None,
        limit=limit,
    )


@router.get("/by-entity", response_model=list[NoteRead])
async def notes_by_entity(
    service: NotesServiceDep,
    entity_type: str = Query(...),
    entity_id: Optional[UUID] = Query(None),
    entity_key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NoteRead]:
    return await service.notes_by_entity(
        entity_type=entity_type, entity_id=entity_id, entity_key=entity_key,
    )
