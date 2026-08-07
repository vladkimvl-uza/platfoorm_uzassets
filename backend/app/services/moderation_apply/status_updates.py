"""Status-updates apply handler (deny-by-default Phase 4).

Применяет одобренную правку журнала «Текущий статус проекта/задачи». Зеркалит
POST /status-updates (create), PATCH /status-updates/{id} (edit),
DELETE /status-updates/{id} (delete).

У модуля НЕТ отдельного сервис-слоя — живой роут пишет ORM-модель StatusUpdate
напрямую (+ watch/audit/notify как побочные эффекты). Поэтому здесь мы повторяем
ровно ту же ORM-логику, что и роут.

Атрибуция — ПРЕДЛОЖИВШИЙ (proposer), не модератор, нажавший «принять»: author_id/
author_name записи, авто-подписка watch и запись аудита должны вести к автору.

Submission shape:
  target_module    = "status_updates"
  target_entity_id = <id записи StatusUpdate> для edit/delete; на create пусто и
                     застолбляется id созданной записи (идемпотентность повтора)
  proposed_value   = create → {"entity_type","entity_id","body","health"}
                     edit   → {"body"?, "health"?}
                     delete → {"id"}
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.status_update import StatusUpdate
from app.models.user import User
from app.schemas.status_update import ENTITY_TYPES, HEALTH_VALUES
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value)

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user

    # ── create ────────────────────────────────────────────────────
    if action in ("create", "created"):
        # Идемпотентность повтора: id созданной записи столбим в
        # target_entity_id в ТОМ ЖЕ коммите, что и запись, — если пометка
        # apply_status='applied' не успела сохраниться, повтор НЕ плодит дубль.
        if sub.target_entity_id:
            try:
                dup = (await db.execute(
                    select(StatusUpdate).where(StatusUpdate.id == UUID(sub.target_entity_id))
                )).scalar_one_or_none()
            except Exception:
                dup = None
            if dup is not None:
                return {"action": "create", "status_update_id": sub.target_entity_id,
                        "idempotent": True}

        entity_type = str(pv.get("entity_type") or "")
        entity_id = str(pv.get("entity_id") or "")
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"invalid entity_type: {entity_type!r}")
        if not entity_id:
            raise ValueError("status_updates create requires entity_id")
        body = str(pv.get("body") or "").strip()
        if not body:
            raise ValueError("status_updates create requires non-empty body")
        health = pv.get("health") or None
        if health and health not in HEALTH_VALUES:
            raise ValueError(f"invalid health: {health!r}")

        row = StatusUpdate(
            entity_type=entity_type,
            entity_id=entity_id,
            body=body,
            health=health,
            author_id=author.id,
            author_name=(getattr(author, "full_name", None) or getattr(author, "email", None)),
        )
        db.add(row)
        await db.flush()
        sub.target_entity_id = str(row.id)  # застолбить id в этом же коммите
        await db.commit()

        # Побочные эффекты живого роута — best-effort (как в роуте: в try/except,
        # чтобы сбой уведомления не откатывал уже применённую правку). Автор всех
        # эффектов — ПРЕДЛОЖИВШИЙ.
        await _post_create_side_effects(db, row, author, entity_type, entity_id)
        return {"action": "create", "status_update_id": str(row.id)}

    # ── edit ──────────────────────────────────────────────────────
    if action in ("edit", "update"):
        row = await _load_row(db, sub)
        if pv.get("body") is not None:
            row.body = str(pv["body"]).strip()
        if pv.get("health") is not None:
            health = pv.get("health") or None
            if health and health not in HEALTH_VALUES:
                raise ValueError(f"invalid health: {health!r}")
            row.health = health
        await db.commit()
        return {"action": "edit", "status_update_id": str(row.id)}

    # ── delete ────────────────────────────────────────────────────
    if action in ("delete", "archived"):
        row = await _load_row(db, sub)
        await db.delete(row)
        await db.commit()
        return {"action": "delete", "status_update_id": str(sub.target_entity_id)}

    raise ValueError(f"unknown status_updates action: {action!r}")


async def _load_row(db, sub: ModerationSubmission) -> StatusUpdate:
    if not sub.target_entity_id:
        raise ValueError("missing target_entity_id")
    try:
        rid = UUID(str(sub.target_entity_id))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"invalid status_update id: {sub.target_entity_id}") from e
    row = await db.get(StatusUpdate, rid)
    if row is None:
        raise ValueError(f"StatusUpdate {rid} no longer exists")
    return row


async def _post_create_side_effects(
    db, row: StatusUpdate, author: User, entity_type: str, entity_id: str,
) -> None:
    """Watch auto-follow + rich-аудит + уведомление watcher'ов — как в роуте,
    но атрибуция = ПРЕДЛОЖИВШИЙ. Всё best-effort: запись уже закоммичена."""
    excerpt = row.body if len(row.body) <= 140 else row.body[:140] + "…"
    label = "проекта" if entity_type == "project" else "задачи"

    from app.services import watch_service
    try:
        await watch_service.auto_follow(db, author.id, entity_type, entity_id)
        await db.commit()
    except Exception:
        pass

    _title: str | None = None
    try:
        from app.models.project import Project as _Project
        from app.models.task import Task as _Task
        from app.services import audit_service
        _model = _Task if entity_type == "task" else _Project
        _title = (await db.execute(
            select(_model.title).where(_model.id == entity_id)
        )).scalar_one_or_none()
        await audit_service.write_event(
            db,
            actor_id=author.id, actor_email=getattr(author, "email", None),
            actor_role=(author.roles[0].code if getattr(author, "roles", None) else None),
            action="status_update.created", module="tasks",
            entity_type=entity_type, entity_id=str(entity_id),
            entity_label=(_title or "")[:140],
            notes=f"обновил ход {label} «{_title or '—'}»: {excerpt}",
            is_critical=False,
        )
        await db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("status-update apply audit failed", exc_info=True)

    try:
        await watch_service.notify_watchers(
            db, entity_type=entity_type, entity_id=entity_id,
            actor_id=author.id, notif_type="watch.progress",
            title=f"Обновлён ход отслеживаемого {label}",
            body=f"{getattr(author, 'full_name', None) or getattr(author, 'email', '')}: {excerpt}",
            title_template="Обновлён ход отслеживаемого {kind}",
            template_vars={"kind": label},
            translate_vars={"kind"},
            payload={
                "entity_type": entity_type, "entity_id": entity_id,
                "entity_title": _title or None,
                "action": "progress", "excerpt": excerpt, "health": row.health or None,
            },
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("status-update apply watcher notify failed", exc_info=True)


register_apply_handler("status_updates", apply)
