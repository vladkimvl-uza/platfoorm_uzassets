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
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.password import hash_password, validate_password_policy
from app.core.security import _has_permission, has_effective_permission
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
    GroupMember,
    GroupMembersUpdate,
    GroupGrantItem,
    GroupPermission,
    GroupPermissionsUpdate,
    GroupUpdatePayload,
    PasswordResetPayload,
    PermissionBrief,
    PreviewTokenResponse,
    RBACOverview,
    RoleBrief,
    RoleCreatePayload,
    RoleDetail,
    RolePermissionsUpdate,
    RoleUpdatePayload,
    UserBrief,
    UserCreatePayload,
    UserDetail,
    UserGroupMembership,
    UserListResponse,
    UserMembershipUpsert,
    UserUpdatePayload,
)
from app.services.auth_service import revoke_all_sessions

log = logging.getLogger(__name__)

# Сетка «Доступ к модулям» (frontend MODULE_REGISTRY, 16 модулей) умеет
# представлять ТОЛЬКО коды вида {module}.{view|edit|export|manage}. Любое
# право вне этого множества (companies.view, sectors.view, users.view,
# ai.chat, investment.view, procurement.request.view, tasks.create/assign,
# treasury.view, finmodel.view, announcements.view, …) сетка не видит, поэтому
# set_user_permissions НЕ имеет права автоматически денайнить такие права —
# иначе сохранение сетки молча отбирает у пользователя доступ роли.
_GRID_MODULE_CODES = (
    "dashboard", "bp", "kpi", "financials", "credit", "invest", "procurement",
    "esg", "governance", "ratings", "procurement_analysis", "consultants",
    "tasks", "reports", "monitoring", "ai", "admin",
)
_GRID_PERMISSION_SUFFIXES = ("view", "edit", "export", "manage")
_GRID_MANAGEABLE_CODES = frozenset(
    f"{m}.{s}" for m in _GRID_MODULE_CODES for s in _GRID_PERMISSION_SUFFIXES
)


