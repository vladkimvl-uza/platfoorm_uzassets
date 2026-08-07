"""Status updates — «Текущий статус проекта» с историей (project/task).

Append-only журнал. Чтение → tasks.view; запись → tasks.edit. Редактировать/
удалять запись может её автор либо admin/owner.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.models.status_update import StatusUpdate
from app.models.user import User
from app.schemas.status_update import (
    ENTITY_TYPES,
    HEALTH_VALUES,
    StatusUpdateCreate,
    StatusUpdateRead,
    StatusUpdateUpdate,
)

router = APIRouter(prefix="/status-updates", tags=["status-updates"])


async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN, f"Permission required: {code}"
        )


def _can_modify(row: StatusUpdate, user: User) -> bool:
    return row.author_id == user.id or user.is_owner


async def _resolve_entity_company(
    db: AsyncSession, user: User, entity_type: str, entity_id: str,
) -> tuple[UUID | None, str | None]:
    """Компания и название сущности (project/task) по entity_id, с проверкой
    доступа автора к этой компании.

    Нужно ДО модерационного гейта: иначе внешний автор мог бы отправить в
    очередь правку хода задачи/проекта ВНЕ своего доступа (мы уже даём company_id
    модератору для scope на approve). Возвращает (company_id|None, title|None).
    Если сущность не найдена — (None, None) (лениво, как раньше в create); если
    найдена и привязана к компании — сверяем доступ (403 вне области)."""
    try:
        _eid = UUID(str(entity_id))
    except (ValueError, TypeError):
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid entity_id")
    if entity_type == "project":
        from app.models.project import Project as _Ent
    else:
        from app.models.task import Task as _Ent
    row = (await db.execute(
        select(_Ent.company_id, _Ent.title).where(_Ent.id == _eid)
    )).first()
    if row is None:
        return None, None
    company_id, title = row[0], row[1]
    if company_id is not None:
        from app.core.access import ensure_company_access
        await ensure_company_access(db, user, company_id)
    return company_id, title


@router.get("", response_model=list[StatusUpdateRead])
async def list_status_updates(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.view")
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid entity_type")
    # Security (audit M-11): доступ к КОМПАНИИ сущности (BOLA) — раньше любой с
    # tasks.view читал историю статусов чужой задачи/проекта по entity_id.
    try:
        _eid = UUID(str(entity_id))
    except (ValueError, TypeError):
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid entity_id")
    from app.core.access import ensure_company_access
    if entity_type == "project":
        from app.models.project import Project as _Ent
    else:
        from app.models.task import Task as _Ent
    _row = (await db.execute(select(_Ent.id, _Ent.company_id).where(_Ent.id == _eid))).first()
    if _row is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "not found")
    if _row[1] is not None:
        await ensure_company_access(db, user, _row[1])
    rows = (
        await db.execute(
            select(StatusUpdate)
            .where(
                StatusUpdate.entity_type == entity_type,
                StatusUpdate.entity_id == entity_id,
            )
            .order_by(desc(StatusUpdate.created_at))
        )
    ).scalars().all()
    return rows


@router.post("", response_model=StatusUpdateRead, status_code=http_status.HTTP_201_CREATED)
async def create_status_update(
    payload: StatusUpdateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.edit")
    if payload.entity_type not in ENTITY_TYPES:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid entity_type")
    if payload.health and payload.health not in HEALTH_VALUES:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid health")

    # Модерация (Phase 4): внешний автор → в очередь. Область автора проверяем ДО
    # гейта (ensure_company_access внутри резолвера) + получаем company_id для
    # scope модератора на approve. Записи ещё нет → entity_id=None, apply
    # штампует id созданной записи.
    _cid, _title = await _resolve_entity_company(
        db, user, payload.entity_type, payload.entity_id)
    _label_kind = "проекта" if payload.entity_type == "project" else "задачи"
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user, module="status_updates", action="create",
        entity_id=None,
        entity_label=f"Ход {_label_kind}: {_title or payload.entity_id}",
        company_id=_cid, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Обновление хода {_label_kind}",
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})

    row = StatusUpdate(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        body=payload.body.strip(),
        health=payload.health or None,
        author_id=user.id,
        author_name=user.full_name or user.email,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Watch: автор подписывается, watcher'ам — уведомление о ходе
    from app.services import watch_service
    try:
        await watch_service.auto_follow(db, user.id, payload.entity_type, payload.entity_id)
        await db.commit()
    except Exception:
        pass
    excerpt = row.body if len(row.body) <= 140 else row.body[:140] + "…"
    label = "проекта" if payload.entity_type == "project" else "задачи"
    _title: str | None = None  # название сущности (для аудита и payload уведомления)

    # Rich-аудит: ход проекта/задачи — с названием записи (для ленты аудита).
    try:
        from sqlalchemy import select as _sel
        from app.models.task import Task as _Task
        from app.models.project import Project as _Project
        from app.services import audit_service
        _model = _Task if payload.entity_type == "task" else _Project
        _title = (await db.execute(_sel(_model.title).where(_model.id == payload.entity_id))).scalar_one_or_none()
        await audit_service.write_event(
            db,
            actor_id=user.id, actor_email=user.email,
            actor_role=(user.roles[0].code if getattr(user, "roles", None) else None),
            action="status_update.created", module="tasks",
            entity_type=payload.entity_type, entity_id=str(payload.entity_id),
            entity_label=(_title or "")[:140],
            notes=f"обновил ход {label} «{_title or '—'}»: {excerpt}",
            is_critical=False,
        )
        await db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("status-update audit failed", exc_info=True)

    await watch_service.notify_watchers(
        db, entity_type=payload.entity_type, entity_id=payload.entity_id,
        actor_id=user.id, notif_type="watch.progress",
        title=f"Обновлён ход отслеживаемого {label}",
        body=f"{user.full_name or user.email}: {excerpt}",
        title_template="Обновлён ход отслеживаемого {kind}",
        template_vars={"kind": label},
        translate_vars={"kind"},
        payload={
            "entity_type": payload.entity_type, "entity_id": payload.entity_id,
            "entity_title": _title or None,
            "action": "progress", "excerpt": excerpt, "health": row.health or None,
        },
    )
    return row


@router.patch("/{update_id}", response_model=StatusUpdateRead)
async def update_status_update(
    update_id: UUID,
    payload: StatusUpdateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.edit")
    row = await db.get(StatusUpdate, update_id)
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "not found")
    if not _can_modify(row, user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "only author or owner")
    if payload.health is not None and payload.health and payload.health not in HEALTH_VALUES:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid health")

    # Модерация (Phase 4): внешний автор → в очередь. Область автора + company_id
    # резолвим по сущности записи ДО гейта.
    _cid, _ = await _resolve_entity_company(db, user, row.entity_type, row.entity_id)
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user, module="status_updates", action="edit",
        entity_id=str(update_id),
        entity_label=f"Ход {'проекта' if row.entity_type == 'project' else 'задачи'}",
        company_id=_cid, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary="Изменение записи хода",
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})

    if payload.body is not None:
        row.body = payload.body.strip()
    if payload.health is not None:
        row.health = payload.health or None
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{update_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_status_update(
    update_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.edit")
    row = await db.get(StatusUpdate, update_id)
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "not found")
    if not _can_modify(row, user):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "only author or owner")

    # Модерация (Phase 4): внешний автор → в очередь. Область автора + company_id
    # резолвим по сущности записи ДО гейта.
    _cid, _ = await _resolve_entity_company(db, user, row.entity_type, row.entity_id)
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user, module="status_updates", action="delete",
        entity_id=str(update_id),
        entity_label=f"Ход {'проекта' if row.entity_type == 'project' else 'задачи'}",
        company_id=_cid, sector_id=None, year=None,
        payload={"id": str(update_id)},
        diff_summary="Удаление записи хода",
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})

    await db.delete(row)
    await db.commit()
