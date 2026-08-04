"""Единственный источник ответа «кто модератор».

До этого модуля ответ существовал в двух копиях одинакового сырого SQL
(`moderation_service.moderator_ids` и `moderation_admin.query_service
.list_moderators`), и обе копии смотрели ТОЛЬКО на роли:

* персональный грант из `user_permission_grant` они не видели — а именно им
  `rbac_v3.service._ensure_review_permission` выдаёт право согласующему,
  назначенному при создании пользователя. Такой человек получал заявки, но в
  списке модераторов не показывался;
* отзыв права (deny) они не видели тоже — то есть «снять модератора» было
  физически нечем: список считался по ролям, а роль отбирать нельзя, не
  забрав вместе с ней всё остальное.

Здесь один предикат, которым пользуются и список, и маршрутизация, и счётчик
на вкладке. Правила совпадают с `core.security.has_effective_permission`:

* право даёт роль, персональный грант ИЛИ статус владельца;
* персональный отзыв (deny) забирает его у ЛЮБОГО, включая носителя роли
  «Администратор» и самого владельца — по решению владельца от 04.08.2026.
  Иммунитета нет ни у кого: на реальной базе право согласования у всех девяти
  модераторов приходит из роли admin, и любой иммунитет означал бы, что убрать
  из списка нельзя никого. Кто вправе нажать кнопку — отдельный вопрос, он
  решается в `set_moderator` (владельца снимает только владелец).

Проверка отзыва живёт здесь и в `_assert_can_resolve`, а не в
`has_effective_permission`: тот для владельца и super-admin выходит раньше
любых deny, и трогать общий резолвер прав ради одного модуля нельзя.
"""
from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

REVIEW_CODE = "moderation.review"

# Активный (не истёкший) персональный оверлей по нужному коду.
_OVERLAY = """
    SELECT 1 FROM user_permission_grant g
     WHERE g.user_id = {alias}.id
       AND g.permission_code = :review_code
       AND g.grant_type = :gtype
       AND (g.expires_at IS NULL OR g.expires_at > now())
"""

_ROLE_PERM = """
    SELECT 1 FROM user_role ur
      JOIN role_permission rp ON rp.role_id = ur.role_id
      JOIN permissions p      ON p.id = rp.permission_id
     WHERE ur.user_id = {alias}.id AND p.code = :review_code
"""

def moderator_predicate(alias: str = "u") -> str:
    """SQL-условие «этот пользователь — действующий модератор».

    Ожидает биндинги :review_code и :gtype_grant/:gtype_deny (см. PARAMS).
    """
    ov_grant = _OVERLAY.format(alias=alias).replace(":gtype", ":gtype_grant")
    ov_deny = _OVERLAY.format(alias=alias).replace(":gtype", ":gtype_deny")
    return f"""
        {alias}.is_active
        AND NOT EXISTS ({ov_deny})
        AND (
            {alias}.is_owner
            OR EXISTS ({_ROLE_PERM.format(alias=alias)})
            OR EXISTS ({ov_grant})
        )
    """


PARAMS: dict[str, Any] = {
    "review_code": REVIEW_CODE,
    "gtype_grant": "grant",
    "gtype_deny": "deny",
}


async def moderator_ids(db: AsyncSession) -> list[UUID]:
    rows = (await db.execute(
        text(f"SELECT DISTINCT u.id FROM users u WHERE {moderator_predicate('u')}"),
        PARAMS,
    )).scalars().all()
    return list(rows)


async def filter_moderators(db: AsyncSession, ids: Iterable[Any]) -> list[UUID]:
    """Оставить из списка только тех, кто реально модератор.

    Нужно маршрутизации: персональные согласующие и кураторы секторов хранятся
    в JSONB-полях пользователя и не пересчитываются при снятии права. Без этого
    фильтра заявка ушла бы человеку, которому approve вернёт 403, и повисла бы.
    """
    ids = [str(x) for x in ids if x]
    if not ids:
        return []
    rows = (await db.execute(
        text(f"""
            SELECT u.id FROM users u
             WHERE u.id = ANY(CAST(:ids AS uuid[]))
               AND {moderator_predicate('u')}
        """),
        {**PARAMS, "ids": ids},
    )).scalars().all()
    return list(rows)


async def is_moderator(db: AsyncSession, user_id: Any) -> bool:
    return bool(await filter_moderators(db, [user_id]))


async def review_denied(db: AsyncSession, user: Any) -> bool:
    """Право согласования отозвано персонально.

    Проверяется отдельно от `is_moderator`, потому что решать по заявке может и
    тот, кого на неё назначили маршрутизацией (`_can_resolve`). Отзыв должен
    перебивать и это назначение — иначе снятый модератор продолжит нажимать
    «Принять» в Telegram, где HTTP-гейта `require_permission` нет вовсе.

    Исключений нет и для владельца: он может снять согласование и с себя, и с
    другого владельца, и это должно действовать, а не быть отметкой в списке.
    """
    row = (await db.execute(
        text("""
            SELECT 1 FROM user_permission_grant g
             WHERE g.user_id = :uid
               AND g.permission_code = :review_code
               AND g.grant_type = :gtype_deny
               AND (g.expires_at IS NULL OR g.expires_at > now())
             LIMIT 1
        """),
        {**PARAMS, "uid": str(user.id)},
    )).first()
    return row is not None