def _require_admin(user: User) -> None:
    if user.is_owner or _has_permission(user, "admin.users"):
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
        self, db: AsyncSession, u: User, company_names: Optional[dict] = None,
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
            last_login_at=u.last_login_at,
            last_seen_at=getattr(u, "last_seen_at", None),
            locked_until=u.locked_until,
            created_at=u.created_at,
            role_codes=[r.code for r in rows],
            role_names=[r.name_ru for r in rows],
            organization_id=u.organization_id,
            company=(company_names or {}).get(u.organization_id),
            allowed_companies=None,  # Pack 147: per-group memberships
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

    # ─── Overview ─────────────────────────────────────────────────

    async def overview(self, db: AsyncSession, user: User) -> RBACOverview:
        _require_admin(user)
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
        _require_admin(user)
        rows = await self._repo(db).list_permissions()
        return [PermissionBrief.model_validate(p) for p in rows]

    # ─── Roles ────────────────────────────────────────────────────

    async def list_roles(self, db: AsyncSession, user: User) -> list[RoleBrief]:
        _require_admin(user)
        out: list[RoleBrief] = []
        for r in await self._repo(db).list_roles_with_perm_count():
            rb = RoleBrief.model_validate(r.Role)
            rb.permission_count = r.perm_count or 0
            out.append(rb)
        return out

    async def get_role(
        self, code: str, db: AsyncSession, user: User
    ) -> RoleDetail:
        _require_admin(user)
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
        _require_admin(user)
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
        _require_admin(user)
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
        _require_admin(user)
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
        _require_admin(user)
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
        _require_admin(user)
        repo = self._repo(db)
        q = repo.base_user_query()
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
        items = [await self._hydrate_user(db, u, _company_names) for u in users]
        return UserListResponse(items=items, total=total)

    async def get_user(
        self, user_id: UUID, db: AsyncSession, user: User
    ) -> UserDetail:
        _require_admin(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")

        base = await self._hydrate_user(db, u)
        perms = await repo.effective_permission_codes(u.id)
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
            group_memberships=memberships,
            is_external=bool(getattr(u, "is_external", False)),
            bypass_moderation=bool(getattr(u, "bypass_moderation", False)),
            external_org_name=getattr(u, "external_org_name", None),
            allowed_sectors=getattr(u, "allowed_sectors", None) or None,
        )

    async def set_user_permissions(
        self, user_id: UUID, payload: "RolePermissionsUpdate", db: AsyncSession, user: User,
    ) -> UserDetail:
        """Прямое per-user редактирование доступа к модулям (OWNER/ADMIN).

        Сетка «Доступ к модулям» → permission_codes. Сохраняем как overlay:
        grant на то, чего нет в роли (повышение), deny на то, что роль даёт,
        но сетка убирает (понижение). Так effective == выбранная сетка.
        """
        _require_admin(user)
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
        baseline = await repo.base_permission_codes(user_id)

        # КРИТИЧНО: сетка «Доступ к модулям» оперирует только 16 модулями и
        # испускает коды вида {module}.{view|edit|export|manage}. Права роли,
        # которые сетка не способна представить (companies.view, sectors.view,
        # users.view, ai.chat, investment.view, procurement.request.view,
        # tasks.create/assign, treasury.view, …), НЕ должны автоматически
        # уходить в deny — иначе сохранение сетки молча отбирает у пользователя
        # доступ, который даёт роль (например, список компаний → 403).
        # Поэтому deny ограничиваем grid-представимыми кодами; всё вне сетки
        # остаётся за ролью нетронутым.
        denies = sorted((baseline - desired) & _GRID_MANAGEABLE_CODES)
        grants = sorted(desired - baseline)
        rows = [(c, "grant") for c in grants] + [(c, "deny") for c in denies]
        await repo.set_user_grants(user_id, rows, user.id)
        await db.commit()

        return await self.get_user(user_id, db, user)

    async def create_user(
        self, payload: UserCreatePayload, db: AsyncSession, user: User
    ) -> UserDetail:
        _require_admin(user)
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
        )
        repo.add(new_user)
        await repo.flush()
        for r in roles:
            await repo.assign_user_role(new_user.id, r.id)
        await db.commit()

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.create",
            entity_type="user", entity_id=str(new_user.id),
            notes=f"email={payload.email}, roles={payload.role_codes}",
        )
        await db.commit()

        # Письмо-приглашение с временным паролем. send_invite_email возвращает
        # False, если SMTP выключен ИЛИ отправка упала → пробрасываем это в ответ,
        # чтобы UI показал предупреждение и temp-пароль для ручной передачи.
        invite_sent = False
        try:
            from app.services.email.service import send_invite_email
            invite_sent = await send_invite_email(
                to=new_user.email, full_name=new_user.full_name,
                temp_password=payload.password,
                must_change=payload.must_change_password,
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
        _require_admin(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
        if u.id == user.id and payload.is_active is False:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "You cannot deactivate your own account.",
            )
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
            u.organization_id = payload.organization_id
            changes.append(f"organization_id={payload.organization_id}")
        if payload.allowed_companies is not None:
            changes.append("allowed_companies=<ignored: use groups endpoint>")
        if payload.allowed_sectors is not None:
            new_sectors = payload.allowed_sectors or None
            if (u.allowed_sectors or None) != new_sectors:
                u.allowed_sectors = new_sectors
                changes.append(f"allowed_sectors={payload.allowed_sectors}")
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
        _require_admin(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
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
        if existing:
            if existing.role_id == role.id:
                return await self.get_user(user_id, db, user)
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
        _require_admin(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
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
        _require_admin(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
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
        _require_admin(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
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
        _require_admin(user)
        if user_id == user.id:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "You cannot deactivate your own account.",
            )
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
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
        _require_admin(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
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
        _require_admin(user)
        repo = self._repo(db)
        u = await repo.get_user_by_id(user_id)
        if not u:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
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
                f"Не удалось удалить пользователя: {e.__class__.__name__}. "
                "Возможно, есть связанные данные без CASCADE.",
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
        _require_admin(user)
        repo = self._repo(db)
        target = await repo.get_user_with_roles_perms(user_id)
        if not target:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
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
        from app.core.jwt import create_access_token
        expires_minutes = 30
        token = create_access_token(
            subject=str(target.id),
            expires_minutes=expires_minutes,
            extra_claims={
                "impersonator_id": str(user.id),
                "impersonator_email": user.email,
                "is_preview": True,
            },
        )
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.impersonate",
            entity_type="user", entity_id=str(target.id),
            notes=f"target_email={target.email}, duration_min={expires_minutes}",
        )
        await db.commit()
        return PreviewTokenResponse(
            access_token=token,
            expires_in=expires_minutes * 60,
            target_user_id=target.id,
            target_email=target.email,
        )

    # ─── Groups ───────────────────────────────────────────────────

    async def list_groups(self, db: AsyncSession, user: User) -> list[GroupBrief]:
        _require_admin(user)
        rows = await self._repo(db).list_groups()
        return [await self._group_to_brief(db, g) for g in rows]

    async def get_group(
        self, group_id: UUID, db: AsyncSession, user: User
    ) -> GroupDetail:
        _require_admin(user)
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
        _require_admin(user)
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
        _require_admin(user)
        repo = self._repo(db)
        g = await repo.get_group(group_id)
        if not g:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
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
        _require_admin(user)
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
        _require_admin(user)
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
        _require_admin(user)
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
