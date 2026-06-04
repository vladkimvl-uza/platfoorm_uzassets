"""RBAC v3 REST — thin HTTP shim (refactored 2026-05-25).

URL prefix: /rbac/v3. All endpoints require admin (is_owner OR admin.users).
Business logic + audit chaining live in `app.services.rbac_v3.RbacV3Service`.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.dependencies.rbac_v3 import RbacV3ServiceDep
from app.models.user import User
from app.schemas.rbac_v3 import (
    GroupBrief,
    GroupCreatePayload,
    GroupDetail,
    GroupMembersUpdate,
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
    SetOwnerPayload,
    UserCreatePayload,
    UserDetail,
    UserListResponse,
    UserMembershipUpsert,
    UserUpdatePayload,
)

router = APIRouter(prefix="/rbac/v3", tags=["rbac-v3"])


# ─── Overview / Permissions ───────────────────────────────────────

@router.get("/overview", response_model=RBACOverview)
async def get_overview(
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.overview(db, user)


@router.get("/permissions", response_model=list[PermissionBrief])
async def list_permissions(
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.list_permissions(db, user)


# ─── Roles ────────────────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleBrief])
async def list_roles(
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.list_roles(db, user)


@router.get("/roles/{code}", response_model=RoleDetail)
async def get_role(
    code: str,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.get_role(code, db, user)


@router.post(
    "/roles", response_model=RoleDetail,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_role(
    payload: RoleCreatePayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.create_role(payload, db, user)


@router.patch("/roles/{code}", response_model=RoleDetail)
async def update_role(
    code: str,
    payload: RoleUpdatePayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.update_role(code, payload, db, user)


@router.patch("/roles/{code}/permissions", response_model=RoleDetail)
async def update_role_permissions(
    code: str,
    payload: RolePermissionsUpdate,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.update_role_permissions(code, payload, db, user)


@router.delete("/roles/{code}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_role(
    code: str,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.delete_role(code, db, user)


# ─── Users ────────────────────────────────────────────────────────

@router.get("/users", response_model=UserListResponse)
async def list_users(
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    is_active: Optional[bool] = Query(None),
    role_code: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by email or full_name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return await service.list_users(
        db, user,
        is_active=is_active, role_code=role_code, search=search,
        limit=limit, offset=offset,
    )


@router.get("/users/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.get_user(user_id, db, user)


@router.post(
    "/users", response_model=UserDetail,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_user(
    payload: UserCreatePayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.create_user(payload, db, user)


@router.patch("/users/{user_id}", response_model=UserDetail)
async def update_user(
    user_id: UUID,
    payload: UserUpdatePayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.update_user(user_id, payload, db, user)


@router.put("/users/{user_id}/permissions", response_model=UserDetail)
async def set_user_permissions(
    user_id: UUID,
    payload: RolePermissionsUpdate,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Прямое per-user редактирование доступа к модулям (OWNER/ADMIN)."""
    return await service.set_user_permissions(user_id, payload, db, user)


@router.put("/users/{user_id}/memberships/{group_id}", response_model=UserDetail)
async def upsert_user_membership(
    user_id: UUID,
    group_id: UUID,
    payload: UserMembershipUpsert,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.upsert_user_membership(user_id, group_id, payload, db, user)


@router.delete(
    "/users/{user_id}/memberships/{group_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def remove_user_membership(
    user_id: UUID,
    group_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.remove_user_membership(user_id, group_id, db, user)


@router.post(
    "/users/{user_id}/force-password-change",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def force_password_change(
    user_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.force_password_change(user_id, db, user)


@router.post(
    "/users/{user_id}/reset-password",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def reset_password(
    user_id: UUID,
    payload: PasswordResetPayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.reset_password(user_id, payload, db, user)


@router.delete("/users/{user_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.deactivate_user(user_id, db, user)


@router.delete(
    "/users/{user_id}/permanent",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def permanently_delete_user(
    user_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.permanently_delete_user(user_id, db, user)


@router.post("/users/{user_id}/owner", response_model=UserDetail)
async def set_user_owner(
    user_id: UUID,
    payload: SetOwnerPayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Назначить/снять статус OWNER. Доступно только текущему OWNER-у."""
    return await service.set_owner(user_id, payload.is_owner, db, user)


@router.post("/users/{user_id}/preview-token", response_model=PreviewTokenResponse)
async def create_preview_token(
    user_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.create_preview_token(user_id, db, user)


# ─── Role-by-email auto-assignment ────────────────────────────────

@router.get("/role-by-email", response_model=list[RoleByEmailRule])
async def list_role_by_email(
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.list_rbe(db, user)


@router.post(
    "/role-by-email", response_model=RoleByEmailRule,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_role_by_email(
    payload: RoleByEmailCreatePayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.create_rbe(payload, db, user)


@router.patch("/role-by-email/{rule_id}", response_model=RoleByEmailRule)
async def update_role_by_email(
    rule_id: UUID,
    payload: RoleByEmailUpdatePayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.update_rbe(rule_id, payload, db, user)


@router.delete(
    "/role-by-email/{rule_id}", status_code=http_status.HTTP_204_NO_CONTENT,
)
async def delete_role_by_email(
    rule_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.delete_rbe(rule_id, db, user)


# ─── Groups ───────────────────────────────────────────────────────

@router.get("/groups", response_model=list[GroupBrief])
async def list_groups(
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.list_groups(db, user)


@router.get("/groups/{group_id}", response_model=GroupDetail)
async def get_group(
    group_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.get_group(group_id, db, user)


@router.post(
    "/groups", response_model=GroupBrief,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_group(
    payload: GroupCreatePayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.create_group(payload, db, user)


@router.patch("/groups/{group_id}", response_model=GroupBrief)
async def update_group(
    group_id: UUID,
    payload: GroupUpdatePayload,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.update_group(group_id, payload, db, user)


@router.delete("/groups/{group_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await service.delete_group(group_id, db, user)


@router.put("/groups/{group_id}/members", response_model=GroupDetail)
async def set_group_members(
    group_id: UUID,
    payload: GroupMembersUpdate,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.set_group_members(group_id, payload, db, user)


@router.put("/groups/{group_id}/permissions", response_model=GroupDetail)
async def set_group_permissions(
    group_id: UUID,
    payload: GroupPermissionsUpdate,
    service: RbacV3ServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.set_group_permissions(group_id, payload, db, user)
