"""Parse @-mentions from text + notify mentioned users (Pack 149).

Mention syntax: `@username` or `@email-prefix`. Match is case-insensitive
across User.username and User.email local-part. Each mention triggers an
in-app notification (type='mention') routed via notifications_service.

Used by:
  - Task/Project description (on create/update)
  - Comments (on create/update)

Mentions are stored on the parent entity's `extra.mentions` field as a
deduplicated list of user IDs — convenient for "who was tagged in this"
queries and for telegram_notify_hook's `n_type='mention'` routing.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# @username — letters, digits, dot, underscore, hyphen
_MENTION_RE = re.compile(r"(?:^|[\s\(\[\{,>])@([A-Za-z0-9._-]{2,64})")


def extract_mentions(text: Optional[str]) -> list[str]:
    """Return all @-tagged tokens from text (unique, lowercased)."""
    if not text:
        return []
    seen = set()
    out: list[str] = []
    for m in _MENTION_RE.finditer(text):
        tag = m.group(1).lower()
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


async def resolve_mentions_to_user_ids(
    db: AsyncSession, tags: Iterable[str],
) -> list[UUID]:
    """Match @-tags against active users (username OR email local-part).
    Returns deduplicated list of user IDs.
    """
    tag_list = [t.lower() for t in tags if t]
    if not tag_list:
        return []

    # Match username OR email starting with the tag + "@"
    conds = []
    for t in tag_list:
        conds.append(func.lower(User.username) == t)
        conds.append(func.lower(User.email).like(f"{t}@%"))

    rows = (await db.execute(
        select(User.id).where(User.is_active.is_(True)).where(or_(*conds))
    )).all()
    return [r[0] for r in rows]


async def _filter_by_company_access(
    db: AsyncSession, user_ids: list[UUID], company_id: UUID,
) -> list[UUID]:
    """P0 (аудит уведомлений): оставить только получателей с доступом к company_id.
    Раньше @mention слал полный текст комментария/описания + название компании
    ЛЮБОМУ совпавшему по тегу пользователю без RBAC-доступа к компании (утечка по
    in-app + Telegram + email). Теперь вне-scope получатели отсеиваются целиком."""
    from app.core.access import allowed_company_ids, has_unrestricted_view

    cid_s = str(company_id)
    out: list[UUID] = []
    for uid in user_ids:
        u = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if u is None:
            continue
        if has_unrestricted_view(u):
            out.append(uid)
            continue
        allowed = await allowed_company_ids(db, u)  # None=все, []=нет, [ids]
        if allowed is None or cid_s in {str(x) for x in allowed}:
            out.append(uid)
    return out


async def notify_mentioned_users(
    db: AsyncSession,
    *,
    text: str,
    actor_id: Optional[UUID],
    actor_name: Optional[str],
    entity_type: str,        # 'task' | 'project' | 'comment'
    entity_id: str,
    entity_title: str,
    link_url: Optional[str] = None,
    company_id: Optional[UUID] = None,
    company_name: Optional[str] = None,
    comment_id: Optional[str] = None,
) -> list[UUID]:
    """Parse mentions in `text`, look up users, fire in-app notifications.
    Returns list of user IDs that were notified.

    Silently no-ops if no mentions, no matching users, or the notifications
    service isn't available.
    """
    tags = extract_mentions(text)
    if not tags:
        return []
    user_ids = await resolve_mentions_to_user_ids(db, tags)
    if not user_ids:
        return []
    # P0-scope: если сущность привязана к компании — уведомляем только тех, у кого
    # есть доступ к ней (иначе утечка текста вне RBAC). Без company_id (сущность
    # вне компании) фильтр не применяем.
    if company_id is not None:
        user_ids = await _filter_by_company_access(db, user_ids, company_id)
        if not user_ids:
            return []
    # Self-mentions ARE allowed (people use it as a TODO/reminder).
    # If you want to skip, filter out actor_id here.

    try:
        from app.services.notifications_service import notify
    except ImportError:
        return user_ids

    notification_ids: list[str] = []
    for uid in user_ids:
        try:
            # Title shows actor name + entity context, body = full comment.
            kind_ru = {"task": "задаче", "project": "проекте", "comment": "комментарии"}.get(
                entity_type, "записи",
            )
            company_part = f" · {company_name}" if company_name else ""
            title = f"{actor_name or 'Кто-то'} упомянул вас в {kind_ru}: «{entity_title}»{company_part}"
            n = await notify(
                db,
                recipient_id=uid,
                type="mention",
                title=title,
                body=text[:600],
                source_module=entity_type,
                source_entity_id=str(entity_id),
                source_user_id=actor_id,
                link_url=link_url,
                priority="high",
                payload={
                    "actor_name": actor_name,
                    "entity_type": entity_type,
                    "entity_id": str(entity_id),
                    "entity_title": entity_title,
                    "company_name": company_name,
                    "comment_id": str(comment_id) if comment_id else None,
                    "raw_text": text[:1000],
                },
                commit=False,  # caller commits the parent transaction
            )
            if n is not None:
                notification_ids.append(str(n.id))
        except Exception:
            continue

    # Schedule background TG forwarding for each notification — they will
    # fire AFTER the parent transaction commits (own session, fire-and-forget).
    # The notify() helper itself only schedules when commit=True, so we do it
    # here explicitly for the commit=False path.
    if notification_ids:
        try:
            from app.services.telegram_notify_hook_bg import schedule_forward
            for nid in notification_ids:
                schedule_forward(nid)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "mention: tg-forward schedule failed: %s", e,
            )
    return user_ids
