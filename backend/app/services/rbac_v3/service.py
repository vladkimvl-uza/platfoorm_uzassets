"""RBAC v3 use-cases — thin orchestration over RbacV3Repository.

NOT using the UoW pattern: route handlers chain multiple endpoints (e.g.
`return await get_role(role.code, db, user)` from inside `create_role`) and
audit-chain commits happen on the same session before the response is built.
The service operates on the raw `AsyncSession` passed by the route via
`Depends(get_db)` to preserve exact transactional semantics.

All endpoints require admin (is_owner OR `admin.users` perm), gated via
`_require_admin`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import false as sa_false
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.i18n import current_locale, tr
from app.core.password import hash_password, validate_password_policy
from app.core.security import has_effective_permission, is_super_admin
from app.models.rbac_v3 import GroupPermissionGrant
from app.models.user import (
    Group,
    Role,
    User,
    UserGroupRole,
    user_role,
)
from app.repositories.rbac_v3_repository import RbacV3Repository
from app.schemas.rbac_v3 import (
    GroupBrief,
    GroupCreatePayload,
    GroupDetail,
    GroupGrantItem,
    GroupMember,
    GroupMembersUpdate,
    GroupPermission,
    GroupPermissionsUpdate,
    GroupUpdatePayload,
    PasswordResetPayload,
    PermissionBrief,
    PreviewExchangeResponse,
    PreviewTokenResponse,
    RBACOverview,
    RoleBrief,
    RoleCreatePayload,
    RoleDetail,
    RolePermissionsUpdate,
    RoleUpdatePayload,
    UserBrief,
    UserCompanyMembership,
    UserCreatePayload,
    UserDetail,
    UserGroupMembership,
    UserListResponse,
    UserMembershipUpsert,
    UserUpdatePayload,
)
from app.services.auth_service import revoke_all_sessions

log = logging.getLogger(__name__)

# Сетка «Доступ к модулям» (frontend MODULE_REGISTRY) с 07.2026 предлагает два
# уровня доступа — «Наблюдать» и «Редактировать» (плюс «Нет доступа») — и
# испускает ТОЛЬКО коды вида:
#   read  → {module}.view   (+ {module}.export, если такой код есть в каталоге)
#   write → read + {module}.edit (+ {module}.import, если код есть в каталоге)
# Любое право вне этого множества (companies.view, sectors.view, users.view,
# investment.manage, procurement.request.view, tasks.create/assign,
# treasury.view, finmodel.view, announcements.view, …) сетка не видит, поэтому
# set_user_permissions НЕ имеет права автоматически денайнить такие права —
# иначе сохранение сетки молча отбирает у пользователя доступ роли.
#
# Модуль 'admin' из сетки исключён: администрирование платформы — не модуль
# компании, оно выдаётся ролью. В каталоге у него вообще нет пары view/edit
# (только admin.users / admin.role_edit / admin.audit), и выдача admin.users
# из сетки была бы скрытой эскалацией до администратора RBAC.
#
# Действия каждого модуля сетки — ТОЧНОЕ зеркало флагов hasExport / hasEdit /
# hasImport в MODULE_REGISTRY фронта (frontend/src/composables/usePermissions.ts),
# сверенное с каталогом прав прода. Держать таблицу здесь, а не перемножать
# модули на все суффиксы, обязательно: множество кодов, которое денайнит бэк,
# должно СОВПАДАТЬ с тем, что испускает levelsToPermissions. Перемножение
# «все модули × все суффиксы» давало 22 лишних кода (reports.edit, ai.edit,
# bp.export, tasks.import, …). Сегодня они инертны — их нет в каталоге, значит
# нет и в baseline, — но стоит завести любой из них ролью, и сохранение сетки
# молча отобрало бы это право, хотя сетка его даже не показывает (для reports
# и ai уровень «Редактировать» в UI заблокирован).
#
# {m}.view есть у каждого модуля сетки, поэтому в таблице он присутствует явно
# только для единообразия чтения.
_GRID_MODULE_ACTIONS: dict[str, frozenset[str]] = {
    "dashboard":            frozenset({"view", "export", "edit"}),
    # Компании — сама карточка/воркспейс компании. Без этого модуля сетка не
    # умела ни выдать, ни забрать доступ к рабочему пространству компании
    # (companies.view), хотя это самый частый запрос: «пусть видит только свою
    # компанию и больше ничего». companies.create/delete сеткой не управляются —
    # это администрирование портфеля, оно выдаётся ролью.
    "companies":            frozenset({"view", "edit"}),
    # Экран министра и сводный обзор портфеля — read-only поверхности: за ними
    # нет ни одного пишущего эндпоинта, поэтому уровень «Редактировать» в сетке
    # для них заблокирован и write-коды сюда не попадают.
    "exec_dashboard":       frozenset({"view"}),
    "exec_overview":        frozenset({"view"}),
    "bp":                   frozenset({"view", "edit", "import"}),
    "kpi":                  frozenset({"view", "edit", "import"}),
    "financials":           frozenset({"view", "export", "edit", "import"}),
    # SOE Health Check: правка глобальных порогов методики (PUT
    # /financials/soe-health/params). Удельная себестоимость: правка цен
    # энергоносителей и данных компании (PUT /unit-cost/*). Экспорта и импорта
    # у обоих экранов нет — таких кодов в каталоге тоже нет.
    "soe_health":           frozenset({"view", "edit"}),
    "unit_cost":            frozenset({"view", "edit"}),
    "credit":               frozenset({"view", "edit", "import"}),
    # Сетка показывает модуль как 'invest', права живут на 'investment'
    # (MODULE_CODE_ALIASES на фронте) — здесь всегда канонический код.
    "investment":           frozenset({"view", "export", "edit"}),
    "procurement":          frozenset({"view", "edit"}),
    "esg":                  frozenset({"view", "edit", "import"}),
    "governance":           frozenset({"view", "edit"}),
    "ratings":              frozenset({"view", "edit", "import"}),
    "procurement_analysis": frozenset({"view", "export", "edit"}),
    "consultants":          frozenset({"view", "export", "edit"}),
    "tasks":                frozenset({"view", "edit"}),
    "pmo":                  frozenset({"view", "export", "edit"}),
    # У reports и ai (как и у exec_dashboard/exec_overview выше) в каталоге нет
    # ни .edit, ни .import — уровень «Редактировать» для них в сетке
    # заблокирован, поэтому write-коды сюда не попадают и денайниться не могут.
    "reports":              frozenset({"view", "export"}),
    "monitoring":           frozenset({"view", "export", "edit"}),
    "ai":                   frozenset({"view"}),
}
_GRID_MODULE_CODES = tuple(_GRID_MODULE_ACTIONS)

# Суффиксы по уровням сетки: первый в паре — «якорный» код уровня, который
# сетка испускает всегда, второй — необязательный (испускается, только если
# такой код есть в каталоге прав, см. _GRID_MODULE_ACTIONS). Суффикс 'manage'
# сетка НЕ выдаёт НИКОГДА (это уровень роли, а раньше именно через него
# проходила эскалация с уровня «Полный доступ»), поэтому его нет и в списке
# управляемых: денайнить право, которого сетка не показывает, значит отбирать
# доступ, выданный ролью.
_GRID_LEVEL_SUFFIXES: dict[str, tuple[str, ...]] = {
    "read": ("view", "export"),
    "write": ("edit", "import"),
}
_GRID_PERMISSION_SUFFIXES = tuple(
    s for suffixes in _GRID_LEVEL_SUFFIXES.values() for s in suffixes
)


def _build_grid_code_level_anchor() -> dict[str, str]:
    """Код → код, наличие которого в выбранном уровне ЗАЩИЩАЕТ его от deny.

    Для якорных кодов (view/edit) это он сам. Для производных — якорь своего
    уровня: {m}.export живёт на уровне «Наблюдать» ({m}.view), {m}.import — на
    уровне «Редактировать» ({m}.edit). Так выбранный уровень сохраняет все свои
    коды целиком, а снятый — уходит в deny целиком.

    Берём только те действия, которые реально есть у модуля: набор ключей этой
    карты и есть множество денайнимых кодов, и оно обязано совпадать с набором
    levelsToPermissions на фронте.
    """
    anchors: dict[str, str] = {}
    for module, actions in _GRID_MODULE_ACTIONS.items():
        for suffixes in _GRID_LEVEL_SUFFIXES.values():
            anchor_suffix = suffixes[0]
            # Нет якоря уровня (reports/ai без .edit) — уровень модулю
            # недоступен, его производные коды тоже не наши.
            if anchor_suffix not in actions:
                continue
            anchor = f"{module}.{anchor_suffix}"
            for suffix in suffixes:
                if suffix in actions:
                    anchors[f"{module}.{suffix}"] = anchor
    # Легаси-алиас: старые роли несут ai.chat, а сетка испускает канонический
    # ai.view (гейт has_effective_permission считает их равными). Без явной
    # привязки уровень «Нет доступа» по модулю ИИ «залипал» бы: deny на ai.view
    # не ставился (его нет в базе роли), а ai.chat оставался и возвращал доступ.
    # Якорь именно ai.view: при выбранном уровне read/write алиас НЕ денайним —
    # активный deny на ai.chat в effective_permission_codes гасит и ai.view.
    anchors["ai.chat"] = "ai.view"
    return anchors


_GRID_CODE_LEVEL_ANCHOR: dict[str, str] = _build_grid_code_level_anchor()

_GRID_MANAGEABLE_CODES = frozenset(_GRID_CODE_LEVEL_ANCHOR)


async def _scope_users_query(db: AsyncSession, actor: User, q):
    """Сузить выборку пользователей до сотрудников компаний актора.

    Владелец и платформенный super-admin видят всех (возврат без изменений).
    Остальным (роль «Администратор компании» с правом admin.users) остаются
    только те, кто привязан к их компаниям — через User.organization_id ЛИБО
    через членство в группе такой компании. Пустая область → пустой список:
    fail-closed, чтобы сбой резолва не открывал весь справочник.
    """
    from app.core.access import allowed_company_ids, has_unrestricted_view
    if actor.is_owner or is_super_admin(actor) or has_unrestricted_view(actor):
        return q
    allowed = await allowed_company_ids(db, actor)
    if allowed is None:
        return q
    if not allowed:
        return q.where(sa_false())
    member_of_my_companies = (
        select(UserGroupRole.user_id)
        .join(Group, Group.id == UserGroupRole.group_id)
        .where(Group.company_id.in_(allowed))
    )
    return q.where(or_(
        User.organization_id.in_(allowed),
        User.id.in_(member_of_my_companies),
    ))


async def _ensure_target_in_scope(db: AsyncSession, actor: User, target: User) -> None:
    """Целевой пользователь должен быть в компаниях актора.

    Парная защита к _scope_users_query: список сужен, но чтение/правку по
    прямому UUID это не закрывает. Владелец и платформенный super-admin — без
    ограничений. Отвечаем 404, а не 403: существование чужого аккаунта не
    подтверждаем.
    """
    from app.core.access import allowed_company_ids, has_unrestricted_view
    if actor.is_owner or is_super_admin(actor) or has_unrestricted_view(actor):
        return
    allowed = await allowed_company_ids(db, actor)
    if allowed is None:
        return
    allowed_set = {str(x) for x in allowed}
    if str(getattr(target, "organization_id", "") or "") in allowed_set:
        return
    rows = (await db.execute(
        select(Group.company_id)
        .join(UserGroupRole, UserGroupRole.group_id == Group.id)
        .where(UserGroupRole.user_id == target.id, Group.company_id.is_not(None))
    )).scalars().all()
    if any(str(c) in allowed_set for c in rows):
        return
    raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")


async def _ensure_review_permission(db: AsyncSession, user_id: UUID) -> None:
    """Назначили согласующим — выдаём право открывать очередь модерации.

    Без этого назначение было бы «на бумаге»: экран `/admin/moderation` и
    approve/reject закрыты правом `moderation.review`, и заявка приходила бы
    человеку, который физически не может её открыть. Грант прямой (overlay
    user_permission_grant), поэтому администратор в любой момент снимет его в
    сетке доступа — правило остаётся одно: авторитет берётся из RBAC.
    """
    from sqlalchemy import text as _text
    await db.execute(
        _text("""
            INSERT INTO user_permission_grant
                (id, user_id, permission_code, grant_type, created_at, updated_at)
            SELECT gen_random_uuid(), CAST(:uid AS uuid), 'moderation.review',
                   'grant', now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM user_permission_grant
                WHERE user_id = CAST(:uid AS uuid)
                  AND permission_code = 'moderation.review'
            )
        """),
        {"uid": str(user_id)},
    )


async def _require_admin(db: AsyncSession, user: User) -> None:
    # P1 (аудит RBAC): через has_effective_permission (учитывает GroupPermissionGrant
    # grant/deny), а не синхронный _has_permission — иначе отзыв admin.users через
    # группу не действовал (fail-open), а выдача только через группу не работала
    # (fail-closed). Owner и роль-'admin' (super-admin) — быстрый bypass без запроса.
    if user.is_owner or is_super_admin(user):
        return
    if await has_effective_permission(db, user, "admin.users"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: admin.users (or owner status)",
    )


def _require_owner(user: User) -> None:
    """Управление статусом OWNER доступно ТОЛЬКО владельцу платформы."""
    if not user.is_owner:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Только OWNER может назначать или снимать статус OWNER",
        )


def _ensure_can_manage_target(actor: User, target: User) -> None:
    """P0 (аудит RBAC): аккаунт OWNER может трогать только OWNER. Защищает
    reset_password / deactivate / update(is_active) / delete от захвата и
    lockout'а владельца не-owner администратором (у force_password_change
    такой guard уже был — свели к единому)."""
    if getattr(target, "is_owner", False) and not actor.is_owner:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Only an owner can manage another owner account",
        )


@dataclass
class RbacV3Service:
    """All methods are gated by `_require_admin`. Pattern:
       1. validate, mutate, db.commit()
       2. append_audit_entry, db.commit()
       3. return reshaped detail (often via re-fetching)."""

    # ─── Common helpers ───────────────────────────────────────────

    @staticmethod
    def _repo(db: AsyncSession) -> RbacV3Repository:
        return RbacV3Repository(db)

    async def _hydrate_user(
        self,
        db: AsyncSession,
        u: User,
        company_names: Optional[dict] = None,
        company_memberships: Optional[list[UserCompanyMembership]] = None,
    ) -> UserBrief:
        repo = self._repo(db)
        rows = await repo.list_user_role_brief(u.id)
        return UserBrief(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            avatar_url=getattr(u, "avatar_url", None),
            department=u.department,
            job_title=getattr(u, "job_title", None),
            is_active=u.is_active,
            is_owner=u.is_owner,
            must_change_password=u.must_change_password,
            password_changed_at=getattr(u, "password_changed_at", None),
            last_login_at=u.last_login_at,
            last_seen_at=getattr(u, "last_seen_at", None),
            locked_until=u.locked_until,
            created_at=u.created_at,
            role_codes=[r.code for r in rows],
            role_names=[r.name_ru for r in rows],
            organization_id=u.organization_id,
            company=(company_names or {}).get(u.organization_id),
            allowed_companies=None,  # Pack 147: per-group memberships
            company_memberships=company_memberships or [],
        )

    async def _group_to_brief(self, db: AsyncSession, g: Group) -> GroupBrief:
        repo = self._repo(db)
        member_count = await repo.group_member_count(g.id)
        perm_count = await repo.group_perm_count(g.id)
        return GroupBrief(
            id=g.id, code=g.code, name=g.name, description=g.description,
            company_id=g.company_id, organization_id=g.organization_id,
            department=g.department,
            member_count=member_count, permission_count=perm_count,
            role_codes=[],
        )

    async def _ensure_group_membership_within_ceiling(
        self, db: AsyncSession, repo: RbacV3Repository, actor: User, g: Group,
    ) -> None:
        """P0 (аудит RBAC): вступление в группу расширяет доступ участника ДВУМЯ
        путями, которые role-ceiling (role_permission_codes) не покрывает:
          1) Group.company_id — само членство даёт видимость этой компании
             (allowed_company_ids, Pack 147 / rbac_scope_c3), даже без грантов →
             горизонтальная эскалация scope (выход из своей компании);
          2) GroupPermissionGrant группы — эффективны глобально на уровне проверки
             права (scope живёт только на гранте) → вертикальная эскалация прав.
        Поэтому не-owner не может добавить участника (в т.ч. себя) в группу, чьи
        company_id / гранты несут право или scope сверх его собственных — иначе
        self/сообщник получает их через членство.
        Зеркалит ceiling из set_group_permissions + company-scope из access.py.

        Решение владельца (29.07.2026): обход по is_super_admin СНЯТ. Право
        admin.users принадлежит единственной роли 'admin', которая и есть
        super-admin bypass, поэтому раньше потолок не срабатывал НИ РАЗУ —
        все администраторы проходили мимо него. Теперь потолок обходит только
        владелец платформы."""
        if actor.is_owner:
            return
        from app.core.access import allowed_company_ids
        allowed = await allowed_company_ids(db, actor)   # None = все компании
        allowed_str = None if allowed is None else {str(x) for x in allowed}

        # (1) company_id самой группы: членство даёт доступ к этой компании.
        # allowed_str is None = актор видит все компании (companies.view_all) → ок.
        if allowed_str is not None and getattr(g, "company_id", None) is not None:
            if str(g.company_id) not in allowed_str:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "Группа привязана к компании вне вашего доступа — управлять её "
                    "участниками может owner или администратор с доступом к этой компании.",
                )

        # (2) гранты группы: право/scope сверх собственных.
        grants = await repo.list_group_grants(g.id)
        if not grants:
            return
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        actor_codes = set(await repo.effective_permission_codes(actor.id))
        for gr in grants:
            if getattr(gr, "grant_type", "grant") == "deny":
                continue   # deny (понижение) не эскалация
            exp = getattr(gr, "expires_at", None)
            if exp is not None and exp < now:
                continue   # истёкший grant прав не даёт — не блокируем (как access.py)
            c = gr.permission_code
            if c == "admin" or c.startswith("admin.") or c not in actor_codes:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    tr(
                        "Группа несёт право сверх ваших ({permission}) — добавление участников в неё доступно только owner или администратору с этим правом.",
                        current_locale(), permission=c,
                    ),
                )
            sc = getattr(gr, "scope_companies", None)
            if sc and allowed_str is not None:
                excess = {str(x) for x in sc} - allowed_str
                if excess:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        tr(
                            "Группа даёт доступ к компаниям вне вашего scope: {companies}",
                            current_locale(), companies=", ".join(sorted(excess)),
                        ),
                    )

    async def _ensure_assigned_scope_within_ceiling(
        self, db: AsyncSession, actor: User, *,
        organization_id=None, allowed_sectors=None,
    ) -> None:
        """P0 (аудит RBAC): company/sector-scope, назначаемый пользователю напрямую
        (User.organization_id + User.allowed_sectors), эффективен как per-company
        доступ (allowed_company_ids: organization_id → одна компания, allowed_sectors
        → все компании сектора). Не-owner не может выдать (СЕБЕ или другому) scope
        сверх собственного — иначе self/сообщник выходит за пределы своей компании.
        Применяется в create_user/update_user. Вызывать до записи полей.

        Решение владельца (29.07.2026): обход по is_super_admin снят — см.
        _ensure_group_membership_within_ceiling."""
        if actor.is_owner:
            return
        from app.core.access import allowed_company_ids
        allowed = await allowed_company_ids(db, actor)
        if allowed is None:
            return   # актор видит все компании (companies.view_all) → любой scope в пределах
        allowed_str = {str(x) for x in allowed}
        # organization_id: назначаемая компания должна быть в доступе актора
        if organization_id is not None and str(organization_id) not in allowed_str:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Нельзя назначить пользователю компанию вне вашего доступа.",
            )
        # allowed_sectors: только подмножество собственных секторов актора (иначе
        # company-scoped админ выдал бы себе целый сектор = все его компании)
        if allowed_sectors:
            actor_sectors = {str(s) for s in (getattr(actor, "allowed_sectors", None) or [])}
            excess = {str(s) for s in allowed_sectors} - actor_sectors
            if excess:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    tr(
                        "Нельзя выдать секторы вне ваших: {sectors}",
                        current_locale(), sectors=", ".join(sorted(excess)),
                    ),
                )

    # ─── Overview ─────────────────────────────────────────────────

    async def _resolve_create_group_memberships(
        self,
        db: AsyncSession,
        repo: RbacV3Repository,
        payload: UserCreatePayload,
        actor: User,
    ) -> list[tuple[Group, Role]]:
        """Validate group-scoped role assignments supplied during user creation."""
        requested: list[tuple[UUID, str]] = [
            (m.group_id, m.role_code) for m in (payload.group_memberships or [])
        ]

        # Back-compat for older clients that sent allowed_companies without
        # group_memberships. A single role_code is treated as the scoped role;
        # otherwise viewer is the least-privileged default.
        if not requested and payload.allowed_companies:
            # lookup_company_groups_by_refs ключует результат ОБРЕЗАННОЙ ссылкой и
            # выбрасывает пустые. Сравнивать с сырым payload нельзя: ' alpha' или ''
            # в списке дали бы 400 «Unknown company/group refs» на существующей
            # компании. Нормализуем один раз и работаем только с нормализованным.
            raw_refs = [str(r).strip() for r in payload.allowed_companies if str(r).strip()]
            groups_by_ref = await repo.lookup_company_groups_by_refs(raw_refs)
            missing_refs = [ref for ref in raw_refs if ref not in groups_by_ref]
            if missing_refs:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Unknown company/group refs: {sorted(missing_refs)}",
                )
            scoped_role = payload.role_codes[0] if len(payload.role_codes) == 1 else "viewer"
            requested = [(groups_by_ref[ref].id, scoped_role) for ref in raw_refs]

        if not requested:
            return []

        deduped: dict[UUID, str] = {}
        for group_id, role_code in requested:
            existing = deduped.get(group_id)
            if existing is not None and existing != role_code:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Group {group_id} is assigned more than one role",
                )
            deduped[group_id] = role_code

        groups_by_id = await repo.lookup_groups_by_ids(list(deduped.keys()))
        missing_groups = [str(gid) for gid in deduped if gid not in groups_by_id]
        if missing_groups:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown group ids: {sorted(missing_groups)}",
            )

        roles = list(await repo.lookup_roles(list(set(deduped.values()))))
        roles_by_code = {r.code: r for r in roles}
        missing_roles = [rc for rc in set(deduped.values()) if rc not in roles_by_code]
        if missing_roles:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown role codes: {sorted(missing_roles)}",
            )

        actor_codes: set[str] | None = None
        out: list[tuple[Group, Role]] = []
        for group_id, role_code in deduped.items():
            group = groups_by_id[group_id]
            role = roles_by_code[role_code]
            if role.code == "admin" and not actor.is_owner:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "Only an owner can assign the 'admin' role.",
                )
            # Решение владельца (29.07.2026): потолок прав применяется ко ВСЕМ,
            # кроме владельца — обход по is_super_admin снят (роль 'admin' и есть
            # super-admin, поэтому потолок раньше не срабатывал ни разу).
            if not actor.is_owner:
                if actor_codes is None:
                    actor_codes = set(await repo.effective_permission_codes(actor.id))
                role_perms = set(await repo.role_permission_codes(role.id))
                excess = [
                    c for c in sorted(role_perms)
                    if c == "admin" or c.startswith("admin.") or c not in actor_codes
                ]
                if excess:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        f"Role '{role.code}' grants permissions above yours: " + ", ".join(excess),
                    )
            await self._ensure_group_membership_within_ceiling(db, repo, actor, group)
            out.append((group, role))
        return out

    async def overview(self, db: AsyncSession, user: User) -> RBACOverview:
        await _require_admin(db, user)
        c = await self._repo(db).overview_counts()
        return RBACOverview(
            users_total=c["users_total"],
            users_active=c["users_active"],
            users_inactive=c["users_total"] - c["users_active"],
            roles_total=c["roles_total"],
            permissions_total=c["perms_total"],
            users_without_roles=c["users_without_roles"],
            most_assigned_roles=c["top_rows"],
        )

    # ─── Permissions ──────────────────────────────────────────────

    async def list_permissions(
        self, db: AsyncSession, user: User
    ) -> list[PermissionBrief]:
        await _require_admin(db, user)
        rows = await self._repo(db).list_permissions()
        return [PermissionBrief.model_validate(p) for p in rows]

    # ─── Roles ────────────────────────────────────────────────────

    async def list_roles(self, db: AsyncSession, user: User) -> list[RoleBrief]:
        await _require_admin(db, user)
        out: list[RoleBrief] = []
        for r in await self._repo(db).list_roles_with_perm_count():
            rb = RoleBrief.model_validate(r.Role)
            rb.permission_count = r.perm_count or 0
            out.append(rb)
        return out

    async def get_role(
        self, code: str, db: AsyncSession, user: User
    ) -> RoleDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        role = await repo.get_role_by_code(code)
        if not role:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found"
            )
        perms = list(await repo.list_role_permissions(role.id))
        return RoleDetail(
            id=role.id, code=role.code, name_ru=role.name_ru,
            name_uz=role.name_uz, name_en=role.name_en,
            description_ru=role.description_ru,
            is_system=role.is_system, sort_order=role.sort_order,
            permission_count=len(perms),
            permissions=[PermissionBrief.model_validate(p) for p in perms],
        )

    async def create_role(
        self, payload: RoleCreatePayload, db: AsyncSession, user: User
    ) -> RoleDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        if await repo.get_role_by_code(payload.code):
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                f"Role '{payload.code}' already exists",
            )
        perm_objs: list = []
        if payload.permission_codes:
            perm_objs = list(await repo.lookup_permissions(payload.permission_codes))
            missing = set(payload.permission_codes) - {p.code for p in perm_objs}
            if missing:
                # Фронт генерирует канонический набор {module}.view/edit/export/manage
                # на уровень, но каталог прав разрежённый (напр. governance имеет
                # только view/edit; export/manage нет). Несуществующие коды игнорируем
                # (грант = валидное подмножество — недо-грант безопасен), не падая 400.
                log.warning(
                    "[rbac] create_role '%s': ignoring unknown permission codes: %s",
                    payload.code, sorted(missing),
                )
            # P0 ceiling: не-owner не может вложить в роль права сверх собственных
            # (иначе крафтит роль с admin.*/чужими правами и назначает её).
            if not user.is_owner:
                actor_codes = set(await repo.effective_permission_codes(user.id))
                excess = [p.code for p in perm_objs
                          if p.code == "admin" or p.code.startswith("admin.") or p.code not in actor_codes]
                if excess:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        tr(
                            "Нельзя вложить в роль права сверх ваших: {permissions}",
                            current_locale(), permissions=", ".join(sorted(excess)),
                        ),
                    )
        role = Role(
            code=payload.code, name_ru=payload.name_ru, name_en=payload.name_en,
            description_ru=payload.description_ru, sort_order=payload.sort_order,
            is_system=False,
        )
        repo.add(role)
        await repo.flush()
        for p in perm_objs:
            await repo.assign_role_permission(role.id, p.id)
        await db.commit()

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.role.create",
            entity_type="role", entity_id=str(role.id),
            notes=f"role={role.code}, permissions={len(perm_objs)}",
        )
        await db.commit()
        return await self.get_role(role.code, db, user)

    async def update_role(
        self, code: str, payload: RoleUpdatePayload,
        db: AsyncSession, user: User,
    ) -> RoleDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        role = await repo.get_role_by_code(code)
        if not role:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found"
            )
        changed: list[str] = []
        if payload.name_ru is not None and payload.name_ru != role.name_ru:
            role.name_ru = payload.name_ru; changed.append("name_ru")
        if payload.name_en is not None and payload.name_en != role.name_en:
            role.name_en = payload.name_en; changed.append("name_en")
        if payload.description_ru is not None and payload.description_ru != role.description_ru:
            role.description_ru = payload.description_ru; changed.append("description_ru")
        if payload.sort_order is not None and payload.sort_order != role.sort_order:
            role.sort_order = payload.sort_order; changed.append("sort_order")
        if changed:
            await db.commit()
            await append_audit_entry(
                db, actor_id=str(user.id), actor_email=user.email,
                action="rbac.role.update",
                entity_type="role", entity_id=str(role.id),
                notes=f"role={code}, fields={','.join(changed)}",
            )
            await db.commit()
        return await self.get_role(code, db, user)

    async def update_role_permissions(
        self, code: str, payload: RolePermissionsUpdate,
        db: AsyncSession, user: User,
    ) -> RoleDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        role = await repo.get_role_by_code(code)
        if not role:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found"
            )
        found = list(await repo.lookup_permissions(payload.permission_codes))
        missing = set(payload.permission_codes) - {p.code for p in found}
        if missing:
            # Разрежённый каталог прав: игнорируем несуществующие коды (валидное
            # подмножество, недо-грант безопасен), не падая 400. См. create_role.
            log.warning(
                "[rbac] update_role '%s': ignoring unknown permission codes: %s",
                code, sorted(missing),
            )
        # H5: non-owner cannot drop admin.users from `admin`
        if (
            code == "admin" and not user.is_owner
            and "admin.users" not in {p.code for p in found}
        ):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Нельзя удалить право 'admin.users' из роли 'admin' без статуса owner.",
            )
        # P0 ceiling: не-owner не может вложить в роль права сверх собственных
        # (защита от эскалации через правку прав роли).
        if not user.is_owner:
            actor_codes = set(await repo.effective_permission_codes(user.id))
            excess = [p.code for p in found
                      if p.code == "admin" or p.code.startswith("admin.") or p.code not in actor_codes]
            if excess:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    tr(
                        "Нельзя вложить в роль права сверх ваших: {permissions}",
                        current_locale(), permissions=", ".join(sorted(excess)),
                    ),
                )
        await repo.clear_role_permissions(role.id)
        for p in found:
            await repo.assign_role_permission(role.id, p.id)
        await db.commit()

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.role.update_permissions",
            entity_type="role", entity_id=str(role.id),
            notes=f"role={code}, permissions_count={len(found)}",
        )
        await db.commit()
        return await self.get_role(code, db, user)

    async def delete_role(
        self, code: str, db: AsyncSession, user: User
    ) -> None:
        await _require_admin(db, user)
        repo = self._repo(db)
        role = await repo.get_role_by_code(code)
        if not role:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found"
            )
        if role.is_system:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"System role '{code}' cannot be deleted",
            )
        user_count = await repo.role_user_count(role.id)
        if user_count > 0:
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                f"Cannot delete role '{code}': {user_count} user(s) still assigned. "
                "Reassign them first.",
            )
        await repo.clear_role_permissions(role.id)
        role_id = str(role.id)
        await repo.delete(role)
        await db.commit()

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.role.delete",
            entity_type="role", entity_id=role_id,
            notes=f"role={code}",
        )
        await db.commit()

    # ─── Users ────────────────────────────────────────────────────

    async def list_users(
        self,
        db: AsyncSession,
        user: User,
        *,
        is_active: Optional[bool] = None,
        role_code: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> UserListResponse:
        await _require_admin(db, user)
        repo = self._repo(db)
        q = repo.base_user_query()
        # Область: администратор КОМПАНИИ видит только сотрудников своих компаний.
        # Раньше список отдавался целиком любому носителю admin.users — то есть
        # справочник всех 22 организаций с их людьми, должностями и контактами.
        # Владелец и платформенный админ (super-admin) видят всех.
        q = await _scope_users_query(db, user, q)
        if is_active is not None:
            q = q.where(User.is_active.is_(is_active))
        if role_code:
            q = (
                q.join(user_role, user_role.c.user_id == User.id)
                .join(Role, Role.id == user_role.c.role_id)
                .where(Role.code == role_code).distinct()
            )
        if search:
            s = f"%{search.strip().lower()}%"
            q = q.where(or_(
                func.lower(User.email).like(s),
                func.lower(User.full_name).like(s),
                func.lower(User.department).like(s),
            ))
        total = await repo.count_users(q)
        q = q.order_by(User.full_name).limit(limit).offset(offset)
        users = list(await repo.list_users(q))
        # Bulk-резолв названий компаний (organization_id → Company) — без N+1.
        from sqlalchemy import select as _select

        from app.models.company import Company
        _org_ids = {u.organization_id for u in users if u.organization_id}
        _company_names: dict = {}
        if _org_ids:
            _rows = (await db.execute(
                _select(Company.id, Company.name_short, Company.name_ru)
                .where(Company.id.in_(_org_ids))
            )).all()
            _company_names = {r[0]: (r[1] or r[2]) for r in _rows}
        _membership_rows = await repo.list_user_company_memberships([u.id for u in users])
        _memberships_by_user: dict[UUID, list[UserCompanyMembership]] = {}
        for row in _membership_rows:
            _memberships_by_user.setdefault(row.user_id, []).append(
                UserCompanyMembership(
                    company_id=row.company_id,
                    company_name=row.company_name_short or row.company_name_ru,
                    group_id=row.group_id,
                    group_name=row.group_name,
                    role_code=row.role_code,
                    role_name=row.role_name,
                )
            )
        items = [
            await self._hydrate_user(
                db,
                u,
                _company_names,
                _memberships_by_user.get(u.id, []),
            )
            for u in users
        ]
        return UserListResponse(items=items, total=total)

    async def get_user(
        self, user_id: UUID, db: AsyncSession, user: User
    ) -> UserDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)

        base = await self._hydrate_user(db, u)
        perms = await repo.effective_permission_codes(u.id)
        user_grants = await repo.user_grant_rows(u.id)
        mem_rows = await repo.list_user_memberships(u.id)
        memberships = [
            UserGroupMembership(
                group_id=r[0], group_code=r[1], group_name=r[2],
                company_id=r[3], role_code=r[4], role_name=r[5],
            )
            for r in mem_rows
        ]
        return UserDetail(
            **base.model_dump(),
            effective_permissions=perms,
            direct_permissions=sorted(c for c, grant_type in user_grants if grant_type == "grant"),
            denied_permissions=sorted(c for c, grant_type in user_grants if grant_type == "deny"),
            group_memberships=memberships,
            is_external=bool(getattr(u, "is_external", False)),
            bypass_moderation=bool(getattr(u, "bypass_moderation", False)),
            external_org_name=getattr(u, "external_org_name", None),
            allowed_sectors=getattr(u, "allowed_sectors", None) or None,
            moderator_ids=[UUID(str(x)) for x in (getattr(u, "moderator_ids", None) or []) if x],
            moderated_sector_codes=getattr(u, "moderated_sector_codes", None) or None,
        )

    async def set_user_permissions(
        self, user_id: UUID, payload: "RolePermissionsUpdate", db: AsyncSession, user: User,
    ) -> UserDetail:
        """Прямое per-user редактирование доступа к модулям (OWNER/ADMIN).

        Сетка «Доступ к модулям» → permission_codes. Сохраняем как overlay:
        grant на то, чего нет в роли (повышение), deny на то, что роль даёт,
        но сетка убирает (понижение). Так effective == выбранная сетка.
        """
        await _require_admin(db, user)
        repo = self._repo(db)
        target = await repo.get_user_by_id(user_id)
        if not target:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        if target.is_owner:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "OWNER обходит все проверки — его доступ не редактируется здесь.",
            )

        valid = await repo.all_permission_codes()
        desired = {c for c in payload.permission_codes if c in valid}
        # Несуществующие коды отбрасываются молча — и именно так сетка годами
        # «не сохраняла» уровни по модулям, у которых нужного кода нет в
        # каталоге (reports.edit, ai.edit, admin.view). Пишем в лог, чтобы
        # рассинхрон фронта и каталога был виден, а не выглядел как «не
        # сохранилось без причины».
        unknown = sorted(set(payload.permission_codes) - valid)
        if unknown:
            log.warning(
                "rbac.set_user_permissions: коды вне каталога прав отброшены "
                "(user_id=%s, codes=%s)", user_id, unknown,
            )
        baseline = await repo.base_permission_codes(user_id)

        # КРИТИЧНО: сетка «Доступ к модулям» оперирует только своими модулями и
        # уровнями «Наблюдать»/«Редактировать», то есть кодами
        # {module}.{view|export|edit|import}. Права роли, которые сетка не
        # способна представить (companies.view, sectors.view, users.view,
        # admin.users, {module}.manage, procurement.request.view,
        # tasks.create/assign, treasury.view, …), НЕ должны автоматически
        # уходить в deny — иначе сохранение сетки молча отбирает у пользователя
        # доступ, который даёт роль (например, список компаний → 403).
        # Поэтому deny ограничиваем grid-представимыми кодами; всё вне сетки
        # остаётся за ролью нетронутым.
        #
        # Deny ставим по ЯКОРЮ УРОВНЯ, а не по прямому вхождению кода в payload:
        # производные коды ({m}.export на уровне «Наблюдать», {m}.import на
        # уровне «Редактировать», легаси-алиас ai.chat) есть в каталоге не у
        # каждого модуля, и фронт испускает их условно. Если бы deny считался
        # «нет в payload → запретить», то модуль с выбранным уровнем терял бы
        # export/import, которые этому уровню принадлежат.
        denies = sorted(
            code for code in (baseline & _GRID_MANAGEABLE_CODES)
            if code not in desired and _GRID_CODE_LEVEL_ANCHOR[code] not in desired
        )
        grants = sorted(desired - baseline)
        # P0 ceiling: не-owner не может выдать права СВЕРХ собственных эффективных;
        # admin / admin.* — только owner. Иначе admin.users-актор self-эскалируется.
        if not user.is_owner:
            actor_codes = set(await repo.effective_permission_codes(user.id))
            excess = [c for c in grants
                      if c == "admin" or c.startswith("admin.") or c not in actor_codes]
            if excess:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    tr(
                        "Нельзя выдать права сверх собственных: {permissions}",
                        current_locale(), permissions=", ".join(excess),
                    ),
                )
        rows = [(c, "grant") for c in grants] + [(c, "deny") for c in denies]
        # Зачищаем только то, чем управляет сама сетка: коды вне неё (например
        # moderation.review) сетка не показывает и восстановить не может, а
        # раньше replace-all стирал их при каждом сохранении.
        await repo.set_user_grants(
            user_id, rows, user.id, manage_codes=set(_GRID_MANAGEABLE_CODES),
        )
        await db.commit()

        return await self.get_user(user_id, db, user)

    async def create_user(
        self, payload: UserCreatePayload, db: AsyncSession, user: User
    ) -> UserDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        if await repo.find_user_by_email(payload.email.lower()):
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                "User with this email already exists",
            )
        try:
            validate_password_policy(payload.password)
        except Exception as e:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(e))

        roles: list = []
        if payload.role_codes:
            roles = list(await repo.lookup_roles(payload.role_codes))
            missing = set(payload.role_codes) - {r.code for r in roles}
            if missing:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Unknown role codes: {sorted(missing)}",
                )
            # P0 ceiling: не-owner не создаёт пользователя с ролью 'admin' или с
            # правами сверх собственных эффективных.
            if "admin" in payload.role_codes and not user.is_owner:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "Only an owner can create a user with the 'admin' role.",
                )
            if not user.is_owner:
                if "admin" in payload.role_codes:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        "Только owner может создать пользователя с ролью 'admin'.",
                    )
                actor_codes = set(await repo.effective_permission_codes(user.id))
                grant_perms: set[str] = set()
                for r in roles:
                    grant_perms |= set(await repo.role_permission_codes(r.id))
                excess = [c for c in sorted(grant_perms)
                          if c == "admin" or c.startswith("admin.") or c not in actor_codes]
                if excess:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        tr(
                            "Назначаемые роли несут права сверх ваших: {permissions}",
                            current_locale(), permissions=", ".join(excess),
                        ),
                    )
        # P0 ceiling: не выдать создаваемому пользователю company/sector-scope сверх своего
        await self._ensure_assigned_scope_within_ceiling(
            db, user,
            organization_id=payload.organization_id,
            allowed_sectors=payload.allowed_sectors,
        )
        scoped_memberships = await self._resolve_create_group_memberships(
            db, repo, payload, user,
        )
        new_user = User(
            email=payload.email.lower(),
            full_name=payload.full_name,
            department=payload.department,
            job_title=payload.job_title,
            password_hash=hash_password(payload.password),
            must_change_password=payload.must_change_password,
            is_active=True, is_owner=False,
            organization_id=payload.organization_id,
            allowed_sectors=payload.allowed_sectors or None,
            moderator_ids=[str(x) for x in (payload.moderator_ids or [])] or None,
            moderated_sector_codes=payload.moderated_sector_codes or None,
        )
        repo.add(new_user)
        await repo.flush()
        for r in roles:
            await repo.assign_user_role(new_user.id, r.id)
        for group, role in scoped_memberships:
            repo.add(UserGroupRole(
                user_id=new_user.id,
                group_id=group.id,
                role_id=role.id,
            ))
        if payload.moderated_sector_codes:
            await _ensure_review_permission(db, new_user.id)
        if payload.moderator_ids:
            for mid in payload.moderator_ids:
                await _ensure_review_permission(db, mid)
        await db.commit()

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.create",
            entity_type="user", entity_id=str(new_user.id),
            notes=(
                f"email={payload.email}, roles={payload.role_codes}, "
                # Голое количество не даёт проследить, ДОСТУП К КАКИМ компаниям выдан
                # при создании (rbac.user.membership.upsert пишет group+role) —
                # пишем состав, иначе выдача доступа к 20 компаниям в аудите = «20».
                f"group_memberships=["
                + ", ".join(f"{g.code}:{r.code}" for g, r in scoped_memberships)
                + "]"
            ),
        )
        await db.commit()

        # Письмо-приглашение с временным паролем. send_invite_email возвращает
        # False, если SMTP выключен ИЛИ отправка упала → пробрасываем это в ответ,
        # чтобы UI показал предупреждение и temp-пароль для ручной передачи.
        invite_sent = False
        try:
            from app.core.i18n import locale_of_user
            from app.services.email.service import send_invite_email
            invite_sent = await send_invite_email(
                to=new_user.email, full_name=new_user.full_name,
                temp_password=payload.password,
                must_change=payload.must_change_password,
                locale=locale_of_user(new_user),
            )
        except Exception:  # noqa: BLE001
            invite_sent = False

        result = await self.get_user(new_user.id, db, user)
        result.invite_email_sent = invite_sent
        return result

    async def update_user(
        self,
        user_id: UUID,
        payload: UserUpdatePayload,
        db: AsyncSession,
        user: User,
    ) -> UserDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        if u.id == user.id and payload.is_active is False:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "You cannot deactivate your own account.",
            )
        if payload.is_active is False:
            _ensure_can_manage_target(user, u)   # P0: не-owner не деактивирует OWNER (lockout)
        changes: list[str] = []
        must_revoke = False
        if payload.full_name is not None and payload.full_name != u.full_name:
            u.full_name = payload.full_name; changes.append(f"full_name={payload.full_name!r}")
        if payload.department is not None and payload.department != u.department:
            u.department = payload.department; changes.append(f"department={payload.department!r}")
        if payload.job_title is not None and payload.job_title != u.job_title:
            u.job_title = payload.job_title; changes.append(f"job_title={payload.job_title!r}")
        if payload.is_active is not None and payload.is_active != u.is_active:
            u.is_active = payload.is_active
            changes.append(f"is_active={payload.is_active}")
            if payload.is_active is False:
                must_revoke = True
        if payload.organization_id is not None and payload.organization_id != u.organization_id:
            # P0 ceiling: не назначить компанию вне доступа актора (в т.ч. себе)
            await self._ensure_assigned_scope_within_ceiling(
                db, user, organization_id=payload.organization_id)
            u.organization_id = payload.organization_id
            changes.append(f"organization_id={payload.organization_id}")
        if payload.allowed_companies is not None:
            changes.append("allowed_companies=<ignored: use groups endpoint>")
        if payload.allowed_sectors is not None:
            new_sectors = payload.allowed_sectors or None
            if (u.allowed_sectors or None) != new_sectors:
                # P0 ceiling: не выдать секторы вне собственных (в т.ч. себе)
                await self._ensure_assigned_scope_within_ceiling(
                    db, user, allowed_sectors=new_sectors)
                u.allowed_sectors = new_sectors
                changes.append(f"allowed_sectors={payload.allowed_sectors}")
        if payload.moderator_ids is not None:
            new_mods = [str(x) for x in payload.moderator_ids] or None
            if (u.moderator_ids or None) != new_mods:
                u.moderator_ids = new_mods
                changes.append(f"moderator_ids={new_mods}")
                for mid in (payload.moderator_ids or []):
                    await _ensure_review_permission(db, mid)
        if payload.moderated_sector_codes is not None:
            new_sec = payload.moderated_sector_codes or None
            if (u.moderated_sector_codes or None) != new_sec:
                u.moderated_sector_codes = new_sec
                changes.append(f"moderated_sector_codes={new_sec}")
                if new_sec:
                    await _ensure_review_permission(db, u.id)
        if payload.role_codes is not None:
            roles = list(await repo.lookup_roles(payload.role_codes))
            missing = set(payload.role_codes) - {r.code for r in roles}
            if missing:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Unknown role codes: {sorted(missing)}",
                )
            old = sorted(await repo.list_user_role_codes(u.id))
            new = sorted(payload.role_codes)
            if old != new:
                added = set(new) - set(old)
                # P0: роль 'admin' = супер-админ (глобальный bypass) — назначить может только owner
                if "admin" in added and not user.is_owner:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        "Только owner может назначить роль 'admin' (супер-администратор).",
                    )
                # P0: не-owner не может менять СВОИ роли (самоэскалация через свой аккаунт)
                if u.id == user.id and added and not user.is_owner:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        "Нельзя изменять собственные роли — попросите owner или другого администратора.",
                    )
                # P0 ceiling: назначаемые роли не должны нести права сверх эффективных прав актора
                if not user.is_owner and added:
                    actor_codes = set(await repo.effective_permission_codes(user.id))
                    add_role_perms: set[str] = set()
                    for r in roles:
                        if r.code in added:
                            add_role_perms |= set(await repo.role_permission_codes(r.id))
                    excess = [c for c in sorted(add_role_perms)
                              if c == "admin" or c.startswith("admin.") or c not in actor_codes]
                    if excess:
                        raise HTTPException(
                            http_status.HTTP_403_FORBIDDEN,
                            tr(
                                "Роль несёт права сверх ваших: {permissions}",
                                current_locale(), permissions=", ".join(excess),
                            ),
                        )
                # H5: prevent admin from removing own admin role
                if (
                    u.id == user.id and not user.is_owner
                    and "admin" in old and "admin" not in new
                ):
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        "Нельзя снять с себя роль 'admin'. Попросите другого администратора или owner.",
                    )
                # M5: prevent removing last admin
                if (
                    "admin" in old and "admin" not in new and not user.is_owner
                ):
                    other_admins = await repo.count_other_active_admins(u.id)
                    if other_admins == 0:
                        raise HTTPException(
                            http_status.HTTP_409_CONFLICT,
                            "Нельзя удалить роль 'admin': этот пользователь — последний "
                            "активный администратор платформы. Сначала назначьте другого.",
                        )
                await repo.clear_user_roles(u.id)
                for r in roles:
                    await repo.assign_user_role(u.id, r.id)
                changes.append(f"roles={payload.role_codes}")
                must_revoke = True

        revoked_count = 0
        if must_revoke:
            revoked_count = await revoke_all_sessions(db, u.id)
            if revoked_count:
                changes.append(f"sessions_revoked={revoked_count}")

        await db.commit()
        if changes:
            await append_audit_entry(
                db, actor_id=str(user.id), actor_email=user.email,
                action="rbac.user.update",
                entity_type="user", entity_id=str(u.id),
                notes=", ".join(changes)[:500],
            )
            await db.commit()
        return await self.get_user(u.id, db, user)

    async def upsert_user_membership(
        self,
        user_id: UUID, group_id: UUID,
        payload: UserMembershipUpsert,
        db: AsyncSession, user: User,
    ) -> UserDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        g = await repo.get_group(group_id)
        if not g:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")
        role = await repo.get_role_by_code(payload.role_code)
        if not role:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown role code: {payload.role_code!r}",
            )
        existing = await repo.get_membership(user_id, group_id)
        if existing and existing.role_id == role.id:
            return await self.get_user(user_id, db, user)   # no-op, роль не меняется

        # P0 (аудит RBAC): membership — единственный оставшийся путь назначения
        # роли БЕЗ privilege-ceiling. Без этих guard'ов scoped-админ с admin.users
        # создаёт группу и самоназначает роль 'admin' (или роль с правами сверх
        # своих) → получает admin.* в обход упрочнённых update_user/create_user.
        # Зеркалим ceiling из update_user.
        _ensure_can_manage_target(user, u)   # не-owner не трогает OWNER-аккаунт
        if role.code == "admin" and not user.is_owner:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Only an owner can assign the 'admin' role.",
            )
        if not user.is_owner:
            # роль 'admin' = супер-админ (глобальный bypass) — назначает только owner
            if role.code == "admin":
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "Только owner может назначить роль 'admin' (супер-администратор).",
                )
            # нельзя менять собственные членства/роли (самоэскалация через свой аккаунт)
            if u.id == user.id:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "Нельзя изменять собственные членства — попросите owner или другого администратора.",
                )
            # ceiling: назначаемая роль не несёт прав сверх эффективных прав актора
            actor_codes = set(await repo.effective_permission_codes(user.id))
            role_perms = set(await repo.role_permission_codes(role.id))
            excess = [c for c in sorted(role_perms)
                      if c == "admin" or c.startswith("admin.") or c not in actor_codes]
            if excess:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    tr(
                        "Роль несёт права сверх ваших: {permissions}",
                        current_locale(), permissions=", ".join(excess),
                    ),
                )
        # Scope/гранты самой группы (company_id + GroupPermissionGrant) — не покрыто role-ceiling
        await self._ensure_group_membership_within_ceiling(db, repo, user, g)

        if existing:
            existing.role_id = role.id
        else:
            repo.add(UserGroupRole(
                user_id=user_id, group_id=group_id, role_id=role.id,
            ))
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.membership.upsert",
            entity_type="user", entity_id=str(user_id),
            notes=f"group={g.code}, role={role.code}",
        )
        await db.commit()
        return await self.get_user(user_id, db, user)

    async def remove_user_membership(
        self, user_id: UUID, group_id: UUID,
        db: AsyncSession, user: User,
    ) -> None:
        await _require_admin(db, user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        rowcount = await repo.delete_membership(user_id, group_id)
        await db.commit()
        if rowcount:
            await append_audit_entry(
                db, actor_id=str(user.id), actor_email=user.email,
                action="rbac.user.membership.remove",
                entity_type="user", entity_id=str(user_id),
                notes=f"group_id={group_id}",
            )
            await db.commit()

    async def force_password_change(
        self, user_id: UUID, db: AsyncSession, user: User
    ) -> None:
        await _require_admin(db, user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        if u.is_owner and not user.is_owner:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Only an owner can force-change another owner",
            )
        u.must_change_password = True
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.force_password_change",
            entity_type="user", entity_id=str(u.id),
            notes=f"target={u.email}",
        )
        await db.commit()

    async def reset_password(
        self, user_id: UUID, payload: PasswordResetPayload,
        db: AsyncSession, user: User,
    ) -> None:
        await _require_admin(db, user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        _ensure_can_manage_target(user, u)   # P0: не дать не-owner сбросить пароль OWNER
        try:
            validate_password_policy(payload.new_password)
        except Exception as e:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(e))
        u.password_hash = hash_password(payload.new_password)
        u.must_change_password = payload.must_change_password
        revoked = await revoke_all_sessions(db, u.id)
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.reset_password",
            entity_type="user", entity_id=str(u.id),
            notes=f"target={u.email}, force_change={payload.must_change_password}, sessions_revoked={revoked}",
        )
        await db.commit()

    async def deactivate_user(
        self, user_id: UUID, db: AsyncSession, user: User
    ) -> None:
        await _require_admin(db, user)
        if user_id == user.id:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "You cannot deactivate your own account.",
            )
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        _ensure_can_manage_target(user, u)   # P0: не дать не-owner деактивировать OWNER
        u.is_active = False
        revoked = await revoke_all_sessions(db, u.id)
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.deactivate",
            entity_type="user", entity_id=str(u.id),
            notes=f"target={u.email}, sessions_revoked={revoked}",
        )

    async def reactivate_user(
        self, user_id: UUID, db: AsyncSession, user: User
    ) -> "UserDetail":
        """Разблокировать аккаунт: снять деактивацию И снять lockout по
        неудачным попыткам входа. Доступно admin/owner. Идемпотентно."""
        await _require_admin(db, user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        was_inactive = not u.is_active
        was_locked = u.locked_until is not None
        u.is_active = True
        u.locked_until = None
        u.failed_login_attempts = 0
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.reactivate",
            entity_type="user", entity_id=str(u.id),
            notes=f"target={u.email}, was_inactive={was_inactive}, was_locked={was_locked}",
        )
        return await self.get_user(user_id, db, user)

    async def set_owner(
        self, user_id: UUID, is_owner: bool, db: AsyncSession, user: User
    ) -> "UserDetail":
        """Назначить/снять статус OWNER. Только текущий OWNER может это делать."""
        _require_owner(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        # Нельзя снять статус с самого себя (защита от случайной потери
        # единственного владельца) — снять может только другой OWNER.
        if not is_owner and user_id == user.id:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "Нельзя снять статус OWNER с самого себя",
            )
        u.is_owner = bool(is_owner)
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.set_owner",
            entity_type="user", entity_id=str(u.id),
            notes=f"target={u.email}, is_owner={u.is_owner}",
        )
        return await self.get_user(user_id, db, user)

    async def permanently_delete_user(
        self, user_id: UUID, db: AsyncSession, user: User
    ) -> None:
        await _require_admin(db, user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Чтение по прямому UUID тоже ограничено областью актора.
        await _ensure_target_in_scope(db, user, u)
        if u.id == user.id:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "You cannot delete your own account.",
            )
        if getattr(u, "is_owner", False):
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "Cannot permanently delete the platform owner.",
            )
        target_email = u.email
        target_id = str(u.id)
        revoked = await revoke_all_sessions(db, u.id)
        await db.flush()
        await db.delete(u)
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                tr(
                    "Не удалось удалить пользователя: {error_type}. Возможно, есть связанные данные без CASCADE.",
                    current_locale(), error_type=e.__class__.__name__,
                ),
            )
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.delete_permanent",
            entity_type="user", entity_id=target_id,
            notes=f"target={target_email}, sessions_revoked={revoked}",
        )
        await db.commit()

    async def create_preview_token(
        self, user_id: UUID, db: AsyncSession, user: User
    ) -> PreviewTokenResponse:
        await _require_admin(db, user)
        repo = self._repo(db)
        target = await repo.get_user_with_roles_perms(user_id)
        if not target:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        # Per-company scope: company-scoped admin.users НЕ может импертонировать юзера
        # чужой компании (горизонтальная эскалация). Только здесь можно проверить —
        # exchange без актора. Зеркалит get_user/update_user (404 вне скоупа).
        await _ensure_target_in_scope(db, user, target)
        if str(target.id) == str(user.id):
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, "Cannot impersonate yourself"
            )
        if not target.is_active:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, "Cannot impersonate inactive user"
            )
        if target.is_owner:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "Cannot impersonate the platform owner"
            )
        if await has_effective_permission(db, target, "admin.users"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot impersonate a user with admin.users privilege",
            )
        # Отдаём КОРОТКОживущий тикет обмена (60с), а НЕ 30-мин access-токен: токен
        # в URL новой вкладки утекал в nginx-логи/history/Referer (P1). Вкладка
        # меняет тикет на токен через preview-exchange (тело ответа, не URL).
        from app.core.jwt import create_preview_ticket
        ticket = create_preview_ticket(
            subject=str(target.id),
            extra_claims={
                "impersonator_id": str(user.id),
                "impersonator_email": user.email,
            },
        )
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.impersonate",
            entity_type="user", entity_id=str(target.id),
            notes=f"target_email={target.email}",
        )
        await db.commit()
        return PreviewTokenResponse(
            preview_ticket=ticket,
            target_user_id=target.id,
            target_email=target.email,
        )

    async def exchange_preview_ticket(
        self, ticket: str, db: AsyncSession
    ) -> "PreviewExchangeResponse":
        """Обменять preview-тикет на 30-мин impersonation-токен. БЕЗ auth —
        подписанный тикет сам credential (как ws_ticket). Тикет 60с/type-specific;
        цель ПЕРЕПРОВЕРЯется (stale-guard): всё ещё активна, не OWNER, без
        admin.users — иначе устаревший тикет мог бы импертонировать повысившегося."""
        from app.core.jwt import create_access_token, decode_token
        try:
            payload = decode_token(ticket, expected_type="preview_ticket")
        except Exception:
            raise HTTPException(
                http_status.HTTP_401_UNAUTHORIZED,
                "Preview-тикет недействителен или истёк",
            )
        target_id = payload.get("sub")
        imp_id = payload.get("impersonator_id")
        imp_email = payload.get("impersonator_email")
        if not target_id or not imp_id:
            raise HTTPException(http_status.HTTP_401_UNAUTHORIZED, "Некорректный тикет")

        target = await self._repo(db).get_user_with_roles_perms(UUID(str(target_id)))
        if not target or not target.is_active or target.is_owner:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "Пользователь больше недоступен для входа"
            )
        if await has_effective_permission(db, target, "admin.users"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Пользователь получил право admin.users — вход невозможен",
            )

        expires_minutes = 30
        token = create_access_token(
            subject=str(target.id),
            expires_minutes=expires_minutes,
            extra_claims={
                "impersonator_id": str(imp_id),
                "impersonator_email": imp_email,
                "is_preview": True,
            },
        )
        return PreviewExchangeResponse(
            access_token=token,
            expires_in=expires_minutes * 60,
            target_email=target.email,
        )

    # ─── Groups ───────────────────────────────────────────────────

    async def list_groups(self, db: AsyncSession, user: User) -> list[GroupBrief]:
        await _require_admin(db, user)
        rows = await self._repo(db).list_groups()
        # Область: администратор КОМПАНИИ видит только группы своих компаний.
        # Группы без company_id (общеплатформенные) остаются видимыми — они не
        # раскрывают чужую организацию, а членство в них всё равно ограничено
        # потолком области при попытке кого-то туда добавить.
        from app.core.access import allowed_company_ids, has_unrestricted_view
        if not (user.is_owner or is_super_admin(user) or has_unrestricted_view(user)):
            allowed = await allowed_company_ids(db, user)
            if allowed is not None:
                allowed_set = {str(x) for x in allowed}
                rows = [
                    g for g in rows
                    if getattr(g, "company_id", None) is None
                    or str(g.company_id) in allowed_set
                ]
        return [await self._group_to_brief(db, g) for g in rows]

    async def get_group(
        self, group_id: UUID, db: AsyncSession, user: User
    ) -> GroupDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        g = await repo.get_group(group_id)
        if not g:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")
        base = await self._group_to_brief(db, g)
        grants = list(await repo.list_group_grants(group_id))
        member_rows = await repo.list_group_members_with_role(group_id)
        return GroupDetail(
            **base.model_dump(),
            members=[
                GroupMember(
                    id=r.id, email=r.email, full_name=r.full_name,
                    role_code=r.code, role_name=r.name_ru,
                )
                for r in member_rows
            ],
            permissions=[
                GroupPermission(
                    code=p.permission_code,
                    grant_type=getattr(p, "grant_type", "grant") or "grant",
                    expires_at=getattr(p, "expires_at", None),
                    scope_companies=getattr(p, "scope_companies", None) or None,
                )
                for p in grants
            ],
            roles=[],
        )

    async def create_group(
        self, payload: GroupCreatePayload, db: AsyncSession, user: User
    ) -> GroupBrief:
        await _require_admin(db, user)
        repo = self._repo(db)
        if await repo.get_group_by_code(payload.code):
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                f"Group with code '{payload.code}' already exists",
            )
        g = Group(**payload.model_dump())
        repo.add(g)
        await repo.flush()
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.group.create",
            entity_type="group", entity_id=str(g.id),
            notes=f"code={g.code}, name={g.name}",
        )
        await db.commit()
        return await self._group_to_brief(db, g)

    async def update_group(
        self, group_id: UUID, payload: GroupUpdatePayload,
        db: AsyncSession, user: User,
    ) -> GroupBrief:
        await _require_admin(db, user)
        repo = self._repo(db)
        g = await repo.get_group(group_id)
        if not g:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")
        fields = payload.model_dump(exclude_unset=True)
        # P0 (аудит RBAC): смена company_id перепривязывает группу к другой компании
        # → все её участники (в т.ч. сам актор, если он в группе) получают доступ к
        # этой компании через allowed_company_ids. Не-owner не может увести группу в
        # компанию вне своего доступа (горизонтальная эскалация scope).
        if ("company_id" in fields and fields["company_id"] is not None
                and fields["company_id"] != g.company_id
                and not user.is_owner and not is_super_admin(user)):
            from app.core.access import allowed_company_ids
            allowed = await allowed_company_ids(db, user)
            if allowed is not None and str(fields["company_id"]) not in {str(x) for x in allowed}:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "Нельзя привязать группу к компании вне вашего доступа.",
                )
        for k, v in fields.items():
            setattr(g, k, v)
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.group.update",
            entity_type="group", entity_id=str(g.id),
            notes=f"code={g.code}",
        )
        await db.commit()
        return await self._group_to_brief(db, g)

    async def delete_group(
        self, group_id: UUID, db: AsyncSession, user: User
    ) -> None:
        await _require_admin(db, user)
        repo = self._repo(db)
        g = await repo.get_group(group_id)
        if not g:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")
        code, gid = g.code, str(g.id)
        await repo.delete(g)
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.group.delete",
            entity_type="group", entity_id=gid,
            notes=f"code={code}",
        )
        await db.commit()

    async def set_group_members(
        self, group_id: UUID, payload: GroupMembersUpdate,
        db: AsyncSession, user: User,
    ) -> GroupDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        g = await repo.get_group(group_id)
        if not g:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")

        assignments: list[tuple] = []
        if payload.members is not None:
            for m in payload.members:
                assignments.append((m.user_id, m.role_code))
        elif payload.user_ids is not None:
            for uid in payload.user_ids:
                assignments.append((uid, "viewer"))
        else:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "Provide either 'members' or 'user_ids'",
            )

        user_ids = [uid for uid, _ in assignments]
        role_codes = list({rc for _, rc in assignments})
        found_ids = await repo.found_user_ids(user_ids)
        unknown_users = [str(uid) for uid in user_ids if uid not in found_ids]
        if unknown_users:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown user_ids: {unknown_users}",
            )
        role_id_by_code = await repo.lookup_roles_id_by_code(role_codes)
        unknown_roles = [rc for rc in role_codes if rc not in role_id_by_code]
        if unknown_roles:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown role codes: {sorted(unknown_roles)}",
            )
        if "admin" in role_codes and not user.is_owner:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Only an owner can assign the 'admin' role.",
            )

        # P0 (аудит RBAC): та же дыра, что в upsert_user_membership — set_group_members
        # тоже пишет UserGroupRole без privilege-ceiling. Без этого scoped-админ с
        # admin.users создаёт группу и выдаёт себе/сообщнику роль 'admin' (или роль с
        # правами сверх своих) → admin.* глобально (роль-права эффективны без scope).
        # Ceiling'а достаточно: он ограничивает роль правами актора, поэтому GAIN
        # невозможен даже для self — блокировать себя целиком (как в upsert) не нужно,
        # иначе сломается штатная правка ростера группы, где актор сам в участниках.
        if not user.is_owner:
            actor_codes = set(await repo.effective_permission_codes(user.id))
            role_perms_cache: dict[str, set[str]] = {}
            for uid, rc in assignments:
                if rc == "admin":
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        "Только owner может назначить роль 'admin' (супер-администратор).",
                    )
                target = await repo.get_user_by_id(uid)
                if target is not None:
                    _ensure_can_manage_target(user, target)   # не-owner не трогает OWNER
                if rc not in role_perms_cache:
                    role_perms_cache[rc] = set(
                        await repo.role_permission_codes(role_id_by_code[rc])
                    )
                excess = [c for c in sorted(role_perms_cache[rc])
                          if c == "admin" or c.startswith("admin.") or c not in actor_codes]
                if excess:
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        tr(
                            "Роль '{role}' несёт права сверх ваших: {permissions}",
                            current_locale(), role=rc, permissions=", ".join(excess),
                        ),
                    )
            # Scope/гранты самой группы (company_id + GroupPermissionGrant) — не покрыто
            # role-ceiling: закрывает горизонтальную (выход из своей компании через
            # Group.company_id) и вертикальную (жирный grant) self-эскалацию, без
            # блокировки штатной правки ростера группы своей компании.
            await self._ensure_group_membership_within_ceiling(db, repo, user, g)

        await repo.clear_group_members(group_id)
        for uid, rc in assignments:
            repo.add(UserGroupRole(
                user_id=uid, group_id=group_id, role_id=role_id_by_code[rc],
            ))
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.group.set_members",
            entity_type="group", entity_id=str(g.id),
            notes=f"code={g.code}, members={len(assignments)}",
        )
        await db.commit()
        return await self.get_group(group_id, db, user)

    async def set_group_permissions(
        self, group_id: UUID, payload: GroupPermissionsUpdate,
        db: AsyncSession, user: User,
    ) -> GroupDetail:
        await _require_admin(db, user)
        repo = self._repo(db)
        g = await repo.get_group(group_id)
        if not g:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")
        # Расширенный формат (grants) имеет приоритет над плоским permission_codes.
        if payload.grants is not None:
            items = payload.grants
            codes = list(dict.fromkeys(i.permission_code for i in items))
        else:
            items = [
                GroupGrantItem(permission_code=c, grant_type="grant")
                for c in dict.fromkeys(payload.permission_codes)
            ]
            codes = [i.permission_code for i in items]
        if codes:
            found = await repo.permission_codes_exist(codes)
            missing = set(codes) - found
            if missing:
                # Разрежённый каталог: игнорируем несуществующие коды (вместо 400),
                # гранты — только по валидным. См. create_role.
                log.warning(
                    "[rbac] set_group_grants: ignoring unknown permission codes: %s",
                    sorted(missing),
                )
                items = [i for i in items if i.permission_code in found]
        # P0 ceiling: не-owner не выдаёт группе права/scope сверх собственных —
        # иначе self-service обход per-company scope (grant всех 22 компаний +
        # добавить себя в группу). Deny (понижение) не ограничиваем.
        if not user.is_owner:
            from app.core.access import allowed_company_ids
            actor_codes = set(await repo.effective_permission_codes(user.id))
            allowed = await allowed_company_ids(db, user)  # None = все компании
            allowed_str = None if allowed is None else {str(x) for x in allowed}
            for it in items:
                if it.grant_type != "deny":
                    c = it.permission_code
                    if c == "admin" or c.startswith("admin.") or c not in actor_codes:
                        raise HTTPException(
                            http_status.HTTP_403_FORBIDDEN,
                            tr(
                                "Нельзя выдать группе право сверх собственных: {permission}",
                                current_locale(), permission=c,
                            ),
                        )
                if it.scope_companies and allowed_str is not None:
                    excess = {str(x) for x in it.scope_companies} - allowed_str
                    if excess:
                        raise HTTPException(
                            http_status.HTTP_403_FORBIDDEN,
                            tr(
                                "scope_companies вне вашего доступа: {companies}",
                                current_locale(), companies=", ".join(sorted(excess)),
                            ),
                        )
        await repo.clear_group_grants(group_id)
        for it in items:
            repo.add(GroupPermissionGrant(
                group_id=group_id,
                permission_code=it.permission_code,
                grant_type=("deny" if it.grant_type == "deny" else "grant"),
                expires_at=it.expires_at,
                scope_companies=it.scope_companies or None,
                granted_by_id=user.id,
            ))
        await db.commit()
        n_deny = sum(1 for i in items if i.grant_type == "deny")
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.group.set_permissions",
            entity_type="group", entity_id=str(g.id),
            notes=f"code={g.code}, grants={len(items)}, deny={n_deny}",
        )
        await db.commit()
        return await self.get_group(group_id, db, user)
