"""RBAC v3 — единый модуль управления доступом.

URL prefix: /rbac/v3
Заменяет старые rbac.py (v1) и rbac_v2.py (v2). Содержит ровно те endpoints,
которые реально используются фронтом rbacV3.ts.

Все endpoints требуют admin-прав (is_owner OR permission `admin.users`).
Это намеренная политика: управление доступом — операция уровня администратора.
Эффективная проверка прав на ОБЫЧНЫХ endpoints (не RBAC-админских) идёт через
require_permission в app/core/security.py, который теперь учитывает и роли,
и group_permission_grant (фикс C1).
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit_chain import append_audit_entry
from app.core.password import hash_password, validate_password_policy
from app.core.security import _has_permission, get_current_user, has_effective_permission
from app.database import get_db
from app.models.rbac_v3 import GroupPermissionGrant
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
from app.services.auth_service import revoke_all_sessions
from app.schemas.rbac_v3 import (
    GroupBrief,
    GroupCreatePayload,
    GroupDetail,
    GroupMember,
    GroupMemberAssignment,
    GroupMembersUpdate,
    GroupPermission,
    GroupPermissionsUpdate,
    GroupUpdatePayload,
    PasswordResetPayload,
    PermissionBrief,
    PreviewTokenResponse,
    RBACOverview,
    RoleBrief,
    RoleByEmailCreatePayload,
    RoleByEmailRule,
    RoleByEmailUpdatePayload,
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


router = APIRouter(prefix="/rbac/v3", tags=["rbac-v3"])


# =====================================================================
# Admin gate
# =====================================================================

def _require_admin(user: User) -> None:
    if user.is_owner:
        return
    if _has_permission(user, "admin.users"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: admin.users (or owner status)",
    )


# =====================================================================
# Helpers
# =====================================================================

async def _user_role_codes(db: AsyncSession, user_id: UUID) -> List[str]:
    q = await db.execute(
        select(Role.code)
        .join(user_role, user_role.c.role_id == Role.id)
        .where(user_role.c.user_id == user_id)
        .order_by(Role.sort_order)
    )
    return list(q.scalars().all())


async def _effective_permissions(db: AsyncSession, user_id: UUID) -> List[str]:
    """Все permission codes, которые юзер получает через все источники.

    Pack 147: объединение
      * global User.roles (через user_role)
      * per-group roles (через user_group_role)
      * group_permission_grant (grant)
      МИНУС group_permission_grant (deny).

    Зеркалит логику security.has_effective_permission, но возвращает
    плоский список для UI.
    """
    # Global roles → permissions
    role_perms_q = await db.execute(
        select(Permission.code)
        .join(role_permission, role_permission.c.permission_id == Permission.id)
        .join(user_role, user_role.c.role_id == role_permission.c.role_id)
        .where(user_role.c.user_id == user_id)
        .distinct()
    )
    role_perms = set(role_perms_q.scalars().all())

    # Pack 147: per-group role permissions
    ugr_perms_q = await db.execute(
        select(Permission.code)
        .join(role_permission, role_permission.c.permission_id == Permission.id)
        .join(UserGroupRole, UserGroupRole.role_id == role_permission.c.role_id)
        .where(UserGroupRole.user_id == user_id)
        .distinct()
    )
    role_perms.update(ugr_perms_q.scalars().all())

    # Group permission grants (overrides + denies) via UserGroupRole membership
    group_grants_q = await db.execute(
        select(GroupPermissionGrant.permission_code, GroupPermissionGrant.grant_type)
        .join(UserGroupRole, UserGroupRole.group_id == GroupPermissionGrant.group_id)
        .where(UserGroupRole.user_id == user_id)
    )
    grants_rows = list(group_grants_q.all())
    group_grants = {code for code, gtype in grants_rows if gtype == "grant"}
    group_denies = {code for code, gtype in grants_rows if gtype == "deny"}

    effective = (role_perms | group_grants) - group_denies
    return sorted(effective)


async def _hydrate_user(db: AsyncSession, u: User) -> UserBrief:
    role_q = await db.execute(
        select(Role.code, Role.name_ru)
        .join(user_role, user_role.c.role_id == Role.id)
        .where(user_role.c.user_id == u.id)
        .order_by(Role.sort_order)
    )
    rows = list(role_q.all())
    return UserBrief(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        department=u.department,
        is_active=u.is_active,
        is_owner=u.is_owner,
        must_change_password=u.must_change_password,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
        role_codes=[r.code for r in rows],
        role_names=[r.name_ru for r in rows],
        organization_id=u.organization_id,
        # Pack 147: allowed_companies устарел; список компаний — через
        # group memberships (см. group_memberships в UserDetail).
        allowed_companies=None,
    )


# =====================================================================
# Overview
# =====================================================================

@router.get("/overview", response_model=RBACOverview)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)

    users_total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    users_active = (
        await db.execute(select(func.count()).select_from(User).where(User.is_active.is_(True)))
    ).scalar_one()
    roles_total = (await db.execute(select(func.count()).select_from(Role))).scalar_one()
    perms_total = (await db.execute(select(func.count()).select_from(Permission))).scalar_one()
    rbe_total = (await db.execute(select(func.count()).select_from(RoleByEmail))).scalar_one()

    no_role_q = (
        select(func.count(User.id.distinct()))
        .outerjoin(user_role, user_role.c.user_id == User.id)
        .where(User.is_active.is_(True), user_role.c.role_id.is_(None))
    )
    users_without_roles = (await db.execute(no_role_q)).scalar_one()

    top_roles_q = (
        select(Role.code, Role.name_ru, func.count(user_role.c.user_id).label("cnt"))
        .outerjoin(user_role, user_role.c.role_id == Role.id)
        .group_by(Role.id, Role.code, Role.name_ru)
        .order_by(func.count(user_role.c.user_id).desc())
        .limit(5)
    )
    top_rows = (await db.execute(top_roles_q)).all()

    return RBACOverview(
        users_total=users_total,
        users_active=users_active,
        users_inactive=users_total - users_active,
        roles_total=roles_total,
        permissions_total=perms_total,
        role_by_email_rules=rbe_total,
        users_without_roles=users_without_roles,
        most_assigned_roles=[
            {"code": r.code, "name": r.name_ru, "user_count": r.cnt} for r in top_rows
        ],
    )


# =====================================================================
# Permissions catalog
# =====================================================================

@router.get("/permissions", response_model=List[PermissionBrief])
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    q = await db.execute(select(Permission).order_by(Permission.module, Permission.action))
    return [PermissionBrief.model_validate(p) for p in q.scalars().all()]


# =====================================================================
# Roles
# =====================================================================

@router.get("/roles", response_model=List[RoleBrief])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    q = await db.execute(
        select(Role, func.count(role_permission.c.permission_id).label("perm_count"))
        .outerjoin(role_permission, role_permission.c.role_id == Role.id)
        .group_by(Role.id)
        .order_by(Role.sort_order, Role.code)
    )
    out: list[RoleBrief] = []
    for r in q.all():
        rb = RoleBrief.model_validate(r.Role)
        rb.permission_count = r.perm_count or 0
        out.append(rb)
    return out


@router.get("/roles/{code}", response_model=RoleDetail)
async def get_role(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    role = (await db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
    if not role:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found")

    perms = list((await db.execute(
        select(Permission)
        .join(role_permission, role_permission.c.permission_id == Permission.id)
        .where(role_permission.c.role_id == role.id)
        .order_by(Permission.module, Permission.action)
    )).scalars().all())

    return RoleDetail(
        id=role.id,
        code=role.code,
        name_ru=role.name_ru,
        name_uz=role.name_uz,
        name_en=role.name_en,
        description_ru=role.description_ru,
        is_system=role.is_system,
        sort_order=role.sort_order,
        permission_count=len(perms),
        permissions=[PermissionBrief.model_validate(p) for p in perms],
    )


@router.post("/roles", response_model=RoleDetail, status_code=http_status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)

    if (await db.execute(select(Role).where(Role.code == payload.code))).scalar_one_or_none():
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Role '{payload.code}' already exists")

    perm_objs: list[Permission] = []
    if payload.permission_codes:
        perm_objs = list((await db.execute(
            select(Permission).where(Permission.code.in_(payload.permission_codes))
        )).scalars().all())
        missing = set(payload.permission_codes) - {p.code for p in perm_objs}
        if missing:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown permission codes: {sorted(missing)}",
            )

    role = Role(
        code=payload.code,
        name_ru=payload.name_ru,
        name_en=payload.name_en,
        description_ru=payload.description_ru,
        sort_order=payload.sort_order,
        is_system=False,
    )
    db.add(role)
    await db.flush()

    for p in perm_objs:
        await db.execute(role_permission.insert().values(role_id=role.id, permission_id=p.id))
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.role.create",
        entity_type="role", entity_id=str(role.id),
        notes=f"role={role.code}, permissions={len(perm_objs)}",
    )
    await db.commit()

    return await get_role(role.code, db, user)


@router.patch("/roles/{code}", response_model=RoleDetail)
async def update_role(
    code: str,
    payload: RoleUpdatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    role = (await db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
    if not role:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found")

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

    return await get_role(code, db, user)


@router.patch("/roles/{code}/permissions", response_model=RoleDetail)
async def update_role_permissions(
    code: str,
    payload: RolePermissionsUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    role = (await db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
    if not role:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found")

    found_perms = list((await db.execute(
        select(Permission).where(Permission.code.in_(payload.permission_codes))
    )).scalars().all())
    missing = set(payload.permission_codes) - {p.code for p in found_perms}
    if missing:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"Unknown permission codes: {sorted(missing)}",
        )

    # Фикс H5: запрет удалять `admin.users` из роли `admin` для не-owner —
    # иначе действующий админ потеряет доступ ко всей RBAC-машинерии.
    if (
        code == "admin"
        and not user.is_owner
        and "admin.users" not in {p.code for p in found_perms}
    ):
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Нельзя удалить право 'admin.users' из роли 'admin' без статуса owner.",
        )

    await db.execute(delete(role_permission).where(role_permission.c.role_id == role.id))
    for p in found_perms:
        await db.execute(role_permission.insert().values(role_id=role.id, permission_id=p.id))
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.role.update_permissions",
        entity_type="role", entity_id=str(role.id),
        notes=f"role={code}, permissions_count={len(found_perms)}",
    )
    await db.commit()

    return await get_role(code, db, user)


@router.delete("/roles/{code}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_role(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    role = (await db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
    if not role:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Role '{code}' not found")
    if role.is_system:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"System role '{code}' cannot be deleted",
        )

    user_count = int((await db.execute(
        select(func.count()).select_from(user_role).where(user_role.c.role_id == role.id)
    )).scalar() or 0)
    if user_count > 0:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Cannot delete role '{code}': {user_count} user(s) still assigned. Reassign them first.",
        )

    await db.execute(delete(role_permission).where(role_permission.c.role_id == role.id))
    role_id = str(role.id)
    await db.delete(role)
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.role.delete",
        entity_type="role", entity_id=role_id,
        notes=f"role={code}",
    )
    await db.commit()


# =====================================================================
# Users
# =====================================================================

@router.get("/users", response_model=UserListResponse)
async def list_users(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    is_active: Optional[bool] = Query(None),
    role_code: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by email or full_name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _require_admin(user)
    q = select(User)
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

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(User.full_name).limit(limit).offset(offset)
    users = list((await db.execute(q)).scalars().all())

    items = [await _hydrate_user(db, u) for u in users]
    return UserListResponse(items=items, total=total)


@router.get("/users/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")

    base = await _hydrate_user(db, u)
    perms = await _effective_permissions(db, u.id)

    rbe = (await db.execute(
        select(RoleByEmail).where(func.lower(RoleByEmail.email) == u.email.lower())
    )).scalar_one_or_none()
    rbe_dict = None
    if rbe:
        rbe_dict = {
            "role_codes": rbe.role_codes,
            "department": rbe.department,
            "allowed_sectors": rbe.allowed_sectors,
            "allowed_companies": rbe.allowed_companies,
            "notes": rbe.notes,
        }

    # Pack 147: per-(user, group) role memberships.
    mem_rows = (await db.execute(
        select(
            Group.id, Group.code, Group.name, Group.company_id,
            Role.code, Role.name_ru,
        )
        .join(UserGroupRole, UserGroupRole.group_id == Group.id)
        .join(Role, Role.id == UserGroupRole.role_id)
        .where(UserGroupRole.user_id == u.id)
        .order_by(Group.name)
    )).all()
    memberships = [
        UserGroupMembership(
            group_id=r[0], group_code=r[1], group_name=r[2], company_id=r[3],
            role_code=r[4], role_name=r[5],
        )
        for r in mem_rows
    ]

    return UserDetail(
        **base.model_dump(),
        effective_permissions=perms,
        role_by_email_rule=rbe_dict,
        group_memberships=memberships,
        is_external=bool(getattr(u, "is_external", False)),
        bypass_moderation=bool(getattr(u, "bypass_moderation", False)),
        external_org_name=getattr(u, "external_org_name", None),
    )


@router.post("/users", response_model=UserDetail, status_code=http_status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)

    exists = (await db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "User with this email already exists")

    try:
        validate_password_policy(payload.password)
    except Exception as e:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(e))

    roles: list[Role] = []
    if payload.role_codes:
        roles = list((await db.execute(
            select(Role).where(Role.code.in_(payload.role_codes))
        )).scalars().all())
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
        password_hash=hash_password(payload.password),
        must_change_password=payload.must_change_password,
        is_active=True,
        is_owner=False,
        organization_id=payload.organization_id,
        # Pack 147: allowed_companies удалено. Per-company access — через
        # group memberships, см. PUT /rbac/v3/groups/{id}/members.
    )
    db.add(new_user)
    await db.flush()

    for r in roles:
        await db.execute(user_role.insert().values(user_id=new_user.id, role_id=r.id))
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.user.create",
        entity_type="user", entity_id=str(new_user.id),
        notes=f"email={payload.email}, roles={payload.role_codes}",
    )
    await db.commit()

    return await get_user(new_user.id, db, user)


@router.patch("/users/{user_id}", response_model=UserDetail)
async def update_user(
    user_id: UUID,
    payload: UserUpdatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)

    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")

    if u.id == user.id and payload.is_active is False:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "You cannot deactivate your own account.",
        )

    changes_log: list[str] = []
    # Сессии revoke'аем если меняется is_active=False ИЛИ список ролей
    # (фикс C5/H7: иначе access-JWT живёт до expiry со старыми claims).
    must_revoke_sessions = False

    if payload.full_name is not None and payload.full_name != u.full_name:
        u.full_name = payload.full_name
        changes_log.append(f"full_name={payload.full_name!r}")
    if payload.department is not None and payload.department != u.department:
        u.department = payload.department
        changes_log.append(f"department={payload.department!r}")
    if payload.is_active is not None and payload.is_active != u.is_active:
        u.is_active = payload.is_active
        changes_log.append(f"is_active={payload.is_active}")
        if payload.is_active is False:
            must_revoke_sessions = True
    if payload.organization_id is not None and payload.organization_id != u.organization_id:
        u.organization_id = payload.organization_id
        changes_log.append(f"organization_id={payload.organization_id}")

    if payload.allowed_companies is not None:
        # Pack 147: payload.allowed_companies теперь deprecated и игнорируется.
        # Per-company доступ управляется через PUT /rbac/v3/groups/{id}/members
        # (см. Stage 5). Поле в схеме оставлено для backward-compat HTTP-клиентов;
        # frontend ходит через groups endpoint.
        changes_log.append("allowed_companies=<ignored: use groups endpoint>")

    if payload.role_codes is not None:
        roles = list((await db.execute(
            select(Role).where(Role.code.in_(payload.role_codes))
        )).scalars().all())
        missing = set(payload.role_codes) - {r.code for r in roles}
        if missing:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown role codes: {sorted(missing)}",
            )
        # Сравниваем со старым списком — revoke только при реальном изменении.
        old_role_codes_q = await db.execute(
            select(Role.code)
            .join(user_role, user_role.c.role_id == Role.id)
            .where(user_role.c.user_id == u.id)
        )
        old_role_codes = sorted(old_role_codes_q.scalars().all())
        new_role_codes = sorted(payload.role_codes)
        if old_role_codes != new_role_codes:
            # Фикс H5: не даём админу (не-owner) снять с себя роль admin —
            # иначе через PATCH /users/me можно случайно потерять доступ.
            if (
                u.id == user.id
                and not user.is_owner
                and "admin" in old_role_codes
                and "admin" not in new_role_codes
            ):
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "Нельзя снять с себя роль 'admin'. Попросите другого администратора или owner.",
                )

            # Фикс M5: нельзя удалить role admin у юзера, если он последний
            # её носитель (платформа осталась бы без активных админов; только
            # owner мог бы это починить). Для owner — оставляем possibility.
            if (
                "admin" in old_role_codes
                and "admin" not in new_role_codes
                and not user.is_owner
            ):
                others_q = await db.execute(
                    select(func.count(User.id))
                    .join(user_role, user_role.c.user_id == User.id)
                    .join(Role, Role.id == user_role.c.role_id)
                    .where(
                        Role.code == "admin",
                        User.is_active.is_(True),
                        User.id != u.id,
                    )
                )
                other_admins = int(others_q.scalar() or 0)
                if other_admins == 0:
                    raise HTTPException(
                        http_status.HTTP_409_CONFLICT,
                        "Нельзя удалить роль 'admin': этот пользователь — последний "
                        "активный администратор платформы. Сначала назначьте другого.",
                    )

            await db.execute(delete(user_role).where(user_role.c.user_id == u.id))
            for r in roles:
                await db.execute(user_role.insert().values(user_id=u.id, role_id=r.id))
            changes_log.append(f"roles={payload.role_codes}")
            must_revoke_sessions = True

    revoked_count = 0
    if must_revoke_sessions:
        revoked_count = await revoke_all_sessions(db, u.id)
        if revoked_count:
            changes_log.append(f"sessions_revoked={revoked_count}")

    await db.commit()

    if changes_log:
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.update",
            entity_type="user", entity_id=str(u.id),
            notes=", ".join(changes_log)[:500],
        )
        await db.commit()

    return await get_user(u.id, db, user)


# ─── Per-user group memberships (Pack 148-followup) ───────────────────
# Convenience endpoints so admins can add/change/remove a single user's
# group membership directly from the User-detail drawer, without having
# to PUT the entire group member list.

@router.put("/users/{user_id}/memberships/{group_id}", response_model=UserDetail)
async def upsert_user_membership(
    user_id: UUID,
    group_id: UUID,
    payload: UserMembershipUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add user to group with the supplied role, or change their role.

    Idempotent — if a row already exists for (user_id, group_id), its
    role_id is updated. Otherwise a new row is inserted.
    """
    _require_admin(user)

    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
    g = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")
    role = (await db.execute(
        select(Role).where(Role.code == payload.role_code)
    )).scalar_one_or_none()
    if not role:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"Unknown role code: {payload.role_code!r}",
        )

    existing = (await db.execute(
        select(UserGroupRole).where(
            UserGroupRole.user_id == user_id,
            UserGroupRole.group_id == group_id,
        )
    )).scalar_one_or_none()
    action = "rbac.user.membership.upsert"
    if existing:
        if existing.role_id == role.id:
            return await get_user(user_id, db, user)
        existing.role_id = role.id
    else:
        db.add(UserGroupRole(
            user_id=user_id, group_id=group_id, role_id=role.id,
        ))
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action=action,
        entity_type="user", entity_id=str(user_id),
        notes=f"group={g.code}, role={role.code}",
    )
    await db.commit()

    return await get_user(user_id, db, user)


