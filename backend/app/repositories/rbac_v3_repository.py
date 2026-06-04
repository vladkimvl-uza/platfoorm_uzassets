"""Persistence layer for RBAC v3.

Read-heavy: queries for users, roles, permissions, groups, grants, RBE rules.
All mutation helpers preserve the original commit-points — the service still
owns audit-chain timing.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rbac_v3 import GroupPermissionGrant, UserPermissionGrant
from app.models.user import (
    Group,
    Permission,
    Role,
    RoleByEmail,
    User,
    UserGroupRole,
    role_permission,
    user_role,
)


class RbacV3Repository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── Mutation helpers ─────────────────────────────────────────

    def add(self, obj: Any) -> None:
        self._session.add(obj)

    async def delete(self, obj: Any) -> None:
        await self._session.delete(obj)

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, obj: Any) -> None:
        await self._session.refresh(obj)

    async def execute(self, stmt):
        return await self._session.execute(stmt)

    # ─── Overview counts ──────────────────────────────────────────

    async def overview_counts(self) -> dict:
        users_total = (await self._session.execute(
            select(func.count()).select_from(User)
        )).scalar_one()
        users_active = (await self._session.execute(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )).scalar_one()
        roles_total = (await self._session.execute(
            select(func.count()).select_from(Role)
        )).scalar_one()
        perms_total = (await self._session.execute(
            select(func.count()).select_from(Permission)
        )).scalar_one()
        rbe_total = (await self._session.execute(
            select(func.count()).select_from(RoleByEmail)
        )).scalar_one()
        users_without_roles = (await self._session.execute(
            select(func.count(User.id.distinct()))
            .outerjoin(user_role, user_role.c.user_id == User.id)
            .where(User.is_active.is_(True), user_role.c.role_id.is_(None))
        )).scalar_one()
        top_rows = (await self._session.execute(
            select(Role.code, Role.name_ru, func.count(user_role.c.user_id).label("cnt"))
            .outerjoin(user_role, user_role.c.role_id == Role.id)
            .group_by(Role.id, Role.code, Role.name_ru)
            .order_by(func.count(user_role.c.user_id).desc())
            .limit(5)
        )).all()
        return {
            "users_total": users_total,
            "users_active": users_active,
            "roles_total": roles_total,
            "perms_total": perms_total,
            "rbe_total": rbe_total,
            "users_without_roles": users_without_roles,
            "top_rows": [
                {"code": r.code, "name": r.name_ru, "user_count": r.cnt}
                for r in top_rows
            ],
        }

    # ─── Permissions / Roles ──────────────────────────────────────

    async def list_permissions(self) -> Sequence[Permission]:
        return (await self._session.execute(
            select(Permission).order_by(Permission.module, Permission.action)
        )).scalars().all()

    async def list_roles_with_perm_count(self) -> Sequence[Any]:
        return (await self._session.execute(
            select(Role, func.count(role_permission.c.permission_id).label("perm_count"))
            .outerjoin(role_permission, role_permission.c.role_id == Role.id)
            .group_by(Role.id)
            .order_by(Role.sort_order, Role.code)
        )).all()

    async def get_role_by_code(self, code: str) -> Optional[Role]:
        return (await self._session.execute(
            select(Role).where(Role.code == code)
        )).scalar_one_or_none()

    async def list_role_permissions(self, role_id: UUID) -> Sequence[Permission]:
        return (await self._session.execute(
            select(Permission)
            .join(role_permission, role_permission.c.permission_id == Permission.id)
            .where(role_permission.c.role_id == role_id)
            .order_by(Permission.module, Permission.action)
        )).scalars().all()

    async def role_user_count(self, role_id: UUID) -> int:
        return int((await self._session.execute(
            select(func.count()).select_from(user_role)
            .where(user_role.c.role_id == role_id)
        )).scalar() or 0)

    async def lookup_permissions(self, codes: Sequence[str]) -> Sequence[Permission]:
        if not codes:
            return []
        return (await self._session.execute(
            select(Permission).where(Permission.code.in_(codes))
        )).scalars().all()

    async def lookup_roles(self, codes: Sequence[str]) -> Sequence[Role]:
        if not codes:
            return []
        return (await self._session.execute(
            select(Role).where(Role.code.in_(codes))
        )).scalars().all()

    async def assign_role_permission(self, role_id: UUID, perm_id: UUID) -> None:
        await self._session.execute(
            role_permission.insert().values(role_id=role_id, permission_id=perm_id)
        )

    async def clear_role_permissions(self, role_id: UUID) -> None:
        await self._session.execute(
            delete(role_permission).where(role_permission.c.role_id == role_id)
        )

    # ─── Users ────────────────────────────────────────────────────

    def base_user_query(self):
        return select(User)

    async def count_users(self, q) -> int:
        return (await self._session.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

    async def list_users(self, q) -> Sequence[User]:
        return (await self._session.execute(q)).scalars().all()

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        return (await self._session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

    async def get_user_with_roles_perms(self, user_id: UUID) -> Optional[User]:
        return (await self._session.execute(
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.id == user_id)
        )).scalar_one_or_none()

    async def find_user_by_email(self, email_lower: str) -> Optional[User]:
        return (await self._session.execute(
            select(User).where(func.lower(User.email) == email_lower)
        )).scalar_one_or_none()

    async def list_user_role_codes(self, user_id: UUID) -> list[str]:
        return list((await self._session.execute(
            select(Role.code)
            .join(user_role, user_role.c.role_id == Role.id)
            .where(user_role.c.user_id == user_id)
            .order_by(Role.sort_order)
        )).scalars().all())

    async def list_user_role_brief(self, user_id: UUID) -> Sequence[Any]:
        return (await self._session.execute(
            select(Role.code, Role.name_ru)
            .join(user_role, user_role.c.role_id == Role.id)
            .where(user_role.c.user_id == user_id)
            .order_by(Role.sort_order)
        )).all()

    async def base_permission_codes(self, user_id: UUID) -> set[str]:
        """Права из ролей + групп (БЕЗ прямых user-грантов). База для diff'а."""
        role_perms_q = (await self._session.execute(
            select(Permission.code)
            .join(role_permission, role_permission.c.permission_id == Permission.id)
            .join(user_role, user_role.c.role_id == role_permission.c.role_id)
            .where(user_role.c.user_id == user_id)
            .distinct()
        ))
        role_perms = set(role_perms_q.scalars().all())

        ugr_perms_q = (await self._session.execute(
            select(Permission.code)
            .join(role_permission, role_permission.c.permission_id == Permission.id)
            .join(UserGroupRole, UserGroupRole.role_id == role_permission.c.role_id)
            .where(UserGroupRole.user_id == user_id)
            .distinct()
        ))
        role_perms.update(ugr_perms_q.scalars().all())

        grants_rows = list((await self._session.execute(
            select(GroupPermissionGrant.permission_code, GroupPermissionGrant.grant_type)
            .join(UserGroupRole, UserGroupRole.group_id == GroupPermissionGrant.group_id)
            .where(UserGroupRole.user_id == user_id)
        )).all())
        granted = {c for c, t in grants_rows if t == "grant"}
        denied = {c for c, t in grants_rows if t == "deny"}
        return (role_perms | granted) - denied

    async def user_grant_rows(self, user_id: UUID) -> list[tuple[str, str]]:
        """Прямые user-гранты: [(permission_code, grant_type)]."""
        try:
            rows = (await self._session.execute(
                select(UserPermissionGrant.permission_code, UserPermissionGrant.grant_type)
                .where(UserPermissionGrant.user_id == user_id)
            )).all()
            return [(c, t) for c, t in rows]
        except Exception:
            return []

    async def effective_permission_codes(self, user_id: UUID) -> list[str]:
        base = await self.base_permission_codes(user_id)
        ug = await self.user_grant_rows(user_id)
        ug_grant = {c for c, t in ug if t == "grant"}
        ug_deny = {c for c, t in ug if t == "deny"}
        return sorted((base | ug_grant) - ug_deny)

    async def all_permission_codes(self) -> set[str]:
        """Все существующие коды прав (для фильтрации мусорных грантов)."""
        return set((await self._session.execute(select(Permission.code))).scalars().all())

    async def set_user_grants(self, user_id: UUID, rows: list[tuple[str, str]], granted_by: Optional[UUID]) -> None:
        """Полностью заменить прямые user-гранты (rows = [(code, grant_type)])."""
        import uuid as _uuid
        await self._session.execute(
            delete(UserPermissionGrant).where(UserPermissionGrant.user_id == user_id)
        )
        for code, gtype in rows:
            self._session.add(UserPermissionGrant(
                id=_uuid.uuid4(), user_id=user_id,
                permission_code=code, grant_type=gtype, granted_by_id=granted_by,
            ))

    async def list_user_memberships(self, user_id: UUID) -> Sequence[Any]:
        return (await self._session.execute(
            select(
                Group.id, Group.code, Group.name, Group.company_id,
                Role.code, Role.name_ru,
            )
            .join(UserGroupRole, UserGroupRole.group_id == Group.id)
            .join(Role, Role.id == UserGroupRole.role_id)
            .where(UserGroupRole.user_id == user_id)
            .order_by(Group.name)
        )).all()

    async def clear_user_roles(self, user_id: UUID) -> None:
        await self._session.execute(
            delete(user_role).where(user_role.c.user_id == user_id)
        )

    async def assign_user_role(self, user_id: UUID, role_id: UUID) -> None:
        await self._session.execute(
            user_role.insert().values(user_id=user_id, role_id=role_id)
        )

    async def count_other_active_admins(self, exclude_user_id: UUID) -> int:
        return int((await self._session.execute(
            select(func.count(User.id))
            .join(user_role, user_role.c.user_id == User.id)
            .join(Role, Role.id == user_role.c.role_id)
            .where(
                Role.code == "admin",
                User.is_active.is_(True),
                User.id != exclude_user_id,
            )
        )).scalar() or 0)

    # ─── User-group memberships ───────────────────────────────────

    async def get_membership(self, user_id: UUID, group_id: UUID) -> Optional[UserGroupRole]:
        return (await self._session.execute(
            select(UserGroupRole).where(
                UserGroupRole.user_id == user_id,
                UserGroupRole.group_id == group_id,
            )
        )).scalar_one_or_none()

    async def delete_membership(self, user_id: UUID, group_id: UUID) -> int:
        result = await self._session.execute(
            delete(UserGroupRole).where(
                UserGroupRole.user_id == user_id,
                UserGroupRole.group_id == group_id,
            )
        )
        return int(result.rowcount or 0)

    async def clear_group_members(self, group_id: UUID) -> None:
        await self._session.execute(
            delete(UserGroupRole).where(UserGroupRole.group_id == group_id)
        )

    async def found_user_ids(self, user_ids: Sequence[UUID]) -> set[UUID]:
        if not user_ids:
            return set()
        return set((await self._session.execute(
            select(User.id).where(User.id.in_(user_ids))
        )).scalars().all())

    async def lookup_roles_id_by_code(self, codes: Sequence[str]) -> dict[str, UUID]:
        if not codes:
            return {}
        rows = (await self._session.execute(
            select(Role.id, Role.code).where(Role.code.in_(codes))
        )).all()
        return {r.code: r.id for r in rows}

    # ─── Role-by-email ────────────────────────────────────────────

    async def list_rbe(self) -> Sequence[RoleByEmail]:
        return (await self._session.execute(
            select(RoleByEmail).order_by(RoleByEmail.email)
        )).scalars().all()

    async def get_rbe_for_email(self, email_lower: str) -> Optional[RoleByEmail]:
        return (await self._session.execute(
            select(RoleByEmail).where(func.lower(RoleByEmail.email) == email_lower)
        )).scalar_one_or_none()

    async def get_rbe_by_id(self, rule_id: UUID) -> Optional[RoleByEmail]:
        return (await self._session.execute(
            select(RoleByEmail).where(RoleByEmail.id == rule_id)
        )).scalar_one_or_none()

    async def role_codes_exist(self, codes: Sequence[str]) -> set[str]:
        if not codes:
            return set()
        rows = (await self._session.execute(
            select(Role.code).where(Role.code.in_(codes))
        )).all()
        return {r[0] for r in rows}

    async def permission_codes_exist(self, codes: Sequence[str]) -> set[str]:
        if not codes:
            return set()
        rows = (await self._session.execute(
            select(Permission.code).where(Permission.code.in_(codes))
        )).all()
        return {r[0] for r in rows}

    # ─── Groups ───────────────────────────────────────────────────

    async def list_groups(self) -> Sequence[Group]:
        return (await self._session.execute(
            select(Group).order_by(Group.name)
        )).scalars().all()

    async def get_group(self, group_id: UUID) -> Optional[Group]:
        return (await self._session.execute(
            select(Group).where(Group.id == group_id)
        )).scalar_one_or_none()

    async def get_group_by_code(self, code: str) -> Optional[Group]:
        return (await self._session.execute(
            select(Group).where(Group.code == code)
        )).scalar_one_or_none()

    async def group_member_count(self, group_id: UUID) -> int:
        return int((await self._session.execute(
            select(func.count(UserGroupRole.user_id))
            .where(UserGroupRole.group_id == group_id)
        )).scalar() or 0)

    async def group_perm_count(self, group_id: UUID) -> int:
        return int((await self._session.execute(
            select(func.count(GroupPermissionGrant.id))
            .where(GroupPermissionGrant.group_id == group_id)
        )).scalar() or 0)

    async def list_group_members_with_role(self, group_id: UUID) -> Sequence[Any]:
        return (await self._session.execute(
            select(User.id, User.email, User.full_name, Role.code, Role.name_ru)
            .join(UserGroupRole, UserGroupRole.user_id == User.id)
            .join(Role, Role.id == UserGroupRole.role_id)
            .where(UserGroupRole.group_id == group_id)
            .order_by(User.email)
        )).all()

    async def list_group_grants(self, group_id: UUID) -> Sequence[GroupPermissionGrant]:
        return (await self._session.execute(
            select(GroupPermissionGrant)
            .where(GroupPermissionGrant.group_id == group_id)
        )).scalars().all()

    async def clear_group_grants(self, group_id: UUID) -> None:
        await self._session.execute(
            delete(GroupPermissionGrant)
            .where(GroupPermissionGrant.group_id == group_id)
        )
