"""Watch/Follow «отслеживание» проектов и задач + рассылка watcher'ам.

Переиспользует notifications_service.notify() (каналы in-app/Telegram/email
и пользовательские preferences берутся оттуда).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ENTITY_TYPES = {"project", "task"}


# ─── Подписки ─────────────────────────────────────────────────────

async def follow(db: AsyncSession, user_id: UUID, entity_type: str, entity_id: str, source: str = "manual") -> None:
    await db.execute(
        text(
            "INSERT INTO entity_watch (user_id, entity_type, entity_id, source) "
            "VALUES (:uid, :et, :eid, :src) "
            "ON CONFLICT (user_id, entity_type, entity_id) DO NOTHING"
        ),
        {"uid": user_id, "et": entity_type, "eid": str(entity_id), "src": source},
    )
    await db.commit()


async def auto_follow(db: AsyncSession, user_id: Optional[UUID], entity_type: str, entity_id: str) -> None:
    """Тихая авто-подписка при вовлечённости (создал/назначен/прокомментировал).
    Не трогает существующую (в т.ч. ручную) подписку. Без commit — вызывается
    внутри другой транзакции; коммитит вызывающий."""
    if not user_id:
        return
    await db.execute(
        text(
            "INSERT INTO entity_watch (user_id, entity_type, entity_id, source) "
            "VALUES (:uid, :et, :eid, 'auto') "
            "ON CONFLICT (user_id, entity_type, entity_id) DO NOTHING"
        ),
        {"uid": user_id, "et": entity_type, "eid": str(entity_id)},
    )


async def auto_follow_email(db: AsyncSession, email: Optional[str], entity_type: str, entity_id: str) -> None:
    """Авто-подписать исполнителя по email (если это активный юзер). Без commit."""
    if not email:
        return
    r = await db.execute(
        text("SELECT id FROM users WHERE lower(email) = lower(:em) AND is_active = true"),
        {"em": email},
    )
    uid = r.scalar_one_or_none()
    if uid:
        await auto_follow(db, uid, entity_type, entity_id)


async def unfollow(db: AsyncSession, user_id: UUID, entity_type: str, entity_id: str) -> None:
    await db.execute(
        text(
            "DELETE FROM entity_watch WHERE user_id = :uid AND entity_type = :et AND entity_id = :eid"
        ),
        {"uid": user_id, "et": entity_type, "eid": str(entity_id)},
    )
    await db.commit()


async def is_watching(db: AsyncSession, user_id: UUID, entity_type: str, entity_id: str) -> bool:
    r = await db.execute(
        text(
            "SELECT 1 FROM entity_watch WHERE user_id = :uid AND entity_type = :et AND entity_id = :eid"
        ),
        {"uid": user_id, "et": entity_type, "eid": str(entity_id)},
    )
    return r.scalar_one_or_none() is not None


async def watcher_count(db: AsyncSession, entity_type: str, entity_id: str) -> int:
    r = await db.execute(
        text("SELECT count(*) FROM entity_watch WHERE entity_type = :et AND entity_id = :eid"),
        {"et": entity_type, "eid": str(entity_id)},
    )
    return int(r.scalar_one() or 0)


async def watcher_ids(db: AsyncSession, entity_type: str, entity_id: str, exclude: Optional[UUID] = None) -> list[UUID]:
    r = await db.execute(
        text("SELECT user_id FROM entity_watch WHERE entity_type = :et AND entity_id = :eid"),
        {"et": entity_type, "eid": str(entity_id)},
    )
    ids = [row[0] for row in r.all()]
    if exclude is not None:
        ids = [i for i in ids if i != exclude]
    return ids


async def _entity_link(db: AsyncSession, entity_type: str, entity_id: str) -> Optional[str]:
    """Deep-link на workspace компании сущности (для клика по уведомлению)."""
    try:
        tbl = "projects" if entity_type == "project" else "tasks"
        r = await db.execute(
            text(f"SELECT company_id::text FROM {tbl} WHERE id::text = :eid"),
            {"eid": str(entity_id)},
        )
        cid = r.scalar_one_or_none()
        return f"/library/companies/{cid}" if cid else None
    except Exception:
        return None


# ─── Рассылка watcher'ам ──────────────────────────────────────────

async def notify_watchers(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    actor_id: Optional[UUID],
    notif_type: str,
    title: str,
    body: Optional[str] = None,
    link_url: Optional[str] = None,
    payload: Optional[dict] = None,
    priority: Optional[str] = None,
) -> None:
    """Уведомить всех watcher'ов сущности (кроме автора). Best-effort —
    не роняет основную операцию."""
    try:
        ids = await watcher_ids(db, entity_type, entity_id, exclude=actor_id)
        if not ids:
            return
        if link_url is None:
            link_url = await _entity_link(db, entity_type, entity_id)
        from app.services.notifications_service import notify
        for uid in ids:
            try:
                await notify(
                    db,
                    recipient_id=uid,
                    type=notif_type,
                    title=title,
                    body=body,
                    priority=priority,
                    payload=payload,
                    link_url=link_url,
                    source_module=entity_type + "s",
                    source_entity_id=str(entity_id),
                    source_user_id=actor_id,
                    commit=False,
                )
            except Exception:
                continue
        await db.commit()
    except Exception:
        pass


# ─── «Отслеживаемое» — список с деталями ──────────────────────────

async def list_watched(db: AsyncSession, user_id: UUID) -> list[dict]:
    """Отслеживаемые проекты и задачи с деталями (title/status/due/company/
    health/непрочитанные комментарии) — для раздела «Отслеживаемое»."""
    out: list[dict] = []
    # Проекты
    pr = await db.execute(
        text(
            """
            SELECT 'project' AS etype, p.id::text AS eid, p.num, p.title, p.status,
                   p.due_date, p.company_id::text, COALESCE(c.name_ru, c.name_short, c.code) AS company_name, w.created_at AS followed_at
            FROM entity_watch w
            JOIN projects p ON p.id::text = w.entity_id
            LEFT JOIN companies c ON c.id = p.company_id
            WHERE w.user_id = :uid AND w.entity_type = 'project'
            ORDER BY w.created_at DESC
            """
        ),
        {"uid": user_id},
    )
    # Задачи
    tk = await db.execute(
        text(
            """
            SELECT 'task' AS etype, t.id::text AS eid, t.num, t.title, t.status,
                   t.due_date, t.company_id::text, COALESCE(c.name_ru, c.name_short, c.code) AS company_name, w.created_at AS followed_at
            FROM entity_watch w
            JOIN tasks t ON t.id::text = w.entity_id
            LEFT JOIN companies c ON c.id = t.company_id
            WHERE w.user_id = :uid AND w.entity_type = 'task'
            ORDER BY w.created_at DESC
            """
        ),
        {"uid": user_id},
    )
    rows = list(pr.mappings().all()) + list(tk.mappings().all())
    if not rows:
        return []
    # health последнего статуса
    ids_by_type: dict[str, list[str]] = {"project": [], "task": []}
    for r in rows:
        ids_by_type[r["etype"]].append(r["eid"])
    health: dict[tuple[str, str], Optional[str]] = {}
    for et, ids in ids_by_type.items():
        if not ids:
            continue
        hr = await db.execute(
            text(
                "SELECT DISTINCT ON (entity_id) entity_id, health FROM status_update "
                "WHERE entity_type = :et AND entity_id = ANY(:ids) "
                "ORDER BY entity_id, created_at DESC"
            ),
            {"et": et, "ids": ids},
        )
        for hid, h in hr.all():
            health[(et, hid)] = h
    for r in rows:
        out.append({
            "entity_type": r["etype"],
            "entity_id": r["eid"],
            "num": r["num"],
            "title": r["title"],
            "status": r["status"],
            "due_date": r["due_date"].isoformat() if r["due_date"] else None,
            "company_id": r["company_id"],
            "company_name": r["company_name"],
            "current_health": health.get((r["etype"], r["eid"])),
            "followed_at": r["followed_at"].isoformat() if r["followed_at"] else None,
        })
    # свежие сверху
    out.sort(key=lambda x: x["followed_at"] or "", reverse=True)
    return out