@router.delete(
    "/users/{user_id}/memberships/{group_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def remove_user_membership(
    user_id: UUID,
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove a user from a single group. No-op if not a member."""
    _require_admin(user)
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")

    result = await db.execute(
        delete(UserGroupRole).where(
            UserGroupRole.user_id == user_id,
            UserGroupRole.group_id == group_id,
        )
    )
    await db.commit()

    if result.rowcount:
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.user.membership.remove",
            entity_type="user", entity_id=str(user_id),
            notes=f"group_id={group_id}",
        )
        await db.commit()


@router.post("/users/{user_id}/reset-password", status_code=http_status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: UUID,
    payload: PasswordResetPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)

    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")

    try:
        validate_password_policy(payload.new_password)
    except Exception as e:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(e))

    u.password_hash = hash_password(payload.new_password)
    u.must_change_password = payload.must_change_password
    # Фикс C5: после admin-resetа пароля выкидываем все живые refresh-сессии,
    # чтобы старые токены не могли продолжать жить с прежней парой.
    revoked = await revoke_all_sessions(db, u.id)
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.user.reset_password",
        entity_type="user", entity_id=str(u.id),
        notes=f"target={u.email}, force_change={payload.must_change_password}, sessions_revoked={revoked}",
    )
    await db.commit()


@router.delete("/users/{user_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-deactivate a user (sets is_active=False)."""
    _require_admin(user)

    if user_id == user.id:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "You cannot deactivate your own account.",
        )

    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")

    u.is_active = False
    # Фикс C5: revoke refresh-токенов сразу, иначе access-JWT и refresh
    # юзера живут до своих expiry уже под "отключённым" аккаунтом.
    revoked = await revoke_all_sessions(db, u.id)
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.user.deactivate",
        entity_type="user", entity_id=str(u.id),
        notes=f"target={u.email}, sessions_revoked={revoked}",
    )


