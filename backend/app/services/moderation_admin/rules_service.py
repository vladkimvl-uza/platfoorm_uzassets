"""Moderation Rules CRUD + user flags + comments-listing helpers."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException

from app.models.moderation import ModerationRule
from app.schemas.moderation import (
    CommentRead,
    RuleCreate,
    RuleListResponse,
    RuleRead,
    RuleUpdate,
)
from app.uow.ports import UnitOfWorkABC


def _normalize_conditions(data: dict) -> dict:
    """Convert trigger_conditions list of pydantic models → plain dicts."""
    if data.get("trigger_conditions"):
        data["trigger_conditions"] = [
            c if isinstance(c, dict) else c.model_dump()
            for c in data["trigger_conditions"]
        ]
    return data


class ModerationRulesService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def list_rules(self) -> RuleListResponse:
        async with self.uow:
            rows = await self.uow.moderation.list_rules()
        return RuleListResponse(
            items=[RuleRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    async def get_rule(self, rule_id: UUID) -> RuleRead:
        async with self.uow:
            r = await self.uow.moderation.get_rule(rule_id)
        if not r:
            raise HTTPException(404, "Not found")
        return RuleRead.model_validate(r)

    async def create_rule(self, body: RuleCreate, *, created_by_id: UUID) -> RuleRead:
        now = datetime.now(UTC)
        data = _normalize_conditions(body.model_dump(exclude_unset=True))
        async with self.uow:
            r = ModerationRule(
                created_at=now, updated_at=now,
                created_by_id=created_by_id, version=1, **data,
            )
            self.uow.moderation.add(r)
            await self.uow.moderation.flush()
            await self.uow.moderation.refresh(r)
            return RuleRead.model_validate(r)

    async def update_rule(self, rule_id: UUID, body: RuleUpdate) -> RuleRead:
        data = _normalize_conditions(body.model_dump(exclude_unset=True))
        async with self.uow:
            r = await self.uow.moderation.get_rule(rule_id)
            if not r:
                raise HTTPException(404, "Not found")
            for k, v in data.items():
                setattr(r, k, v)
            r.version += 1
            r.updated_at = datetime.now(UTC)
            await self.uow.moderation.flush()
            await self.uow.moderation.refresh(r)
            return RuleRead.model_validate(r)

    async def delete_rule(self, rule_id: UUID) -> None:
        async with self.uow:
            r = await self.uow.moderation.get_rule(rule_id)
            if not r:
                raise HTTPException(404, "Not found")
            await self.uow.moderation.delete(r)
            await self.uow.moderation.flush()

    async def toggle_rule(self, rule_id: UUID) -> RuleRead:
        async with self.uow:
            r = await self.uow.moderation.get_rule(rule_id)
            if not r:
                raise HTTPException(404, "Not found")
            r.is_active = not r.is_active
            r.updated_at = datetime.now(UTC)
            await self.uow.moderation.flush()
            await self.uow.moderation.refresh(r)
            return RuleRead.model_validate(r)

    # ─── user flags (external / bypass) ───────────────────────────

    async def patch_user_flags(self, user_id: UUID, body: dict) -> dict:
        async with self.uow:
            u = await self.uow.moderation.get_user(user_id)
            if not u:
                raise HTTPException(404, "Not found")
            for f in ("is_external", "bypass_moderation"):
                if f in body and isinstance(body[f], bool):
                    setattr(u, f, body[f])
            if "external_org_name" in body:
                u.external_org_name = body["external_org_name"]
            await self.uow.moderation.flush()
            await self.uow.moderation.refresh(u)
            return {
                "id": str(u.id),
                "is_external": u.is_external,
                "bypass_moderation": u.bypass_moderation,
                "external_org_name": u.external_org_name,
            }

    # ─── состав модераторов ───────────────────────────────────────

    async def set_moderator(
        self, user_id: UUID, *, active: bool, actor,
    ) -> dict:
        """Убрать человека из модераторов или вернуть обратно.

        Механика — персональный оверлей прав (`user_permission_grant`), тот же,
        которым сетка «Доступ к модулям» уже точечно правит права: строка
        `deny` перебивает право, пришедшее из роли, а `grant` — выдаёт его без
        роли. Роли не трогаем: они несут десяток других прав, и снятие роли
        ради модерации отобрало бы у человека половину продукта.

        Чего эта операция НЕ делает намеренно: не чистит `moderator_ids` у
        других пользователей и не переписывает открытые заявки. Маршрутизация
        сама пропускает снятого (см. `resolve_moderators`), поэтому снятие
        обратимо — вернули право, и все прежние назначения снова работают.
        """
        from sqlalchemy import text as _text

        from app.core.security import has_effective_permission, is_super_admin
        from app.services import moderation_authority

        async with self.uow:
            db = self.uow.session
            target = await self.uow.moderation.get_user(user_id)
            if not target:
                raise HTTPException(404, "Пользователь не найден")

            # Владельца снимает только владелец (решение владельца 04.08.2026).
            # Держателю admin.users это закрыто: иначе администратор мог бы
            # отключить согласование у того, кто выдал ему сам доступ.
            if target.is_owner and not actor.is_owner:
                raise HTTPException(
                    403,
                    "Снять согласование с владельца платформы может только "
                    "владелец.",
                )

            if not active:
                # Хотя бы один модератор обязан остаться: заявки внешних авторов
                # иначе некому закрыть, а срока годности у них нет — повиснут
                # навсегда. Считаем всех действующих, включая владельца: после
                # решения 04.08.2026 отзыв действует и на него, значит и он
                # может оказаться последним.
                working = (await db.execute(_text(f"""
                    SELECT count(*) FROM users u
                     WHERE {moderation_authority.moderator_predicate('u')}
                """), moderation_authority.PARAMS)).scalar() or 0
                if working <= 1:
                    raise HTTPException(
                        409,
                        "Это последний действующий модератор. Сначала назначьте "
                        "другого — иначе заявки будет некому разбирать.",
                    )
            else:
                # Возврат = выдача права. Потолок привилегий как в RBAC: не-владелец
                # не может выдать то, чего у него нет, иначе держатель admin.users
                # сделает модератором сам себя.
                if not actor.is_owner and not is_super_admin(actor):
                    if not await has_effective_permission(db, actor, "moderation.review"):
                        raise HTTPException(
                            403,
                            "Вернуть человека в модераторы может только тот, у кого "
                            "право согласования есть у самого.",
                        )

            await db.execute(
                _text("""
                    DELETE FROM user_permission_grant
                     WHERE user_id = :uid AND permission_code = :code
                """),
                {"uid": str(user_id), "code": moderation_authority.REVIEW_CODE},
            )
            await db.execute(
                _text("""
                    INSERT INTO user_permission_grant
                        (id, user_id, permission_code, grant_type, granted_by_id,
                         created_at, updated_at)
                    VALUES (gen_random_uuid(), :uid, :code, :gtype, :actor,
                            now(), now())
                """),
                {
                    "uid": str(user_id),
                    "code": moderation_authority.REVIEW_CODE,
                    "gtype": "grant" if active else "deny",
                    "actor": str(actor.id),
                },
            )

            still = await moderation_authority.is_moderator(db, user_id)
            label = target.full_name or target.email

            from app.services import audit_service
            await audit_service.write_event(
                db,
                actor_id=actor.id, actor_email=actor.email,
                actor_role=(actor.roles[0].code if getattr(actor, "roles", None) else None),
                action="moderation.moderator_added" if active else "moderation.moderator_removed",
                module="moderation",
                entity_type="user", entity_id=str(user_id),
                entity_label=label[:140],
                notes=(
                    f"{label} возвращён в модераторы"
                    if active else
                    f"{label} снят с модерации: право согласования отозвано персонально"
                ),
                is_critical=not active,
                meta={"permission": moderation_authority.REVIEW_CODE,
                      "grant_type": "grant" if active else "deny"},
            )
            # Коммит делает выход из `async with`: правка прав и запись в
            # аудит уходят одной транзакцией.

        return {
            "id": str(user_id),
            "is_moderator": still,
            "full_name": target.full_name,
            "email": target.email,
        }

    # ─── comments listing (read-only) ─────────────────────────────

    async def list_comments(
        self,
        submission_id: UUID,
        *,
        include_internal: bool,
    ) -> list[CommentRead]:
        async with self.uow:
            rows = await self.uow.moderation.list_comments(
                submission_id, include_internal=include_internal,
            )
        return [CommentRead.model_validate(r) for r in rows]

    # ─── submission lookups for route's access checks ─────────────

    async def get_submission_for_access(self, submission_id: UUID):
        async with self.uow:
            return await self.uow.moderation.get_submission(submission_id)