@router.delete("/users/{user_id}/permanent", status_code=http_status.HTTP_204_NO_CONTENT)
async def permanently_delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Hard delete. Owner cannot be deleted; cannot delete self."""
    _require_admin(user)

    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
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

    # Фикс C5: revoke сессии явно. CASCADE удалит их вместе с user,
    # но если delete упадёт по FK — revoke уже отрезал юзера от сессий.
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


@router.post("/users/{user_id}/preview-token", response_model=PreviewTokenResponse)
async def create_preview_token(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Issue a 30-minute impersonate token.

    Safety rails (фикс C4):
      * Нельзя impersonate себя.
      * Нельзя impersonate неактивного юзера.
      * Нельзя impersonate owner.
      * Нельзя impersonate любого юзера, у которого есть `admin.users`
        через ЛЮБУЮ роль (включая кастомные) или через группу.
        Иначе actor с `admin.users` (но без роли `admin`) мог бы взять
        JWT юзера с таким же правом и развить эскалацию RBAC.
    """
    _require_admin(user)

    target = (await db.execute(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == user_id)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "User not found")
    if str(target.id) == str(user.id):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Cannot impersonate yourself")
    if not target.is_active:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Cannot impersonate inactive user")
    if target.is_owner:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Cannot impersonate the platform owner")
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


# =====================================================================
# Role-by-email auto-assignment
# =====================================================================

@router.get("/role-by-email", response_model=List[RoleByEmailRule])
async def list_role_by_email(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    q = await db.execute(select(RoleByEmail).order_by(RoleByEmail.email))
    return [RoleByEmailRule.model_validate(r) for r in q.scalars().all()]


@router.post(
    "/role-by-email",
    response_model=RoleByEmailRule,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_role_by_email(
    payload: RoleByEmailCreatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)

    dup = (await db.execute(
        select(RoleByEmail).where(func.lower(RoleByEmail.email) == payload.email.lower())
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Auto-assignment rule for {payload.email} already exists.",
        )

    found_codes = {row[0] for row in (await db.execute(
        select(Role.code).where(Role.code.in_(payload.role_codes))
    )).all()}
    missing = set(payload.role_codes) - found_codes
    if missing:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"Unknown role codes: {sorted(missing)}",
        )

    rule = RoleByEmail(
        email=payload.email.lower(),
        role_codes=payload.role_codes,
        department=payload.department,
        allowed_sectors=payload.allowed_sectors,
        allowed_companies=payload.allowed_companies,
        notes=payload.notes,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.rbe.create",
        entity_type="role_by_email", entity_id=str(rule.id),
        notes=f"email={payload.email}, roles={payload.role_codes}",
    )
    await db.commit()

    return rule


@router.patch("/role-by-email/{rule_id}", response_model=RoleByEmailRule)
async def update_role_by_email(
    rule_id: UUID,
    payload: RoleByEmailUpdatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Partial update existing email rule. Email и id immutable."""
    _require_admin(user)
    rule = (await db.execute(
        select(RoleByEmail).where(RoleByEmail.id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Rule not found")

    changes: list[str] = []
    if payload.role_codes is not None:
        found_codes = {row[0] for row in (await db.execute(
            select(Role.code).where(Role.code.in_(payload.role_codes))
        )).all()}
        missing = set(payload.role_codes) - found_codes
        if missing:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown role codes: {sorted(missing)}",
            )
        if sorted(rule.role_codes or []) != sorted(payload.role_codes):
            rule.role_codes = payload.role_codes
            changes.append(f"role_codes={payload.role_codes}")

    if payload.department is not None and payload.department != rule.department:
        rule.department = payload.department
        changes.append(f"department={payload.department!r}")
    if payload.allowed_sectors is not None and (rule.allowed_sectors or []) != payload.allowed_sectors:
        rule.allowed_sectors = payload.allowed_sectors
        changes.append(f"allowed_sectors={payload.allowed_sectors}")
    if payload.allowed_companies is not None and (rule.allowed_companies or []) != payload.allowed_companies:
        rule.allowed_companies = payload.allowed_companies
        changes.append(f"allowed_companies={payload.allowed_companies}")
    if payload.notes is not None and payload.notes != rule.notes:
        rule.notes = payload.notes
        changes.append(f"notes={payload.notes!r}")

    if changes:
        await db.commit()
        await db.refresh(rule)
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="rbac.rbe.update",
            entity_type="role_by_email", entity_id=str(rule.id),
            notes=f"email={rule.email}, " + ", ".join(changes)[:400],
        )
        await db.commit()

    return RoleByEmailRule.model_validate(rule)


@router.delete("/role-by-email/{rule_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_role_by_email(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    rule = (await db.execute(
        select(RoleByEmail).where(RoleByEmail.id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Rule not found")

    email = rule.email
    await db.delete(rule)
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.rbe.delete",
        entity_type="role_by_email", entity_id=str(rule_id),
        notes=f"email={email}",
    )
    await db.commit()


# =====================================================================
# Groups
# =====================================================================

async def _group_to_brief(db: AsyncSession, g: Group) -> GroupBrief:
    # Pack 147: member count via user_group_role (per-(user,group) role rows).
    member_count = (await db.execute(
        select(func.count(UserGroupRole.user_id))
        .where(UserGroupRole.group_id == g.id)
    )).scalar() or 0
    perm_count = (await db.execute(
        select(func.count(GroupPermissionGrant.id))
        .where(GroupPermissionGrant.group_id == g.id)
    )).scalar() or 0
    return GroupBrief(
        id=g.id,
        code=g.code,
        name=g.name,
        description=g.description,
        company_id=g.company_id,
        organization_id=g.organization_id,
        department=g.department,
        member_count=member_count,
        permission_count=perm_count,
        role_codes=[],
    )


@router.get("/groups", response_model=List[GroupBrief])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    rows = (await db.execute(select(Group).order_by(Group.name))).scalars().all()
    return [await _group_to_brief(db, g) for g in rows]


@router.get("/groups/{group_id}", response_model=GroupDetail)
async def get_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    g = (await db.execute(
        select(Group).where(Group.id == group_id)
    )).scalar_one_or_none()
    if not g:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")

    base = await _group_to_brief(db, g)
    grants = (await db.execute(
        select(GroupPermissionGrant).where(GroupPermissionGrant.group_id == group_id)
    )).scalars().all()

    # Pack 147: members from user_group_role + their per-group role.
    member_rows = (await db.execute(
        select(User.id, User.email, User.full_name, Role.code, Role.name_ru)
        .join(UserGroupRole, UserGroupRole.user_id == User.id)
        .join(Role, Role.id == UserGroupRole.role_id)
        .where(UserGroupRole.group_id == group_id)
        .order_by(User.email)
    )).all()

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
            GroupPermission(code=p.permission_code) for p in grants
            if p.grant_type == "grant"
        ],
        roles=[],
    )


@router.post("/groups", response_model=GroupBrief, status_code=http_status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    if (await db.execute(select(Group).where(Group.code == payload.code))).scalar_one_or_none():
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Group with code '{payload.code}' already exists",
        )
    g = Group(**payload.model_dump())
    db.add(g)
    await db.flush()
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.group.create",
        entity_type="group", entity_id=str(g.id),
        notes=f"code={g.code}, name={g.name}",
    )
    await db.commit()

    return await _group_to_brief(db, g)


@router.patch("/groups/{group_id}", response_model=GroupBrief)
async def update_group(
    group_id: UUID,
    payload: GroupUpdatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    g = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
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

    return await _group_to_brief(db, g)


@router.delete("/groups/{group_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    g = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")
    code = g.code
    gid = str(g.id)
    await db.delete(g)
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.group.delete",
        entity_type="group", entity_id=gid,
        notes=f"code={code}",
    )
    await db.commit()


@router.put("/groups/{group_id}/members", response_model=GroupDetail)
async def set_group_members(
    group_id: UUID,
    payload: GroupMembersUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace all members of a group with the supplied list.

    Pack 147 preferred shape: `{"members": [{"user_id": ..., "role_code": ...}]}`.
    Legacy shape `{"user_ids": [UUID, ...]}` is still accepted; each user
    gets role `viewer` by default.

    Validates that all user_ids exist and all role_codes exist. Replaces
    the FULL membership atomically (DELETE old → INSERT new).
    """
    _require_admin(user)
    g = (await db.execute(
        select(Group).where(Group.id == group_id)
    )).scalar_one_or_none()
    if not g:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")

    # Normalise to a list of (user_id, role_code) tuples.
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

    # Validate users
    found_users = (await db.execute(
        select(User.id).where(User.id.in_(user_ids))
    )).scalars().all() if user_ids else []
    found_user_ids = set(found_users)
    unknown_users = [str(uid) for uid in user_ids if uid not in found_user_ids]
    if unknown_users:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"Unknown user_ids: {unknown_users}",
        )

    # Validate roles + build code→id map
    role_rows = (await db.execute(
        select(Role.id, Role.code).where(Role.code.in_(role_codes))
    )).all() if role_codes else []
    role_id_by_code = {r.code: r.id for r in role_rows}
    unknown_roles = [rc for rc in role_codes if rc not in role_id_by_code]
    if unknown_roles:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"Unknown role codes: {sorted(unknown_roles)}",
        )

    # Atomic replace: drop existing, insert new.
    await db.execute(
        delete(UserGroupRole).where(UserGroupRole.group_id == group_id)
    )
    for uid, rc in assignments:
        db.add(UserGroupRole(
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

    return await get_group(group_id, db, user)


@router.put("/groups/{group_id}/permissions", response_model=GroupDetail)
async def set_group_permissions(
    group_id: UUID,
    payload: GroupPermissionsUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace all GRANT permissions of a group with the supplied list of codes.

    Все коды валидируются по таблице permissions. Старые grants полностью
    заменяются. deny-grants не управляются через этот endpoint (UI их не
    поддерживает) и удаляются вместе с остальными.
    """
    _require_admin(user)
    g = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Group not found")

    codes = list(dict.fromkeys(payload.permission_codes))  # preserve order, drop dupes
    if codes:
        found_codes = {row[0] for row in (await db.execute(
            select(Permission.code).where(Permission.code.in_(codes))
        )).all()}
        missing = set(codes) - found_codes
        if missing:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown permission codes: {sorted(missing)}",
            )

    await db.execute(
        delete(GroupPermissionGrant).where(GroupPermissionGrant.group_id == group_id)
    )
    for code in codes:
        db.add(GroupPermissionGrant(
            group_id=group_id,
            permission_code=code,
            grant_type="grant",
            granted_by_id=user.id,
        ))
    await db.commit()

    await append_audit_entry(
        db, actor_id=str(user.id), actor_email=user.email,
        action="rbac.group.set_permissions",
        entity_type="group", entity_id=str(g.id),
        notes=f"code={g.code}, permissions={len(codes)}",
    )
    await db.commit()

    return await get_group(group_id, db, user)
